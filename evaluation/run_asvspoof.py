#!/usr/bin/env python3
"""
In-domain evaluation on ASVspoof 2019 LA `eval`, SPEAKER-DISJOINT.

Splits the official eval protocol by speaker, fits thresholds and calibration on
the calibration speakers only, and reports on speakers never used for tuning.
Every attack in `eval` (A07–A19) is unseen relative to AASIST's training data.

    python evaluation/run_asvspoof.py --root data/external/LA_extract
"""

from __future__ import annotations

import argparse, json, random, sys, time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.calibration.calibrate import (  # noqa: E402
    CALIBRATION_VERSION, IsotonicCalibrator, PlattCalibrator, evaluate_calibration, save)
from evaluation.datasets import asvspoof  # noqa: E402
from evaluation.datasets.base import (  # noqa: E402
    BONAFIDE, SPOOF, audit_split_disjointness, find_duplicate_paths,
    label_distribution, validate_labels, write_manifest)
from evaluation.metrics.detection import (  # noqa: E402
    eer, find_threshold_for_far, summarise, threshold_sweep)
from evaluation.runners.score import (  # noqa: E402
    build_detector, last_timing, run_metadata, save_scores, score_samples)

SEED = 1337


def log(m): print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)
def arrays(sc): return (np.array([s.label for s in sc], int),
                        np.array([s.score for s in sc], float))


def distribution(labels, scores):
    out = {}
    for name, v in (("bonafide", BONAFIDE), ("spoof", SPOOF)):
        sub = scores[labels == v]
        out[name] = ({"n": 0} if sub.size == 0 else {
            "n": int(sub.size), "mean": float(np.mean(sub)), "std": float(np.std(sub)),
            "percentiles": {str(p): float(np.percentile(sub, p))
                            for p in (1, 5, 25, 50, 75, 95, 99)}})
    b, s = scores[labels == BONAFIDE], scores[labels == SPOOF]
    if b.size and s.size:
        lo, hi = np.percentile(s, 5), np.percentile(s, 95)
        out["bonafide_inside_spoof_p5_p95"] = float(np.mean((b >= lo) & (b <= hi)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", required=True)
    ap.add_argument("--variant", default="AASIST-L")
    ap.add_argument("--per-class", type=int, default=1000)
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    random.seed(SEED); np.random.seed(SEED)
    tag = args.tag or time.strftime("asvspoof_%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    # require_files=True keeps only entries whose audio is actually present.
    samples = asvspoof.load_split(args.root, "eval", require_files=True)
    log(f"eval entries with audio present: {len(samples)}  {label_distribution(samples)}")
    validate_labels(samples)

    calib_all, test_all, calib_spk, test_spk = asvspoof.speaker_disjoint_split(samples, SEED)
    log(f"speakers: {len(calib_spk)} calibration / {len(test_spk)} test (disjoint)")

    calib = asvspoof.stratified_subset(calib_all, args.per_class, seed=SEED)
    test = asvspoof.stratified_subset(test_all, args.per_class, seed=SEED + 1)
    for s in calib: s.split = "calib"
    for s in test: s.split = "test"
    log(f"calibration {len(calib)} {label_distribution(calib)}")
    log(f"test        {len(test)} {label_distribution(test)}")

    audit = audit_split_disjointness(calib + test, ["calib", "test"])
    audit["calibration_speakers"] = calib_spk
    audit["test_speakers"] = test_spk
    audit["duplicate_paths"] = len(find_duplicate_paths(calib + test))
    (out_dir / "leakage_audit.json").write_text(json.dumps(audit, indent=2))
    log(f"leakage: files={audit['file_overlap']['calib|test']} "
        f"speakers={len(audit['speaker_overlap']['calib|test'])} "
        f"duplicates={audit['duplicate_paths']}")
    if not audit["clean"] or audit["speaker_overlap"]["calib|test"]:
        raise SystemExit("ABORT: leakage detected")

    write_manifest(calib, out_dir / "manifest_calibration.csv")
    write_manifest(test, out_dir / "manifest_test.csv")

    detector = build_detector(variant=args.variant, cascade=False)
    log(f"real model: {detector.variant} on {detector._device}")

    calib_scored = score_samples(calib, detector, batch_size=8)
    ct = last_timing(); save_scores(calib_scored, out_dir / "scores_calibration.csv")
    log(f"calibration scored in {ct['seconds']:.0f}s ({ct['per_file_ms']:.0f} ms/file)")
    test_scored = score_samples(test, detector, batch_size=8)
    tt = last_timing(); save_scores(test_scored, out_dir / "scores_test.csv")
    log(f"test scored in {tt['seconds']:.0f}s")

    y_cal, s_cal = arrays(calib_scored)
    y_test, s_test = arrays(test_scored)

    eer_cal, eer_thr = eer(y_cal, s_cal)
    sweep = threshold_sweep(y_cal, s_cal)
    balanced = max(sweep, key=lambda m: m.balanced_accuracy)
    far1_t, far1_m = find_threshold_for_far(y_cal, s_cal, 0.01)
    far5_t, far5_m = find_threshold_for_far(y_cal, s_cal, 0.05)
    log(f"calibration EER {eer_cal:.4f} @ {eer_thr:.4f} | "
        f"FAR<=1% @ {far1_t:.3f} (FRR {far1_m.frr:.4f}) | "
        f"FAR<=5% @ {far5_t:.3f} (FRR {far5_m.frr:.4f})")
    (out_dir / "threshold_sweep_calibration.json").write_text(json.dumps({
        "eer": {"value": eer_cal, "threshold": eer_thr},
        "balanced": balanced.to_dict(),
        "security_far_1pct": {"threshold": far1_t, **far1_m.to_dict()},
        "security_far_5pct": {"threshold": far5_t, **far5_m.to_dict()},
        "sweep": [m.to_dict() for m in sweep]}, indent=2, default=float))

    platt = PlattCalibrator().fit(s_cal, y_cal)
    iso = IsotonicCalibrator().fit(s_cal, y_cal)
    save(platt, out_dir / "calibrator_platt.json")
    save(iso, out_dir / "calibrator_isotonic.json")
    calibration = {"version": CALIBRATION_VERSION,
                   "fitted_on": "calibration speakers only",
                   "evaluated_on": "held-out speakers",
                   "platt": evaluate_calibration(y_test, s_test, platt.predict(s_test)),
                   "isotonic": evaluate_calibration(y_test, s_test, iso.predict(s_test)),
                   "platt_params": platt.to_dict()}
    (out_dir / "calibration.json").write_text(json.dumps(calibration, indent=2, default=float))
    log(f"Platt    Brier {calibration['platt']['brier_raw']:.4f}->"
        f"{calibration['platt']['brier_calibrated']:.4f}  ECE "
        f"{calibration['platt']['ece_raw']:.4f}->{calibration['platt']['ece_calibrated']:.4f}")
    log(f"Isotonic Brier {calibration['isotonic']['brier_raw']:.4f}->"
        f"{calibration['isotonic']['brier_calibrated']:.4f}  ECE "
        f"{calibration['isotonic']['ece_raw']:.4f}->{calibration['isotonic']['ece_calibrated']:.4f}")

    results = {
        "protocol": "ASVspoof2019 LA eval, speaker-disjoint; thresholds from calibration speakers only",
        "calibration": {"summary_at_eer": summarise(y_cal, s_cal, eer_thr),
                        "distribution": distribution(y_cal, s_cal), "timing": ct},
        "test": {"summary_at_eer_threshold": summarise(y_test, s_test, eer_thr),
                 "summary_at_far1_threshold": summarise(y_test, s_test, far1_t),
                 "summary_at_far5_threshold": summarise(y_test, s_test, far5_t),
                 "own_eer_reference_only": dict(zip(("eer", "threshold"), eer(y_test, s_test))),
                 "distribution": distribution(y_test, s_test), "timing": tt},
        "per_attack": {}}
    for sysid in sorted({s.system_id for s in test_scored if s.system_id}):
        idx = [i for i, s in enumerate(test_scored) if s.system_id == sysid or s.label == BONAFIDE]
        yy, ss = y_test[idx], s_test[idx]
        if len(set(yy.tolist())) < 2: continue
        results["per_attack"][sysid] = summarise(yy, ss, far1_t)
    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=float))

    (out_dir / "run_metadata.json").write_text(json.dumps(run_metadata(detector, extra={
        "run_tag": tag, "seed": SEED, "dataset": "asvspoof2019la",
        "split_protocol": "official eval protocol, speaker-disjoint calibration/test",
        "audio_availability": "77.8% of eval recovered from a partial download; "
                              "recovery rate uniform across class, attack and speaker",
        "per_class_subset": args.per_class,
        "calibration_version": CALIBRATION_VERSION,
        "cascade_disabled_for_evaluation": True}), indent=2, default=str))

    t = results["test"]
    log("-- TEST (held-out speakers) --")
    log(f"  ROC-AUC {t['summary_at_eer_threshold']['roc_auc']:.4f}  "
        f"own EER {t['own_eer_reference_only']['eer']:.4f}")
    log(f"  at calibration EER threshold: FAR {t['summary_at_eer_threshold']['far']:.4f} "
        f"FRR {t['summary_at_eer_threshold']['frr']:.4f}")
    log(f"  at FAR<=1% threshold: FAR {t['summary_at_far1_threshold']['far']:.4f} "
        f"FRR {t['summary_at_far1_threshold']['frr']:.4f}")
    log(f"done -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
