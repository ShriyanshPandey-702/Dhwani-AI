#!/usr/bin/env python3
"""
Evaluate a Phase 1 checkpoint on the FROZEN test sets — α, β, γ, δ.

Comparability is the whole point, so this re-scores the *identical* files the
frozen baseline used, read straight from the committed manifests, with the same
metric code and the same preprocessing. Nothing is re-sampled and no threshold
is re-fitted here.

  α  ASVspoof 2019 LA eval        evaluation/results/asvspoof_official/manifest_test.csv
  β  MLAAD-tiny subset            evaluation/results/mlaad_ood/manifest_test.csv
  γ  WaveFake subset              evaluation/results/wavefake_ood/manifest_test.csv
  δ  In-the-Wild (SEALED)         evaluation/results/inthewild_delta_baseline/manifest_test.csv

δ is opened under its sealed protocol: measured once, never used to tune. This
script cannot select a checkpoint — it only reports.

    python training/eval_checkpoint.py --checkpoint <path> --tag <name>
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "api"))

from app.ml.authenticity.aasist import MODEL_CONFIGS, NB_SAMP  # noqa: E402
from app.ml.authenticity.vendor.aasist_model import Model  # noqa: E402
from evaluation.metrics.detection import eer, metrics_at, summarise  # noqa: E402
from training.data import fit_length, read_audio  # noqa: E402

TEST_SETS = {
    "alpha_asvspoof_eval": "evaluation/results/asvspoof_official/manifest_test.csv",
    "beta_mlaad_tiny": "evaluation/results/mlaad_ood/manifest_test.csv",
    "gamma_wavefake": "evaluation/results/wavefake_ood/manifest_test.csv",
    "delta_in_the_wild": "evaluation/results/inthewild_delta_baseline/manifest_test.csv",
}

# Thresholds fixed on validation only — never re-fitted on any test set.
IMPORTED = {
    "asvspoof_dev_eer": 0.9545068144798277,
    "asvspoof_dev_far1": 0.975,
    "asvspoof_dev_far5": 0.999,
}


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


@torch.no_grad()
def score_manifest(model, device, manifest: Path, batch_size: int = 8):
    rows = list(csv.DictReader(open(manifest)))
    scores, labels = [], []
    buf, blab = [], []

    def flush():
        if not buf:
            return
        x = torch.from_numpy(np.stack(buf)).to(device)
        p = torch.softmax(model(x)[1], dim=1)[:, 1]      # P(bona fide)
        scores.extend((1.0 - p).cpu().numpy().tolist())  # spoof probability
        labels.extend(blab)
        buf.clear(); blab.clear()

    for r in rows:
        a = read_audio(r["audio_path"])
        if a is None:
            continue
        buf.append(fit_length(a, NB_SAMP))
        blab.append(int(r["label"]))
        if len(buf) == batch_size:
            flush()
    flush()
    return np.array(labels, int), np.array(scores, float)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--device", default="cpu",
                    help="cpu keeps parity with the frozen baseline protocol")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--sets", default="all")
    args = ap.parse_args()

    ck = Path(args.checkpoint)
    model = Model(MODEL_CONFIGS["AASIST-L"])
    model.load_state_dict(torch.load(ck, map_location="cpu"), strict=True)
    model.to(args.device).eval()
    log(f"{args.tag}: loaded {ck.name} sha256 {sha256_of(ck)[:16]}… on {args.device}")

    wanted = list(TEST_SETS) if args.sets == "all" else args.sets.split(",")
    out = {"model_version": args.tag,
           "checkpoint": str(ck), "checkpoint_sha256": sha256_of(ck),
           "device": args.device, "imported_thresholds": IMPORTED,
           "protocol": ("frozen manifests re-scored; no threshold or calibrator "
                        "fitted on any test set; delta opened under its seal"),
           "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "results": {}}

    for name in wanted:
        man = REPO / TEST_SETS[name]
        t0 = time.perf_counter()
        y, s = score_manifest(model, args.device, man, args.batch_size)
        own_eer, own_thr = eer(y, s)
        entry = {
            "manifest": TEST_SETS[name], "n": int(y.size),
            "n_bonafide": int((y == 0).sum()), "n_spoof": int((y == 1).sum()),
            "own_eer_reference_only": {"eer": float(own_eer), "threshold": float(own_thr)},
            "at_own_eer_threshold": summarise(y, s, own_thr),
            "score_distribution": {
                "bonafide": {"mean": float(s[y == 0].mean()),
                             "median": float(np.median(s[y == 0])),
                             "std": float(s[y == 0].std())},
                "spoof": {"mean": float(s[y == 1].mean()),
                          "median": float(np.median(s[y == 1])),
                          "std": float(s[y == 1].std())},
            },
            "seconds": round(time.perf_counter() - t0, 1),
        }
        for k, thr in IMPORTED.items():
            entry[f"at_{k}"] = summarise(y, s, thr)
        out["results"][name] = entry
        m = entry["at_own_eer_threshold"]
        log(f"  {name:<22} n={y.size:5d} AUC {m['roc_auc']:.4f} EER {own_eer:.4f} "
            f"FAR {m['far']:.4f} FRR {m['frr']:.4f}  ({entry['seconds']:.0f}s)")

    dest = REPO / args.out / f"phase1_{args.tag}.json"
    dest.write_text(json.dumps(out, indent=2, default=float))
    log(f"-> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
