#!/usr/bin/env python3
"""
Robustness of the REAL AASIST detector under controlled audio degradation.

Scores the same balanced subset under every condition and reports the change
relative to clean. Conditions are synthetic approximations — see
docs/ml_evaluation.md for what that does and does not license you to claim.

    python evaluation/run_robustness.py --asvspoof-root data/external/LA
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.datasets import asvspoof  # noqa: E402
from evaluation.datasets.base import label_distribution, write_manifest  # noqa: E402
from evaluation.metrics.detection import eer, metrics_at, roc_auc  # noqa: E402
from evaluation.robustness.transforms import CONDITIONS  # noqa: E402
from evaluation.runners.score import (  # noqa: E402
    build_detector, run_metadata, save_scores, score_samples,
)

SEED = 1337


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asvspoof-root", required=True)
    ap.add_argument("--variant", default="AASIST-L")
    ap.add_argument("--per-class", type=int, default=250)
    ap.add_argument("--split", default="eval")
    ap.add_argument("--threshold", type=float, default=None,
                    help="operating threshold; defaults to the clean EER threshold")
    ap.add_argument("--conditions", default=None, help="comma-separated subset")
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    tag = args.tag or time.strftime("robustness_%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = asvspoof.stratified_subset(
        asvspoof.load_split(args.asvspoof_root, args.split), args.per_class, seed=SEED)
    log(f"subset {len(samples)} files {label_distribution(samples)} from {args.split}")
    write_manifest(samples, out_dir / "manifest_robustness.csv")

    detector = build_detector(variant=args.variant, cascade=False)
    log(f"real model: {detector.variant} on {detector._device}")

    names = ([c.strip() for c in args.conditions.split(",")]
             if args.conditions else list(CONDITIONS))
    if "clean" in names:
        names.remove("clean")
    names.insert(0, "clean")

    rows, per_condition = [], {}
    baseline = None

    for name in names:
        started = time.perf_counter()
        scored = score_samples(samples, detector, condition=name, seed=SEED, batch_size=8)
        y = np.array([s.label for s in scored], dtype=int)
        s = np.array([s.score for s in scored], dtype=float)
        save_scores(scored, out_dir / f"scores_{name}.csv")

        auc = roc_auc(y, s)
        e, e_threshold = eer(y, s)
        threshold = args.threshold if args.threshold is not None else (
            baseline["eer_threshold"] if baseline else e_threshold)
        m = metrics_at(y, s, threshold)

        row = {
            "condition": name, "n": int(y.size),
            "roc_auc": auc, "eer": e, "eer_threshold": e_threshold,
            "operating_threshold": float(threshold),
            "far": m.far, "frr": m.frr,
            "mean_score_bonafide": float(np.mean(s[y == 0])) if np.any(y == 0) else None,
            "mean_score_spoof": float(np.mean(s[y == 1])) if np.any(y == 1) else None,
            "seconds": round(time.perf_counter() - started, 1),
        }
        if baseline is None:
            baseline = row
            row["delta_auc"] = 0.0
            row["delta_eer"] = 0.0
        else:
            row["delta_auc"] = auc - baseline["roc_auc"]
            row["delta_eer"] = e - baseline["eer"]

        rows.append(row)
        per_condition[name] = row
        log(f"  {name:<20} AUC {auc:.4f} ({row['delta_auc']:+.4f})  "
            f"EER {e:.4f} ({row['delta_eer']:+.4f})  "
            f"FAR {m.far:.4f}  FRR {m.frr:.4f}  [{row['seconds']}s]")

    (out_dir / "robustness.json").write_text(json.dumps({
        "operating_threshold_policy":
            "clean EER threshold applied to every condition unless overridden",
        "rows": rows,
    }, indent=2, default=float))

    meta = run_metadata(detector, extra={
        "run_tag": tag, "seed": SEED, "dataset": "asvspoof2019la",
        "split": args.split, "per_class": args.per_class,
        "conditions": names,
        "caveat": "synthetic degradations; not field validation",
    })
    (out_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    log(f"done → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
