#!/usr/bin/env python3
"""
Out-of-domain evaluation on WaveFake with VOCODER-DISJOINT splits.

Protocol
--------
WaveFake ships spoof audio only: LJSpeech utterances resynthesised by seven
neural vocoders. The bona-fide half is the *original* LJSpeech recording of the
same utterance, which makes this an unusually clean control — same speaker,
same words, same recording chain; the only difference is the vocoder artifact.

Two disjointness axes are enforced simultaneously:

  * VOCODER-disjoint  calibration vocoders {melgan, parallel_wavegan, hifiGAN}
                      never appear in test {full_band_melgan, melgan_large,
                      multi_band_melgan, waveglow}
  * UTTERANCE-disjoint every LJSpeech utterance id is assigned to exactly one
                      side by SHA-256 parity, so no source recording is shared

This complements MLAAD (unseen *TTS systems*) by asking a different question:
does the detector generalise across unseen *vocoders* when content and speaker
are held constant? Failure here cannot be blamed on speaker or channel shift.

    python evaluation/run_wavefake.py --root data/external/WaveFake \
        --ljspeech data/external/LJSpeech-1.1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
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
from evaluation.datasets.base import (  # noqa: E402
    BONAFIDE, SPOOF, Sample, audit_split_disjointness, find_duplicate_paths,
    label_distribution, validate_labels, write_manifest,
)
from evaluation.metrics.detection import (  # noqa: E402
    eer, find_threshold_for_far, summarise, threshold_sweep,
)
from evaluation.runners.score import (  # noqa: E402
    build_detector, last_timing, run_metadata, save_scores, score_samples,
)

SEED = 1337
DATASET = "wavefake"
UTT = re.compile(r"(LJ\d{3}-\d{4})")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def side(utt: str) -> str:
    """Deterministic, generator-independent utterance split."""
    return "calib" if int(hashlib.sha256(utt.encode()).hexdigest(), 16) % 2 == 0 else "test"


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
    ap.add_argument("--root", required=True, help="WaveFake subset root (calib/ and test/)")
    ap.add_argument("--ljspeech", required=True, help="LJSpeech-1.1 root (contains wavs/)")
    ap.add_argument("--variant", default="AASIST-L")
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    rng = random.Random(SEED)
    tag = args.tag or time.strftime("wavefake_%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    root = Path(args.root)
    lj_wavs = Path(args.ljspeech) / "wavs"
    if not lj_wavs.is_dir():
        raise SystemExit(f"ABORT: LJSpeech wavs/ not found at {lj_wavs}")

    # ── Spoof: vocoder-disjoint by directory ─────────────────────────────────
    splits = {"calib": [], "test": []}
    vocoders = {"calib": set(), "test": set()}
    for role in ("calib", "test"):
        for gen_dir in sorted(p for p in (root / role).glob("*") if p.is_dir()):
            for wav in sorted(gen_dir.glob("*.wav")):
                utt = UTT.search(wav.name).group(1)
                if side(utt) != role:      # belt-and-braces; fetch already enforced this
                    continue
                splits[role].append(Sample(
                    audio_path=str(wav), label=SPOOF, dataset=DATASET, split=role,
                    speaker_id="LJ", attack_type="vocoder",
                    system_id=gen_dir.name, language="en"))
                vocoders[role].add(gen_dir.name)
    if vocoders["calib"] & vocoders["test"]:
        raise SystemExit(f"ABORT: vocoder overlap {vocoders['calib'] & vocoders['test']}")

    # ── Bona fide: original LJSpeech, same utterance-hash split ──────────────
    pool = {"calib": [], "test": []}
    for wav in sorted(lj_wavs.glob("*.wav")):
        m = UTT.search(wav.name)
        if m:
            pool[side(m.group(1))].append(wav)
    for role in ("calib", "test"):
        n = len(splits[role])
        chosen = rng.sample(pool[role], min(n, len(pool[role])))
        for wav in chosen:
            splits[role].append(Sample(
                audio_path=str(wav), label=BONAFIDE, dataset=DATASET, split=role,
                speaker_id="LJ", language="en"))

    calib, test = splits["calib"], splits["test"]
    validate_labels(calib)
    validate_labels(test)
    log(f"calibration vocoders {sorted(vocoders['calib'])}")
    log(f"test        vocoders {sorted(vocoders['test'])}")
    log(f"calibration {len(calib)} {label_distribution(calib)}")
    log(f"test        {len(test)} {label_distribution(test)}")

    # ── Leakage audit ────────────────────────────────────────────────────────
    utt_calib = {UTT.search(Path(s.audio_path).name).group(1) for s in calib}
    utt_test = {UTT.search(Path(s.audio_path).name).group(1) for s in test}
    audit = audit_split_disjointness(calib + test, ["calib", "test"])
    audit["calibration_vocoders"] = sorted(vocoders["calib"])
    audit["test_vocoders"] = sorted(vocoders["test"])
    audit["vocoder_groups_disjoint"] = not (vocoders["calib"] & vocoders["test"])
    audit["utterance_overlap"] = sorted(utt_calib & utt_test)
    audit["n_utterances"] = {"calib": len(utt_calib), "test": len(utt_test)}
    audit["duplicate_paths"] = len(find_duplicate_paths(calib + test))
    audit["speaker_note"] = ("LJSpeech is a single-speaker corpus; speaker-disjoint "
                             "splitting is impossible by construction and is not claimed.")
    (out_dir / "leakage_audit.json").write_text(json.dumps(audit, indent=2))
    log(f"leakage: files={audit['file_overlap']['calib|test']} "
        f"vocoder-disjoint={audit['vocoder_groups_disjoint']} "
        f"utterance overlap={len(audit['utterance_overlap'])} "
        f"duplicates={audit['duplicate_paths']}")
    if audit["utterance_overlap"] or not audit["vocoder_groups_disjoint"]:
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

    # ── Thresholds from CALIBRATION vocoders only ────────────────────────────
    eer_cal, eer_threshold = eer(y_cal, s_cal)
    sweep = threshold_sweep(y_cal, s_cal)
    far1_t, far1_m = find_threshold_for_far(y_cal, s_cal, 0.01)
    far5_t, far5_m = find_threshold_for_far(y_cal, s_cal, 0.05)
    log(f"calibration EER {eer_cal:.4f} @ {eer_threshold:.4f} | "
        f"FAR<=1% @ {far1_t:.3f} (FRR {far1_m.frr:.4f}) | "
        f"FAR<=5% @ {far5_t:.3f} (FRR {far5_m.frr:.4f})")
    (out_dir / "threshold_sweep_calibration.json").write_text(json.dumps({
        "eer": {"value": eer_cal, "threshold": eer_threshold},
        "security_far_1pct": {"threshold": far1_t, **far1_m.to_dict()},
        "security_far_5pct": {"threshold": far5_t, **far5_m.to_dict()},
        "sweep": [m.to_dict() for m in sweep],
    }, indent=2, default=float))

    # ── Calibration fitted on calib vocoders, evaluated on test vocoders ─────
    platt = PlattCalibrator().fit(s_cal, y_cal)
    iso = IsotonicCalibrator().fit(s_cal, y_cal)
    save(platt, out_dir / "calibrator_platt.json")
    save(iso, out_dir / "calibrator_isotonic.json")
    calibration = {
        "version": CALIBRATION_VERSION,
        "fitted_on": "calibration vocoders only",
        "evaluated_on": "held-out unseen vocoders",
        "platt": evaluate_calibration(y_test, s_test, platt.predict(s_test)),
        "isotonic": evaluate_calibration(y_test, s_test, iso.predict(s_test)),
        "platt_params": platt.to_dict(),
    }
    (out_dir / "calibration.json").write_text(json.dumps(calibration, indent=2, default=float))
    log(f"Platt    Brier {calibration['platt']['brier_raw']:.4f}->"
        f"{calibration['platt']['brier_calibrated']:.4f}  "
        f"ECE {calibration['platt']['ece_raw']:.4f}->{calibration['platt']['ece_calibrated']:.4f}")
    log(f"Isotonic Brier {calibration['isotonic']['brier_raw']:.4f}->"
        f"{calibration['isotonic']['brier_calibrated']:.4f}  "
        f"ECE {calibration['isotonic']['ece_raw']:.4f}->"
        f"{calibration['isotonic']['ece_calibrated']:.4f}")

    results = {
        "protocol": ("vocoder-disjoint and utterance-disjoint; thresholds and "
                     "calibration fitted on calibration vocoders only"),
        "calibration": {"summary_at_eer": summarise(y_cal, s_cal, eer_threshold),
                        "distribution": distribution(y_cal, s_cal),
                        "timing": calib_timing},
        "test_unseen_vocoders": {
            "summary_at_eer_threshold": summarise(y_test, s_test, eer_threshold),
            "summary_at_far1_threshold": summarise(y_test, s_test, far1_t),
            "summary_at_far5_threshold": summarise(y_test, s_test, far5_t),
            "own_eer_reference_only": dict(zip(("eer", "threshold"), eer(y_test, s_test))),
            "distribution": distribution(y_test, s_test),
            "timing": test_timing,
        },
        "per_vocoder": {},
    }
    for voc in sorted(vocoders["test"]):
        idx = [i for i, s in enumerate(test_scored)
               if s.system_id == voc or s.label == BONAFIDE]
        yy, ss = y_test[idx], s_test[idx]
        if len(set(yy.tolist())) < 2:
            continue
        results["per_vocoder"][voc] = summarise(yy, ss, far1_t)

    (out_dir / "results.json").write_text(json.dumps(results, indent=2, default=float))
    (out_dir / "run_metadata.json").write_text(json.dumps(run_metadata(detector, extra={
        "run_tag": tag, "seed": SEED, "dataset": "wavefake + LJSpeech-1.1",
        "protocol": "vocoder-disjoint + utterance-disjoint",
        "subset_note": ("documented subset: contiguous storage-order block per vocoder "
                        "from generated_audio.zip, filtered to one side of the utterance "
                        "hash split; storage order is randomised w.r.t. utterance id"),
        "calibration_version": CALIBRATION_VERSION,
        "cascade_disabled_for_evaluation": True,
        "single_speaker_corpus": True,
    }), indent=2, default=str))

    t = results["test_unseen_vocoders"]
    log("-- TEST on UNSEEN vocoders --")
    log(f"  ROC-AUC {t['summary_at_eer_threshold']['roc_auc']:.4f}  "
        f"own EER {t['own_eer_reference_only']['eer']:.4f}")
    log(f"  at calibration EER threshold: FAR {t['summary_at_eer_threshold']['far']:.4f}  "
        f"FRR {t['summary_at_eer_threshold']['frr']:.4f}")
    log(f"  at FAR<=1% threshold:         FAR {t['summary_at_far1_threshold']['far']:.4f}  "
        f"FRR {t['summary_at_far1_threshold']['frr']:.4f}")
    for voc, m in results["per_vocoder"].items():
        log(f"    {voc:<22} AUC {m['roc_auc']:.4f}  FAR {m['far']:.4f}")
    log(f"done -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
