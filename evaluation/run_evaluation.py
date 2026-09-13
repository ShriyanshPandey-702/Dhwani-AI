#!/usr/bin/env python3
"""
End-to-end AASIST evaluation: score → metrics → sweep → calibrate → report.

Discipline enforced here, not left to the operator:
  * the CALIBRATION split fits calibration and selects thresholds;
  * the TEST split is scored once and only reported;
  * a leakage audit runs before any number is produced;
  * every run writes metadata sufficient to reproduce it.

    python evaluation/run_evaluation.py --asvspoof-root data/external/LA
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.calibration.calibrate import (  # noqa: E402
    CALIBRATION_VERSION, IsotonicCalibrator, PlattCalibrator, evaluate_calibration, save,
)
from evaluation.datasets import asvspoof  # noqa: E402
from evaluation.datasets.base import (  # noqa: E402
    audit_split_disjointness, find_duplicate_paths, label_distribution,
    split_stats, validate_labels, write_manifest,
)
from evaluation.metrics.detection import (  # noqa: E402
    eer, find_threshold_for_far, metrics_at, summarise, threshold_sweep,
)
from evaluation.runners.score import (  # noqa: E402
    build_detector, last_timing, run_metadata, save_scores, score_samples,
)

SEED = 1337


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def as_arrays(scored) -> tuple:
    return (np.array([s.label for s in scored], dtype=int),
            np.array([s.score for s in scored], dtype=float))


def score_distribution(labels, scores) -> Dict:
    """Separate summaries per class — the basis of the separation judgement."""
    out = {}
    for name, value in (("bonafide", 0), ("spoof", 1)):
        subset = scores[labels == value]
        if subset.size == 0:
            out[name] = {"n": 0}
            continue
        out[name] = {
            "n": int(subset.size),
            "mean": float(np.mean(subset)),
            "std": float(np.std(subset)),
            "min": float(np.min(subset)),
            "max": float(np.max(subset)),
            "percentiles": {str(p): float(np.percentile(subset, p))
                            for p in (1, 5, 25, 50, 75, 95, 99)},
        }
    bona, spoof = scores[labels == 0], scores[labels == 1]
    if bona.size and spoof.size:
        # Overlap: fraction of each class falling inside the other's 5–95 range.
        lo, hi = np.percentile(spoof, 5), np.percentile(spoof, 95)
        out["bonafide_inside_spoof_p5_p95"] = float(np.mean((bona >= lo) & (bona <= hi)))
        lo, hi = np.percentile(bona, 5), np.percentile(bona, 95)
        out["spoof_inside_bonafide_p5_p95"] = float(np.mean((spoof >= lo) & (spoof <= hi)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asvspoof-root", required=True)
    ap.add_argument("--variant", default="AASIST-L")
    ap.add_argument("--calib-per-class", type=int, default=1000)
    ap.add_argument("--test-per-class", type=int, default=1500)
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    random.seed(SEED)
    np.random.seed(SEED)

    tag = args.tag or time.strftime("run_%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"results → {out_dir}")

    # ── Load official splits ─────────────────────────────────────────────────
    log("loading ASVspoof 2019 LA dev (calibration) and eval (test)")
    dev = asvspoof.load_split(args.asvspoof_root, "dev")
    ev = asvspoof.load_split(args.asvspoof_root, "eval")
    log(f"  dev  {len(dev):>6} files  {label_distribution(dev)}")
    log(f"  eval {len(ev):>6} files  {label_distribution(ev)}")
    validate_labels(dev)
    validate_labels(ev)

    # ── Leakage audit (mandatory, before any scoring) ────────────────────────
    log("auditing split disjointness")
    audit = audit_split_disjointness(dev + ev, ["dev", "eval"])
    dupes_dev = find_duplicate_paths(dev)
    dupes_eval = find_duplicate_paths(ev)
    audit["duplicate_paths_dev"] = len(dupes_dev)
    audit["duplicate_paths_eval"] = len(dupes_eval)
    audit["stats"] = {"dev": split_stats(dev, "dev").to_dict(),
                      "eval": split_stats(ev, "eval").to_dict()}
    (out_dir / "leakage_audit.json").write_text(json.dumps(audit, indent=2))
    log(f"  file overlap dev|eval = {audit['file_overlap']['dev|eval']}"
        f"  speaker overlap = {len(audit['speaker_overlap']['dev|eval'])}"
        f"  system overlap = {audit['system_overlap']['dev|eval']}")
    if not audit["clean"]:
        raise SystemExit("ABORT: split leakage detected")

    # ── Stratified subsets (documented, never presented as full splits) ──────
    calib = asvspoof.stratified_subset(dev, args.calib_per_class, seed=SEED)
    test = asvspoof.stratified_subset(ev, args.test_per_class, seed=SEED + 1)
    log(f"  calibration subset {len(calib)} files {label_distribution(calib)}")
    log(f"  test subset        {len(test)} files {label_distribution(test)}")
    write_manifest(calib, out_dir / "manifest_calibration.csv")
    write_manifest(test, out_dir / "manifest_test.csv")

    subset_audit = audit_split_disjointness(calib + test, ["dev", "eval"])
    (out_dir / "subset_audit.json").write_text(json.dumps(subset_audit, indent=2))

    # ── Score with the REAL model ────────────────────────────────────────────
    detector = build_detector(variant=args.variant, cascade=False)
    log(f"real model loaded: {detector.variant} on {detector._device}")

    log("scoring calibration subset")
    calib_scored = score_samples(calib, detector, batch_size=8,
                                 on_progress=lambda i, n: log(f"  calib {i}/{n}"))
    calib_timing = last_timing()
    save_scores(calib_scored, out_dir / "scores_calibration.csv")

    log("scoring test subset")
    test_scored = score_samples(test, detector, batch_size=8,
                                on_progress=lambda i, n: log(f"  test {i}/{n}"))
    test_timing = last_timing()
    save_scores(test_scored, out_dir / "scores_test.csv")

    y_cal, s_cal = as_arrays(calib_scored)
    y_test, s_test = as_arrays(test_scored)

    # ── Threshold selection on CALIBRATION ONLY ──────────────────────────────
    log("threshold sweep on the calibration split")
    eer_cal, eer_threshold = eer(y_cal, s_cal)
    sweep = threshold_sweep(y_cal, s_cal)
    balanced = max(sweep, key=lambda m: m.balanced_accuracy)
    sec_1, sec_1_m = find_threshold_for_far(y_cal, s_cal, 0.01)
    sec_5, sec_5_m = find_threshold_for_far(y_cal, s_cal, 0.05)

    selection = {
        "fitted_on": "asvspoof2019la dev subset (calibration)",
        "eer": {"value": eer_cal, "threshold": eer_threshold},
        "balanced": balanced.to_dict(),
        "security_far_1pct": {"threshold": sec_1, **sec_1_m.to_dict()},
        "security_far_5pct": {"threshold": sec_5, **sec_5_m.to_dict()},
        "sweep": [m.to_dict() for m in sweep],
    }
    (out_dir / "threshold_sweep_calibration.json").write_text(json.dumps(selection, indent=2))
    log(f"  EER {eer_cal:.4f} @ {eer_threshold:.4f} | "
        f"FAR≤1% @ {sec_1:.3f} (FRR {sec_1_m.frr:.4f}) | "
        f"FAR≤5% @ {sec_5:.3f} (FRR {sec_5_m.frr:.4f})")

    # ── Calibration, fitted on CALIBRATION, evaluated on TEST ───────────────
    log("fitting calibrators on the calibration split")
    platt = PlattCalibrator().fit(s_cal, y_cal)
    iso = IsotonicCalibrator().fit(s_cal, y_cal)
    save(platt, out_dir / "calibrator_platt.json")
    save(iso, out_dir / "calibrator_isotonic.json")

    calibration_report = {
        "version": CALIBRATION_VERSION,
        "fitted_on": "calibration split only",
        "evaluated_on": "held-out test split",
        "platt": evaluate_calibration(y_test, s_test, platt.predict(s_test)),
        "isotonic": evaluate_calibration(y_test, s_test, iso.predict(s_test)),
        "platt_params": platt.to_dict(),
    }
    (out_dir / "calibration.json").write_text(json.dumps(calibration_report, indent=2))
    log(f"  Platt    Brier {calibration_report['platt']['brier_raw']:.4f}"
        f" → {calibration_report['platt']['brier_calibrated']:.4f}"
        f" | ECE {calibration_report['platt']['ece_raw']:.4f}"
        f" → {calibration_report['platt']['ece_calibrated']:.4f}")
    log(f"  Isotonic Brier {calibration_report['isotonic']['brier_raw']:.4f}"
        f" → {calibration_report['isotonic']['brier_calibrated']:.4f}"
        f" | ECE {calibration_report['isotonic']['ece_raw']:.4f}"
        f" → {calibration_report['isotonic']['ece_calibrated']:.4f}")

    # ── Report on TEST using thresholds chosen on CALIBRATION ───────────────
    log("evaluating the test split at calibration-selected thresholds")
    results = {
        "calibration_split": {
            "summary_at_eer_threshold": summarise(y_cal, s_cal, eer_threshold),
            "distribution": score_distribution(y_cal, s_cal),
            "timing": calib_timing,
        },
        "test_split": {
            "summary_at_eer_threshold": summarise(y_test, s_test, eer_threshold),
            "summary_at_far1_threshold": summarise(y_test, s_test, sec_1),
            "summary_at_far5_threshold": summarise(y_test, s_test, sec_5),
            "own_eer_reference_only": dict(zip(("eer", "threshold"), eer(y_test, s_test))),
            "distribution": score_distribution(y_test, s_test),
            "timing": test_timing,
        },
        "per_system_test": {},
    }

    # Per-attack breakdown: which generators evade this model.
    for system in sorted({s.system_id for s in test_scored if s.system_id}):
        idx = [i for i, s in enumerate(test_scored)
               if s.system_id == system or s.label == 0]
        yy = y_test[idx]
        ss = s_test[idx]
        if len(set(yy.tolist())) < 2:
            continue
        results["per_system_test"][system] = summarise(yy, ss, sec_1)

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=float))

    meta = run_metadata(detector, extra={
        "run_tag": tag,
        "seed": SEED,
        "dataset": "asvspoof2019la",
        "asvspoof_root": str(args.asvspoof_root),
        "subset": {
            "method": "stratified: bona fide uniform; spoof spread evenly over system_id",
            "calibration_per_class": args.calib_per_class,
            "test_per_class": args.test_per_class,
            "note": "subset results are NOT full-split benchmarks",
        },
        "split_roles": {"calibration": "dev", "test": "eval"},
        "cascade_disabled_for_evaluation": True,
        "calibration_version": CALIBRATION_VERSION,
    })
    (out_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2, default=str))

    t = results["test_split"]["summary_at_far1_threshold"]
    log("── TEST (eval split, threshold chosen on dev) ──")
    log(f"  ROC-AUC {t['roc_auc']:.4f}  EER(test, reference) "
        f"{results['test_split']['own_eer_reference_only']['eer']:.4f}")
    log(f"  at FAR≤1% threshold {sec_1:.3f}: FAR {t['far']:.4f}  FRR {t['frr']:.4f}")
    log(f"done → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
