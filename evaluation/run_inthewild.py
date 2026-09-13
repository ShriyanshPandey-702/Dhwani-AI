#!/usr/bin/env python3
"""
TEST δ — frozen-baseline evaluation on the "In-the-Wild" corpus.

δ IS A SEALED TEST SET. This runner therefore differs from every other runner
in one deliberate way: **it fits nothing on δ.**

  * no calibration split is carved from δ
  * no threshold is selected on δ
  * no calibrator is fitted on δ

Operating thresholds are IMPORTED from the frozen ASVspoof 2019 LA *dev* sweep
(`evaluation/results/asvspoof_official/threshold_sweep_calibration.json`), i.e.
from a validation split that has never seen δ. δ's own EER is reported for
reference only and must never be used to select anything.

    python evaluation/run_inthewild.py --root data/external/InTheWild \
        --per-class 1500 --tag inthewild_delta_baseline
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.datasets import inthewild  # noqa: E402
from evaluation.datasets.base import (  # noqa: E402
    BONAFIDE, SPOOF, find_duplicate_paths, label_distribution, validate_labels,
    write_manifest,
)
from evaluation.metrics.detection import eer, summarise  # noqa: E402
from evaluation.runners.score import (  # noqa: E402
    build_detector, last_timing, run_metadata, save_scores, score_samples,
)

SEED = 1337
IMPORTED_SWEEP = "evaluation/results/asvspoof_official/threshold_sweep_calibration.json"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def arrays(scored):
    return (np.array([s.label for s in scored], int),
            np.array([s.score for s in scored], float))


def distribution(labels, scores):
    out = {}
    for name, v in (("bonafide", BONAFIDE), ("spoof", SPOOF)):
        sub = scores[labels == v]
        out[name] = ({"n": 0} if sub.size == 0 else {
            "n": int(sub.size), "mean": float(np.mean(sub)), "std": float(np.std(sub)),
            "percentiles": {str(p): float(np.percentile(sub, p))
                            for p in (1, 5, 25, 50, 75, 95, 99)}})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--variant", default="AASIST-L")
    ap.add_argument("--per-class", type=int, default=1500,
                    help="speaker-stratified subset size per class")
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default="inthewild_delta_baseline")
    args = ap.parse_args()

    rng = random.Random(SEED)
    out_dir = Path(args.out) / args.tag
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = inthewild.load(args.root)
    validate_labels(samples)
    bona = [s for s in samples if s.label == BONAFIDE]
    spoof = [s for s in samples if s.label == SPOOF]
    speakers = sorted({s.speaker_id for s in samples if s.speaker_id})
    log(f"corpus: {len(samples)} clips  {label_distribution(samples)}  "
        f"speakers={len(speakers)}")

    # ── Speaker-stratified subset, seeded and recorded ───────────────────────
    def stratify(pool, n):
        by_spk = collections.defaultdict(list)
        for s in pool:
            by_spk[s.speaker_id or "?"].append(s)
        for k in by_spk:
            rng.shuffle(by_spk[k])
        picked, keys = [], sorted(by_spk)
        i = 0
        while len(picked) < n and any(by_spk[k] for k in keys):
            k = keys[i % len(keys)]
            if by_spk[k]:
                picked.append(by_spk[k].pop())
            i += 1
        return picked[:n]

    test = stratify(bona, args.per_class) + stratify(spoof, args.per_class)
    for s in test:
        s.split = "test"
    validate_labels(test)
    log(f"δ test subset: {len(test)} {label_distribution(test)}  "
        f"speakers={len({s.speaker_id for s in test})}  "
        f"duplicate paths={len(find_duplicate_paths(test))}")
    write_manifest(test, out_dir / "manifest_test.csv")

    # ── Import thresholds from an EXTERNAL validation split ──────────────────
    sweep = json.loads((REPO_ROOT / IMPORTED_SWEEP).read_text())
    imported = {
        "asvspoof_dev_eer": float(sweep["eer"]["threshold"]),
        "asvspoof_dev_far1": float(sweep["security_far_1pct"]["threshold"]),
        "asvspoof_dev_far5": float(sweep["security_far_5pct"]["threshold"]),
    }
    log(f"imported thresholds (ASVspoof dev, never saw δ): {imported}")

    # ── Score with the frozen model ──────────────────────────────────────────
    detector = build_detector(variant=args.variant, cascade=False)
    log(f"frozen model: {detector.variant} on {detector._device}")
    scored = score_samples(test, detector, batch_size=8)
    timing = last_timing()
    save_scores(scored, out_dir / "scores_test.csv")
    log(f"scored in {timing['seconds']:.0f}s ({timing['per_file_ms']:.0f} ms/file)")

    y, s = arrays(scored)
    own_eer, own_thr = eer(y, s)

    results = {
        "protocol": ("TEST delta — sealed unseen-domain corpus. Nothing is fitted "
                     "on delta: thresholds are imported from the frozen ASVspoof "
                     "2019 LA dev sweep. delta's own EER is reference only."),
        "dataset": {"name": "In-the-Wild", "licence": "CC-BY-SA-4.0",
                    "source": "huggingface.co/datasets/mueller91/In-The-Wild",
                    "generator_labels_available": False},
        "imported_thresholds": imported,
        "test": {
            "own_eer_reference_only": {"eer": own_eer, "threshold": own_thr},
            "summary_at_asvspoof_dev_eer": summarise(y, s, imported["asvspoof_dev_eer"]),
            "summary_at_asvspoof_dev_far1": summarise(y, s, imported["asvspoof_dev_far1"]),
            "summary_at_asvspoof_dev_far5": summarise(y, s, imported["asvspoof_dev_far5"]),
            "distribution": distribution(y, s),
            "timing": timing,
        },
        "per_speaker": {},
    }
    for spk in sorted({x.speaker_id for x in scored if x.speaker_id}):
        idx = [i for i, x in enumerate(scored) if x.speaker_id == spk]
        yy, ss = y[idx], s[idx]
        if len(set(yy.tolist())) < 2:
            continue
        results["per_speaker"][spk] = summarise(yy, ss, imported["asvspoof_dev_far1"])

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=float))
    (out_dir / "run_metadata.json").write_text(json.dumps(run_metadata(detector, extra={
        "run_tag": args.tag, "seed": SEED, "dataset": "in_the_wild",
        "role": "TEST delta (sealed)",
        "protocol": "no fitting on delta; thresholds imported from ASVspoof dev",
        "subset_note": f"speaker-stratified {args.per_class} per class, seed {SEED}",
        "cascade_disabled_for_evaluation": True,
    }), indent=2, default=str))

    t = results["test"]
    log("-- TEST delta (frozen AASIST-L baseline) --")
    log(f"  ROC-AUC {t['summary_at_asvspoof_dev_eer']['roc_auc']:.4f}  "
        f"own EER {own_eer:.4f} (reference only)")
    for k, lbl in (("summary_at_asvspoof_dev_eer", "dev EER thr"),
                   ("summary_at_asvspoof_dev_far1", "dev FAR<=1% thr"),
                   ("summary_at_asvspoof_dev_far5", "dev FAR<=5% thr")):
        m = t[k]
        log(f"  at {lbl:<16} thr={m['operating_threshold']:.4f} "
            f"FAR={m['far']:.4f} FRR={m['frr']:.4f} TPR={m['tpr']:.4f} TNR={m['tnr']:.4f}")
    d = t["distribution"]
    log(f"  bona fide mean {d['bonafide']['mean']:.3f} | spoof mean {d['spoof']['mean']:.3f}")
    log(f"done -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
