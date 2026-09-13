"""
Evaluation smoke test.

Runs the full harness — real model → scores → metrics → threshold selection →
calibration → robustness → streaming — on a handful of generated WAV files.

This proves the pipeline is wired correctly. It is emphatically NOT a benchmark:
the audio is synthetic and the sample count is tiny, so the numbers it produces
are meaningless as measurements and are never reported as such.
"""

from pathlib import Path

import numpy as np
import pytest

from evaluation.calibration.calibrate import PlattCalibrator, evaluate_calibration
from evaluation.datasets.base import (
    BONAFIDE, SPOOF, Sample, audit_split_disjointness, validate_labels, write_manifest,
)
from evaluation.metrics.detection import eer, find_threshold_for_far, roc_auc, summarise
from evaluation.robustness.transforms import apply_condition
from evaluation.runners.score import NotRealModel, build_detector, run_metadata, score_samples

API_ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = API_ROOT / "models"

torch = pytest.importorskip("torch", reason="PyTorch not installed")
checkpoints_present = (MODEL_DIR / "aasist" / "AASIST-L.pth").is_file()
needs_model = pytest.mark.skipif(
    not checkpoints_present, reason="AASIST checkpoint absent — run scripts/fetch_models.py"
)


@pytest.fixture(scope="module")
def tiny_corpus(tmp_path_factory):
    """
    A few seconds of two clearly different synthetic signals, written as WAVs.

    Class membership here is arbitrary — this fixture exercises plumbing, not
    detection quality.
    """
    import soundfile as sf

    root = tmp_path_factory.mktemp("tiny_corpus")
    rng = np.random.default_rng(4)
    samples = []
    for i in range(6):
        t = np.arange(16000 * 5) / 16000.0
        if i % 2 == 0:
            sig = 0.3 * np.sin(2 * np.pi * (140 + i) * t) * (1 + 0.4 * np.sin(2 * np.pi * 3 * t))
            label, split = BONAFIDE, "calib" if i < 3 else "test"
        else:
            sig = 0.3 * np.sign(np.sin(2 * np.pi * (200 + i) * t))
            label, split = SPOOF, "calib" if i < 3 else "test"
        sig = (sig + 0.01 * rng.standard_normal(sig.size)).astype(np.float32)
        path = root / f"clip_{i}_{'bona' if label == 0 else 'spoof'}.wav"
        sf.write(path, sig, 16000)
        samples.append(Sample(str(path), label, "smoke", split, speaker_id=f"S{i}"))
    return samples


def test_runner_refuses_to_score_without_the_real_model(tmp_path):
    """The critical safeguard: no silent fallback to a non-model backend."""
    with pytest.raises(NotRealModel):
        build_detector(variant="AASIST-L", model_dir=str(tmp_path))


@needs_model
def test_full_harness_runs_end_to_end(tiny_corpus, tmp_path):
    validate_labels(tiny_corpus)
    audit = audit_split_disjointness(tiny_corpus, ["calib", "test"])
    assert audit["clean"] is True, "the smoke corpus must have disjoint splits"

    manifest = write_manifest(tiny_corpus, tmp_path / "manifest.csv")
    assert manifest.is_file()

    detector = build_detector(variant="AASIST-L", cascade=False)

    calib = [s for s in tiny_corpus if s.split == "calib"]
    test = [s for s in tiny_corpus if s.split == "test"]

    calib_scored = score_samples(calib, detector, batch_size=2)
    test_scored = score_samples(test, detector, batch_size=2)
    assert len(calib_scored) == len(calib)
    assert len(test_scored) == len(test)
    assert all(0.0 <= s.score <= 1.0 for s in calib_scored + test_scored)

    y_cal = np.array([s.label for s in calib_scored])
    s_cal = np.array([s.score for s in calib_scored])
    y_test = np.array([s.label for s in test_scored])
    s_test = np.array([s.score for s in test_scored])

    # Metrics must compute and stay in range; their values are not asserted.
    auc = roc_auc(y_cal, s_cal)
    assert 0.0 <= auc <= 1.0
    value, threshold = eer(y_cal, s_cal)
    assert 0.0 <= value <= 1.0
    secure_threshold, secure = find_threshold_for_far(y_cal, s_cal, 0.05)
    assert 0.0 <= secure_threshold <= 1.0

    # Calibration fits on calib and is applied to test — never the reverse.
    calibrator = PlattCalibrator().fit(s_cal, y_cal)
    report = evaluate_calibration(y_test, s_test, calibrator.predict(s_test))
    assert 0.0 <= report["brier_calibrated"] <= 1.0
    assert 0.0 <= report["ece_calibrated"] <= 1.0

    out = summarise(y_test, s_test, threshold)
    for key in ("roc_auc", "eer", "far", "frr", "apcer", "bpcer", "confusion"):
        assert key in out


@needs_model
def test_robustness_conditions_score_without_error(tiny_corpus):
    detector = build_detector(variant="AASIST-L", cascade=False)
    subset = tiny_corpus[:2]
    for condition in ("clean", "noise_white_10db", "telephone_chain", "clipping"):
        scored = score_samples(subset, detector, condition=condition, batch_size=2)
        assert len(scored) == len(subset)
        assert all(0.0 <= s.score <= 1.0 for s in scored)
        assert all(s.condition == condition for s in scored)


@needs_model
def test_streaming_harness_uses_the_production_windower(tiny_corpus):
    from app.core.config import settings
    from app.ml.preprocessing.stream import StreamWindower

    from evaluation.runners.score import load_audio
    from evaluation.runners.streaming import run_stream

    detector = build_detector(variant="AASIST-L", cascade=False)
    windower = StreamWindower(window_ms=settings.ANALYSIS_WINDOW_MS,
                              hop_ms=settings.ANALYSIS_HOP_MS)
    audio = load_audio(tiny_corpus[0].audio_path)
    audio = np.tile(audio, 3)                       # long enough for several windows

    result = run_stream(audio, detector, windower, session="smoke", name="smoke")
    assert result.windows_scored >= 2
    assert all(0.0 <= s <= 1.0 for s in result.scores)
    stats = result.stats()
    assert stats["n"] == result.windows_scored
    assert "jitter_mean_abs_delta" in stats


@needs_model
def test_silence_produces_no_windows_to_score():
    from app.core.config import settings
    from app.ml.preprocessing.stream import StreamWindower

    from evaluation.runners.streaming import run_stream

    detector = build_detector(variant="AASIST-L", cascade=False)
    windower = StreamWindower(window_ms=settings.ANALYSIS_WINDOW_MS,
                              hop_ms=settings.ANALYSIS_HOP_MS)
    result = run_stream(np.zeros(16000 * 10, dtype=np.float32), detector,
                        windower, session="silence", name="silence")
    assert result.windows_scored == 0, "silence must never be scored"
    assert result.skipped_no_evidence > 0


@needs_model
def test_run_metadata_records_what_is_needed_to_reproduce():
    detector = build_detector(variant="AASIST-L", cascade=False)
    meta = run_metadata(detector, extra={"run_tag": "smoke"})
    assert meta["model"]["name"] == "AASIST"
    assert meta["model"]["checkpoint_sha256"], "checkpoint hashes must be recorded"
    assert meta["preprocessing"]["sample_rate"] == 16000
    assert meta["preprocessing"]["input_samples"] == 64600
    assert meta["software"]["torch"]
    assert meta["hardware"]["machine"]
