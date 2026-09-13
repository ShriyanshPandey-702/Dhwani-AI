"""
Real authenticity backend — model loading, inference, failure handling and the
guarantee that a fallback is never reported as real ML.

Tests that need the AASIST checkpoints skip cleanly when they are absent, so the
suite still runs on a machine that has not fetched models.
"""

from pathlib import Path

import numpy as np
import pytest

from app.ml.authenticity import dsp
from app.ml.authenticity.aasist import (
    CHECKPOINTS, MODEL_CONFIGS, NB_SAMP, AASISTDetector, CheckpointMissing,
)
from app.ml.authenticity.detector import (
    HEURISTIC_DEMO, HEURISTIC_FALLBACK, REAL_ML, AuthenticityDetector,
)

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
MODEL_DIR = Path(__file__).resolve().parents[1] / "models"

torch = pytest.importorskip("torch", reason="PyTorch not installed")

checkpoints_present = all(
    (MODEL_DIR / "aasist" / fname).is_file() for fname, _ in CHECKPOINTS.values()
)
needs_checkpoints = pytest.mark.skipif(
    not checkpoints_present,
    reason="AASIST checkpoints absent — run scripts/fetch_models.py",
)


@pytest.fixture(scope="module")
def speech() -> np.ndarray:
    """Real speech waveform (macOS TTS, i.e. synthetic origin) at 16 kHz mono."""
    import soundfile as sf

    path = FIXTURES / "tts_synthetic_16k.wav"
    if not path.is_file():
        pytest.skip("speech fixture missing")
    audio, sr = sf.read(path, dtype="float32")
    assert sr == 16000
    return audio


@pytest.fixture(scope="module")
def real_detector():
    detector = AASISTDetector(model_dir=str(MODEL_DIR), variant="AASIST-L", cascade=False)
    if not detector.is_available:
        pytest.skip("AASIST checkpoints absent")
    return detector


# ── 1. Model loading ──────────────────────────────────────────────────────────

@needs_checkpoints
def test_both_checkpoints_load_strictly():
    """A strict load proves the vendored architecture matches the released weights."""
    from app.ml.authenticity.vendor.aasist_model import Model

    for name in ("AASIST", "AASIST-L"):
        model = Model(MODEL_CONFIGS[name])
        state = torch.load(MODEL_DIR / "aasist" / CHECKPOINTS[name][0], map_location="cpu")
        model.load_state_dict(state, strict=True)   # raises if keys/shapes differ


@needs_checkpoints
def test_checkpoint_integrity_matches_recorded_hashes():
    import hashlib

    for name, (fname, expected) in CHECKPOINTS.items():
        digest = hashlib.sha256((MODEL_DIR / "aasist" / fname).read_bytes()).hexdigest()
        assert digest == expected, f"{name} checkpoint does not match its recorded hash"


def test_missing_checkpoint_raises_rather_than_faking(tmp_path):
    detector = AASISTDetector(model_dir=str(tmp_path))
    assert detector.is_available is False
    assert detector.missing_checkpoints()
    with pytest.raises(CheckpointMissing):
        detector._load("AASIST-L")


# ── 2–5. Inference over valid, invalid, silent and short audio ────────────────

@needs_checkpoints
def test_valid_speech_produces_an_in_range_observation(real_detector, speech):
    observed = real_detector.score(speech)
    assert 0.0 <= observed.synthetic_probability <= 1.0
    assert 0.0 <= observed.model_confidence <= 0.80   # never claims certainty
    assert observed.model_name == "AASIST"
    assert observed.inference_ms > 0
    assert observed.tiers_run == ("AASIST-L",)


@needs_checkpoints
@pytest.mark.parametrize("length", [1, 100, 1000, NB_SAMP - 1, NB_SAMP, NB_SAMP + 5000])
def test_any_length_is_fitted_to_the_trained_input_size(real_detector, length):
    audio = np.sin(np.arange(length, dtype=np.float32) * 0.05) * 0.3
    fitted = real_detector._fit_length(audio)
    assert fitted.shape == (NB_SAMP,)
    assert np.all(np.isfinite(fitted))


def test_detector_returns_none_for_silence():
    """Silence is not evidence — a model has no defined behaviour on it."""
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    assert detector.analyze(np.zeros(64600, dtype=np.float32)) is None
    assert detector.analyze(np.full(64600, 1e-5, dtype=np.float32)) is None


def test_detector_returns_none_for_short_audio():
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    assert detector.analyze(np.random.randn(100).astype(np.float32) * 0.1) is None
    assert detector.analyze(None) is None


@needs_checkpoints
def test_non_finite_audio_does_not_crash_the_detector(speech):
    detector = AuthenticityDetector(pipeline_mode=REAL_ML)
    if not detector.is_real_ml:
        pytest.skip("real backend unavailable")
    broken = speech.copy()
    broken[:100] = np.nan
    result = detector.analyze(broken)          # must not raise
    assert result is None or 0.0 <= result.spoof_probability <= 1.0


# ── 6. Window / repeated inference ────────────────────────────────────────────

@needs_checkpoints
def test_repeated_windows_all_score_in_range(real_detector, speech):
    tiled = np.tile(speech, 3)
    windows = [tiled[i:i + NB_SAMP] for i in range(0, len(tiled) - NB_SAMP, NB_SAMP // 2)][:6]
    assert len(windows) >= 3
    for w in windows:
        observed = real_detector.score(w)
        assert 0.0 <= observed.synthetic_probability <= 1.0


# ── 7–8. Output range and reproducibility ─────────────────────────────────────

@needs_checkpoints
def test_inference_is_deterministic_for_identical_input(real_detector, speech):
    """Eval-mode inference must be reproducible; dropout must not be active."""
    a = real_detector.score(speech).synthetic_probability
    b = real_detector.score(speech).synthetic_probability
    assert a == pytest.approx(b, abs=1e-6)


@needs_checkpoints
def test_cascade_runs_the_heavy_tier_only_when_undecided(speech):
    """The cascade is a real tiering of two released checkpoints."""
    always = AASISTDetector(model_dir=str(MODEL_DIR), variant="AASIST-L",
                            cascade=True, cascade_margin=1.0)
    never = AASISTDetector(model_dir=str(MODEL_DIR), variant="AASIST-L",
                           cascade=True, cascade_margin=0.0)
    assert always.score(speech).tiers_run == ("AASIST-L", "AASIST")
    assert never.score(speech).tiers_run == ("AASIST-L",)


# ── 9. Failure recovery ───────────────────────────────────────────────────────

def test_backend_failure_degrades_to_a_labelled_fallback(monkeypatch, speech):
    """A model that raises mid-call must not end the session or lie about mode."""
    detector = AuthenticityDetector(pipeline_mode=REAL_ML)
    if not detector.is_real_ml:
        pytest.skip("real backend unavailable")

    def boom(_audio):
        raise RuntimeError("simulated inference failure")

    monkeypatch.setattr(detector._aasist, "score", boom)
    result = detector.analyze(speech)

    assert result is not None, "a failed window must still produce evidence"
    assert result.pipeline_mode == HEURISTIC_FALLBACK
    assert result.is_mock is True
    assert result.model_name == "heuristic-dsp"


def test_missing_checkpoints_fall_back_and_record_the_reason(monkeypatch):
    monkeypatch.setenv("MODEL_DIR", "/nonexistent")
    from app.core.config import settings

    monkeypatch.setattr(settings, "MODEL_DIR", "/nonexistent")
    detector = AuthenticityDetector(pipeline_mode=REAL_ML)
    assert detector.pipeline_mode == HEURISTIC_FALLBACK
    assert detector.is_real_ml is False
    assert "checkpoint" in (detector.fallback_reason or "").lower()


# ── 12. Evidence schema ───────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "score", "spoof_probability", "confidence",
    "acoustic_anomaly", "spectral_anomaly", "prosody_anomaly",
    "model_version", "is_mock", "model_name", "pipeline_mode",
    "inference_ms", "device",
}


def test_evidence_schema_is_stable_across_backends(speech):
    """The dashboard's contract must not depend on which backend ran."""
    demo = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO).analyze(speech)
    assert REQUIRED_FIELDS <= set(demo.to_dict())

    real = AuthenticityDetector(pipeline_mode=REAL_ML)
    if real.is_real_ml:
        observed = real.analyze(speech)
        assert set(observed.to_dict()) == set(demo.to_dict())
        assert observed.is_mock is False
        assert observed.pipeline_mode == REAL_ML


def test_evidence_carries_no_identity_or_context_fields(speech):
    """Stream independence: authenticity must not leak the other streams."""
    result = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO).analyze(speech).to_dict()
    for leaked in ("otp_request", "match_score", "transcript", "enrollment_status",
                   "financial_request", "consequence"):
        assert leaked not in result


def test_anomaly_bands_are_always_valid(speech):
    result = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO).analyze(speech)
    for value in (result.acoustic_anomaly, result.spectral_anomaly, result.prosody_anomaly):
        assert value in {dsp.LOW, dsp.MEDIUM, dsp.HIGH}


# ── 13. Mock-mode regression ──────────────────────────────────────────────────

def test_mock_mode_scores_are_unchanged_by_real_ml_integration():
    """The deterministic demonstration must be bit-for-bit what it always was."""
    from app.ml.preprocessing.audio import preprocess_audio_chunk
    from app.simulation.mock_audio import generate_frame

    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    observed = [
        detector.analyze(preprocess_audio_chunk(generate_frame(step, 12))).spoof_probability
        for step in (0, 5, 11)
    ]
    assert observed == pytest.approx([0.1224, 0.5082, 0.6963], abs=5e-4)


def test_mock_mode_never_claims_to_be_real_ml():
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    assert detector.is_real_ml is False
    assert detector.pipeline_mode == HEURISTIC_DEMO
    assert detector.model_name == "heuristic-dsp"


# ── Score calibration integration ────────────────────────────────────────────

CALIBRATOR = Path(__file__).resolve().parents[1] / "models" / "calibration" / \
    "authenticity_isotonic_asvspoof2019la.json"


def test_shipped_calibrator_loads_and_is_monotonic():
    from app.ml.authenticity.calibration import load_calibrator

    if not CALIBRATOR.is_file():
        pytest.skip("shipped calibrator absent")
    cal = load_calibrator(CALIBRATOR)
    assert cal.method == "isotonic"
    grid = np.linspace(0, 1, 200)
    out = cal.predict(grid)
    assert np.all(np.diff(out) >= -1e-9), "calibration must be monotonic"
    assert np.all((out >= 0) & (out <= 1))


def test_calibrator_carries_its_provenance():
    from app.ml.authenticity.calibration import load_calibrator

    if not CALIBRATOR.is_file():
        pytest.skip("shipped calibrator absent")
    prov = load_calibrator(CALIBRATOR).provenance
    assert "fitted_on" in prov and "ASVspoof" in prov["fitted_on"]
    assert "warning" in prov, "an in-domain-only calibrator must carry its caveat"


def test_raw_score_is_never_overwritten_by_calibration(speech):
    """The contract: calibration is additive."""
    detector = AuthenticityDetector(pipeline_mode=REAL_ML)
    if not detector.is_real_ml or detector._calibrator is None:
        pytest.skip("real backend or calibrator unavailable")

    result = detector.analyze(speech)
    raw_again = detector._aasist.score(speech).synthetic_probability
    assert result.spoof_probability == pytest.approx(raw_again, abs=1e-4), \
        "spoof_probability must remain the raw model score"
    assert result.calibrated_spoof_probability is not None
    assert result.calibration_method == "isotonic"


def test_heuristic_backend_is_not_calibrated(speech):
    """The calibrator was fitted on model scores, not heuristic scores."""
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    result = detector.analyze(speech)
    assert result.calibrated_spoof_probability is None
    assert result.calibration_method is None


def test_a_broken_calibrator_cannot_break_inference(monkeypatch, tmp_path, speech):
    bad = tmp_path / "bad.json"
    bad.write_text('{"method": "nonsense"}')
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTHENTICITY_CALIBRATOR", str(bad))
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    assert detector._calibrator is None
    assert detector.analyze(speech) is not None, "inference must survive a bad calibrator"


def test_missing_calibrator_is_not_an_error(monkeypatch, speech):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTHENTICITY_CALIBRATOR", "/nonexistent/cal.json")
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    assert detector._calibrator is None
    assert detector.analyze(speech) is not None


def test_fusion_uses_the_raw_score_by_default(speech):
    """
    The shipped calibrator was fitted in-domain only, and the model is
    near-chance out of domain, so the fused value stays the raw score unless
    explicitly opted in.
    """
    from app.core.config import settings

    assert settings.USE_CALIBRATED_SCORE_FOR_FUSION is False
