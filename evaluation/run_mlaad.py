#!/usr/bin/env python3
"""
Out-of-domain evaluation on MLAAD-tiny with GENERATOR-DISJOINT splits.

Protocol
--------
The 32 TTS systems present locally are partitioned into two disjoint groups.
Bona-fide files are partitioned disjointly by file. Thresholds and calibration
are fitted on the CALIBRATION group only; the TEST group contains generators
the threshold has never seen.

This is the unseen-generator question that matters for deployment: an
anti-spoofing model trained in 2021 on ASVspoof 2019 meets a 2025 TTS system it
has never encountered. Reporting on generators used to pick the threshold would
answer a much easier question.

    python evaluation/run_mlaad.py --root data/external/MLAAD-tiny
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.calibration.calibrate import (  # noqa: E402
    CALIBRATION_VERSION, IsotonicCalibrator, PlattCalibrator, evaluate_calibration, save,
)
from evaluation.datasets import mlaad  # noqa: E402
from evaluation.datasets.base import (  # noqa: E402
    BONAFIDE, SPOOF, audit_split_disjointness, find_duplicate_paths,
    label_distribution, validate_labels, write_manifest,
)
from evaluation.metrics.detection import (  # noqa: E402
    eer, find_threshold_for_far, summarise, threshold_sweep,
)
from evaluation.runners.score import (  # noqa: E402
    build_detector, last_timing, run_metadata, save_scores, score_samples,
)

SEED = 1337


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
    ap.add_argument("--spoof-per-split", type=int, default=200)
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    rng = random.Random(SEED)
    tag = args.tag or time.strftime("mlaad_%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    samples = mlaad.load(args.root, split="all")
    bona = [s for s in samples if s.label == BONAFIDE]
    spoof = [s for s in samples if s.label == SPOOF]
    log(f"local MLAAD-tiny: {len(bona)} bona fide, {len(spoof)} spoof")

    # ── Generator-disjoint partition ─────────────────────────────────────────
    systems = sorted({f"{s.language}/{s.system_id}" for s in spoof})
    rng.shuffle(systems)
    half = len(systems) // 2
    calib_systems, test_systems = set(systems[:half]), set(systems[half:])
    log(f"{len(systems)} systems → {len(calib_systems)} calibration / {len(test_systems)} test")

    def pick_spoof(system_set, n):
        pool = [s for s in spoof if f"{s.language}/{s.system_id}" in system_set]
        by_sys = {}
        for s in pool:
            by_sys.setdefault(s.system_id, []).append(s)
        per = max(1, n // max(1, len(by_sys)))
        out = []
        for sys_id in sorted(by_sys):
            out += rng.sample(by_sys[sys_id], min(per, len(by_sys[sys_id])))
        return out[:n]

    rng.shuffle(bona)
    mid = len(bona) // 2
    calib_bona, test_bona = bona[:mid], bona[mid:]

    calib = calib_bona + pick_spoof(calib_systems, args.spoof_per_split)
    test = test_bona + pick_spoof(test_systems, args.spoof_per_split)
    for s in calib:
        s.split = "calib"
    for s in test:
        s.split = "test"

    validate_labels(calib)
    validate_labels(test)
    log(f"calibration {len(calib)} {label_distribution(calib)}")
    log(f"test        {len(test)} {label_distribution(test)}")

    # ── Leakage audit ────────────────────────────────────────────────────────
    audit = audit_split_disjointness(calib + test, ["calib", "test"])
    audit["calibration_systems"] = sorted(calib_systems)
    audit["test_systems"] = sorted(test_systems)
    audit["system_groups_disjoint"] = not (calib_systems & test_systems)
    audit["duplicate_paths"] = len(find_duplicate_paths(calib + test))
    (out_dir / "leakage_audit.json").write_text(json.dumps(audit, indent=2))
    log(f"leakage: file overlap={audit['file_overlap']['calib|test']} "
        f"system-group disjoint={audit['system_groups_disjoint']} "
        f"duplicate paths={audit['duplicate_paths']}")
    if not audit["clean"] or not audit["system_groups_disjoint"]:
        raise SystemExit("ABORT: leakage detected")

    write_manifest(calib, out_dir / "manifest_calibration.csv")
    write_manifest(test, out_dir / "manifest_test.csv")

    # ── Score with the REAL model ────────────────────────────────────────────
    detector = build_detector(variant=args.variant, cascade=False)
    log(f"real model: {detector.variant} on {detector._device}")

    calib_scored = score_samples(calib, detector, batch_size=8)
    calib_timing = last_timing()
    save_scores(calib_scored, out_dir / "scores_calibration.csv")
    log(f"scored calibration in {calib_timing['seconds']:.0f}s "
        f"({calib_timing['per_file_ms']:.0f} ms/file)")

    test_scored = score_samples(test, detector, batch_size=8)
    test_timing = last_timing()
    save_scores(test_scored, out_dir / "scores_test.csv")
    log(f"scored test in {test_timing['seconds']:.0f}s")

    y_cal, s_cal = arrays(calib_scored)
    y_test, s_test = arrays(test_scored)

    # ── Thresholds from CALIBRATION only ─────────────────────────────────────
    eer_cal, eer_threshold = eer(y_cal, s_cal)
    sweep = threshold_sweep(y_cal, s_cal)
    balanced = max(sweep, key=lambda m: m.balanced_accuracy)
    far1_t, far1_m = find_threshold_for_far(y_cal, s_cal, 0.01)
    far5_t, far5_m = find_threshold_for_far(y_cal, s_cal, 0.05)
    log(f"calibration EER {eer_cal:.4f} @ {eer_threshold:.4f} | "
        f"FAR≤1% @ {far1_t:.3f} (FRR {far1_m.frr:.4f}) | "
        f"FAR≤5% @ {far5_t:.3f} (FRR {far5_m.frr:.4f})")
    (out_dir / "threshold_sweep_calibration.json").write_text(json.dumps({
        "eer": {"value": eer_cal, "threshold": eer_threshold},
        "balanced": balanced.to_dict(),
        "security_far_1pct": {"threshold": far1_t, **far1_m.to_dict()},
        "security_far_5pct": {"threshold": far5_t, **far5_m.to_dict()},
        "sweep": [m.to_dict() for m in sweep],
    }, indent=2, default=float))

    # ── Calibration fitted on calib, evaluated on test ───────────────────────
    platt = PlattCalibrator().fit(s_cal, y_cal)
    iso = IsotonicCalibrator().fit(s_cal, y_cal)
    save(platt, out_dir / "calibrator_platt.json")
    save(iso, out_dir / "calibrator_isotonic.json")
    calibration = {
        "version": CALIBRATION_VERSION,
        "fitted_on": "calibration systems only",
        "evaluated_on": "held-out unseen generators",
        "platt": evaluate_calibration(y_test, s_test, platt.predict(s_test)),
        "isotonic": evaluate_calibration(y_test, s_test, iso.predict(s_test)),
        "platt_params": platt.to_dict(),
    }
    (out_dir / "calibration.json").write_text(json.dumps(calibration, indent=2, default=float))
    log(f"Platt    Brier {calibration['platt']['brier_raw']:.4f}→"
        f"{calibration['platt']['brier_calibrated']:.4f}  "
        f"ECE {calibration['platt']['ece_raw']:.4f}→{calibration['platt']['ece_calibrated']:.4f}")
    log(f"Isotonic Brier {calibration['isotonic']['brier_raw']:.4f}→"
        f"{calibration['isotonic']['brier_calibrated']:.4f}  "
        f"ECE {calibration['isotonic']['ece_raw']:.4f}→"
        f"{calibration['isotonic']['ece_calibrated']:.4f}")

    # ── Report on the unseen generators ──────────────────────────────────────
    results = {
        "protocol": "generator-disjoint; thresholds fitted on calibration systems only",
        "calibration": {"summary_at_eer": summarise(y_cal, s_cal, eer_threshold),
                        "distribution": distribution(y_cal, s_cal),
                        "timing": calib_timing},
        "test_unseen_generators": {
            "summary_at_eer_threshold": summarise(y_test, s_test, eer_threshold),
            "summary_at_far1_threshold": summarise(y_test, s_test, far1_t),
            "summary_at_far5_threshold": summarise(y_test, s_test, far5_t),
            "own_eer_reference_only": dict(zip(("eer", "threshold"), eer(y_test, s_test))),
            "distribution": distribution(y_test, s_test),
            "timing": test_timing,
        },
        "per_system": {},
    }
    for system in sorted({s.system_id for s in test_scored if s.system_id}):
        idx = [i for i, s in enumerate(test_scored) if s.system_id == system or s.label == BONAFIDE]
        yy, ss = y_test[idx], s_test[idx]
        if len(set(yy.tolist())) < 2:
            continue
        results["per_system"][system] = summarise(yy, ss, far1_t)

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=float))
    (out_dir / "run_metadata.json").write_text(json.dumps(run_metadata(detector, extra={
        "run_tag": tag, "seed": SEED, "dataset": "mlaad_tiny",
        "protocol": "generator-disjoint calibration/test",
        "subset_note": "locally available portion of MLAAD-tiny; not the full dataset",
        "spoof_per_split": args.spoof_per_split,
        "calibration_version": CALIBRATION_VERSION,
        "cascade_disabled_for_evaluation": True,
    }), indent=2, default=str))

    t = results["test_unseen_generators"]
    log("── TEST on UNSEEN generators ──")
    log(f"  ROC-AUC {t['summary_at_eer_threshold']['roc_auc']:.4f}  "
        f"own EER {t['own_eer_reference_only']['eer']:.4f}")
    log(f"  at calibration EER threshold: FAR {t['summary_at_eer_threshold']['far']:.4f}  "
        f"FRR {t['summary_at_eer_threshold']['frr']:.4f}")
    log(f"  at FAR≤1% threshold:          FAR {t['summary_at_far1_threshold']['far']:.4f}  "
        f"FRR {t['summary_at_far1_threshold']['frr']:.4f}")
    log(f"done → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
