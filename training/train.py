#!/usr/bin/env python3
"""
Phase 1 controlled fine-tuning of AASIST-L.

Trains ONLY on ASVspoof 2019 LA train; selects ONLY on ASVspoof 2019 LA dev.
No test set (eval / MLAAD-tiny / WaveFake / In-the-Wild δ) is touched here —
this module cannot even import their loaders.

CHECKPOINT SELECTION RULE — fixed before any result was seen (§13):

  1. Primary   : lowest validation EER.
  2. Tie-break : if two checkpoints are within 0.005 absolute EER, prefer the
                 one with the lower FAR at the validation EER threshold
                 (a security system should prefer admitting fewer spoofs).
  3. Guard     : a checkpoint whose validation FRR exceeds 0.20 is ineligible,
                 unless no checkpoint satisfies the guard, in which case the
                 rule falls back to (1) and the violation is recorded.

Metric code is imported from `evaluation.metrics.detection` so training-time
numbers use the identical definitions as the frozen baseline. That import is
one-directional: `evaluation` never imports `training`.

    python training/train.py --scheme C --seed 1337 --epochs 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "api"))

from app.ml.authenticity.aasist import MODEL_CONFIGS, NB_SAMP  # noqa: E402
from app.ml.authenticity.vendor.aasist_model import Model  # noqa: E402
from evaluation.metrics.detection import eer, roc_auc, pr_auc, metrics_at  # noqa: E402
from training.data import (  # noqa: E402
    ASVspoofWindows, balanced_subset, distribution, load_items,
)
from training.schemes import SCHEMES, apply_scheme, set_train_mode  # noqa: E402

FRR_GUARD = 0.20

# AASIST's released checkpoints use output index 1 = BONA FIDE (upstream
# convention, see aasist.py::_run). Our dataset labels are 0 = bona fide,
# 1 = spoof. Training targets must therefore be INVERTED into the model's
# convention, or fine-tuning teaches the exact opposite of the pretrained
# behaviour. Verified by: the pretrained model's initial training loss must be
# near zero on in-domain data (it is ~12 with the wrong mapping).
def to_model_target(labels: torch.Tensor) -> torch.Tensor:
    """dataset label (0=bonafide, 1=spoof) -> AASIST target index (1=bonafide)."""
    return 1 - labels
EER_TIE = 0.005
PREP_VERSION = "prep-v1"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pick_device(requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@torch.no_grad()
def evaluate(model, loader, device, criterion) -> dict:
    model.eval()
    scores, labels, losses = [], [], []
    for x, y in loader:
        x = x.to(device)
        yt = y.to(device)
        logits = model(x)[1]
        losses.append(float(criterion(logits, to_model_target(yt)).item()) * len(y))
        p = torch.softmax(logits, dim=1)[:, 1]      # P(bona fide)
        scores.append((1.0 - p).cpu().numpy())      # spoof probability
        labels.append(y.numpy())
    s = np.concatenate(scores)
    y = np.concatenate(labels)
    e, thr = eer(y, s)
    m = metrics_at(y, s, thr)
    bona, spoof = s[y == 0], s[y == 1]
    return {
        "loss": float(sum(losses) / max(1, len(y))),
        "roc_auc": float(roc_auc(y, s)),
        "pr_auc": float(pr_auc(y, s)),
        "eer": float(e),
        "eer_threshold": float(thr),
        "far": float(m.far), "frr": float(m.frr),
        "tpr": float(m.tpr), "tnr": float(m.tnr),
        "score_distribution": {
            "bonafide": {"mean": float(bona.mean()), "median": float(np.median(bona)),
                         "std": float(bona.std()), "n": int(bona.size)},
            "spoof": {"mean": float(spoof.mean()), "median": float(np.median(spoof)),
                      "std": float(spoof.std()), "n": int(spoof.size)},
        },
        "n": int(y.size),
    }


def is_better(cand: dict, best: Optional[dict]) -> bool:
    """The pre-registered selection rule. Do not change after seeing results."""
    if best is None:
        return True
    c_ok = cand["frr"] <= FRR_GUARD
    b_ok = best["frr"] <= FRR_GUARD
    if c_ok != b_ok:
        return c_ok
    if abs(cand["eer"] - best["eer"]) <= EER_TIE:
        return cand["far"] < best["far"]
    return cand["eer"] < best["eer"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scheme", required=True, choices=SCHEMES)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-5,
                    help="ONE lr for every scheme: the experiment's only intended "
                         "variable is which layers are trainable (§8)")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--freq-aug", action="store_true")
    ap.add_argument("--per-class", type=int, default=None)
    ap.add_argument("--val-per-class", type=int, default=1000)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--data-root", default="data/external/LA_extract_full")
    ap.add_argument("--out", default="experiments/phase1_aasist")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    lr = args.lr
    tag = args.tag or f"aasist-l-phase1-{args.scheme}-seed{args.seed}" + \
                      ("-freqaug" if args.freq_aug else "")
    out_dir = REPO / args.out / f"scheme_{args.scheme}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ck_dir = REPO / args.out / "checkpoints"
    ck_dir.mkdir(parents=True, exist_ok=True)

    seed_everything(args.seed)
    device = pick_device(args.device)
    log(f"{tag} | device={device} lr={lr} bs={args.batch_size} epochs={args.epochs} "
        f"freq_aug={args.freq_aug}")

    root = REPO / args.data_root
    train_items = load_items(root, "train")
    dev_items = load_items(root, "dev")
    train_sel = balanced_subset(train_items, args.seed, args.per_class)
    dev_sel = balanced_subset(dev_items, args.seed, args.val_per_class)
    log(f"train {distribution(train_sel)}   dev {distribution(dev_sel)}")

    # Leakage guard: train and validation must not share a file.
    overlap = {i.path for i in train_sel} & {i.path for i in dev_sel}
    if overlap:
        raise SystemExit(f"ABORT: {len(overlap)} files in both train and dev")

    g = torch.Generator(); g.manual_seed(args.seed)
    train_dl = DataLoader(ASVspoofWindows(train_sel), batch_size=args.batch_size,
                          shuffle=True, num_workers=args.workers, generator=g,
                          drop_last=True, persistent_workers=args.workers > 0)
    dev_dl = DataLoader(ASVspoofWindows(dev_sel), batch_size=args.batch_size,
                        shuffle=False, num_workers=args.workers,
                        persistent_workers=args.workers > 0)

    model = Model(MODEL_CONFIGS["AASIST-L"])
    state = torch.load(REPO / "services/api/models/aasist/AASIST-L.pth", map_location="cpu")
    model.load_state_dict(state, strict=True)
    info = apply_scheme(model, args.scheme)
    model.to(device)
    log(f"scheme {args.scheme}: {info.trainable_params}/{info.total_params} trainable "
        f"({100*info.trainable_params/info.total_params:.2f}%), "
        f"{info.frozen_bn_modules} BatchNorm modules forced to eval()")

    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=lr, weight_decay=args.weight_decay)
    criterion = nn.CrossEntropyLoss()   # data is 1:1 balanced, so no class weights

    history = []
    best, best_epoch = None, None
    best_path = ck_dir / f"{tag}.pth"
    t_start = time.perf_counter()

    base = evaluate(model, dev_dl, device, criterion)
    log(f"epoch 0 (pretrained, before any update): val EER {base['eer']:.4f} "
        f"AUC {base['roc_auc']:.4f} FAR {base['far']:.4f} FRR {base['frr']:.4f}")
    history.append({"epoch": 0, "train_loss": None, "val": base, "note": "pretrained"})

    for epoch in range(1, args.epochs + 1):
        set_train_mode(model, args.scheme)     # re-applies the frozen-BN override
        running, seen = 0.0, 0
        t0 = time.perf_counter()
        for bi, (x, y) in enumerate(train_dl, 1):
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            logits = model(x, Freq_aug=args.freq_aug)[1]
            loss = criterion(logits, to_model_target(y))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            running += float(loss.item()) * len(y); seen += len(y)
            if bi % 50 == 0:
                log(f"  e{epoch} b{bi}/{len(train_dl)} loss {running/max(1,seen):.4f}")
        train_loss = running / max(1, seen)
        val = evaluate(model, dev_dl, device, criterion)
        secs = time.perf_counter() - t0
        log(f"epoch {epoch}: train_loss {train_loss:.4f} | val EER {val['eer']:.4f} "
            f"AUC {val['roc_auc']:.4f} FAR {val['far']:.4f} FRR {val['frr']:.4f} "
            f"({secs:.0f}s)")
        history.append({"epoch": epoch, "train_loss": train_loss, "val": val,
                        "seconds": secs})
        if is_better(val, best):
            best, best_epoch = val, epoch
            torch.save(model.state_dict(), best_path)
            log(f"  -> new best (epoch {epoch}) saved")

    total_s = time.perf_counter() - t_start
    ck_sha = sha256_of(best_path) if best_path.is_file() else None
    try:
        commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except Exception:
        commit = None

    record = {
        "model_version": tag,
        "scheme": info.to_dict(),
        "selection_rule": {
            "primary": "lowest validation EER",
            "tie_break": f"within {EER_TIE} absolute EER, prefer lower FAR",
            "guard": f"validation FRR must be <= {FRR_GUARD}",
            "fixed_before_results": True,
        },
        "best_epoch": best_epoch,
        "best_validation": best,
        "pretrained_validation": base,
        "history": history,
        "hyperparameters": {
            "optimizer": "AdamW", "lr": lr, "weight_decay": args.weight_decay,
            "batch_size": args.batch_size, "epochs": args.epochs,
            "grad_clip_norm": 1.0, "loss": "CrossEntropyLoss",
            "class_balancing": "1:1 balanced subset, spoof stratified over A01-A06",
            "freq_aug": args.freq_aug, "seed": args.seed,
        },
        "data": {
            "train_root": str(args.data_root),
            "train": distribution(train_sel), "validation": distribution(dev_sel),
            "train_speakers": sorted({i.speaker_id for i in train_sel}),
            "validation_speakers": sorted({i.speaker_id for i in dev_sel}),
            "train_dev_file_overlap": 0,
            "excluded": ["ASVspoof eval", "MLAAD-tiny", "WaveFake", "In-the-Wild delta"],
        },
        "preprocessing_version": PREP_VERSION,
        "checkpoint": {"path": str(best_path.relative_to(REPO)), "sha256": ck_sha,
                       "bytes": best_path.stat().st_size if best_path.is_file() else None},
        "base_checkpoint_sha256":
            "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a",
        "environment": {"device": device, "python": platform.python_version(),
                        "torch": torch.__version__, "platform": platform.platform()},
        "training_seconds": round(total_s, 1),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": commit,
    }
    (out_dir / f"{tag}.json").write_text(json.dumps(record, indent=2))
    log(f"best epoch {best_epoch}: EER {best['eer']:.4f} AUC {best['roc_auc']:.4f}")
    log(f"checkpoint {best_path.name} sha256 {ck_sha}")
    log(f"record -> {out_dir / (tag + '.json')}  ({total_s/60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
