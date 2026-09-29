"""
Phase 2 PS Coverage Enrichment Tests:
Verifies Pitch (F0), Prosody, Rhythm, Pause Analysis, Microvariation,
and Hindi/Hinglish contextual scam classification.
"""

import math
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app
from app.ml.authenticity import dsp
from app.ml.authenticity.detector import AuthenticityDetector, AuthenticityResult
from app.ml.context.classifier import ContextClassifier

client = TestClient(app)


# ── 1. Pitch / F0 Analysis Tests ──────────────────────────────────────────────

def test_pitch_voiced_audio_returns_finite_values():
    sr = 16000
    duration_s = 2.0
    t = np.arange(int(sr * duration_s)) / float(sr)
    # Generate 180 Hz periodic fundamental with harmonics
    audio = 0.5 * np.sin(2 * np.pi * 180 * t) + 0.25 * np.sin(2 * np.pi * 360 * t)
    audio = audio.astype(np.float32)

    result = dsp.estimate_pitch_f0(audio, sample_rate=sr)
    assert result is not None, "Voiced audio must return pitch statistics"
    assert "mean_f0_hz" in result
    assert result["mean_f0_hz"] is not None
    assert 170.0 <= result["mean_f0_hz"] <= 190.0, f"Expected ~180 Hz, got {result['mean_f0_hz']}"
    assert math.isfinite(result["mean_f0_hz"])
    assert math.isfinite(result["f0_std_hz"])
    assert math.isfinite(result["f0_min_hz"])
    assert math.isfinite(result["f0_max_hz"])
    assert 0.0 <= result["voiced_frame_ratio"] <= 1.0


def test_pitch_silence_returns_unavailable():
    sr = 16000
    silence = np.zeros(sr * 2, dtype=np.float32)
    result = dsp.estimate_pitch_f0(silence, sample_rate=sr)
    assert result is None, "Pure silence must return None (unavailable)"


def test_pitch_short_audio_does_not_crash():
    sr = 16000
    short_audio = np.random.randn(200).astype(np.float32)
    result = dsp.estimate_pitch_f0(short_audio, sample_rate=sr)
    assert result is None, "Short audio (< 100ms) must return None safely without crashing"

    # None input
    assert dsp.estimate_pitch_f0(None, sample_rate=sr) is None


# ── 2. Prosody Analysis Tests ─────────────────────────────────────────────────

def test_prosody_valid_audio_returns_finite_metrics():
    sr = 16000
    t = np.arange(sr * 3) / float(sr)
    # Modulated audio: 150 Hz carrier with amplitude modulation
    carrier = np.sin(2 * np.pi * 150 * t)
    modulator = 0.5 * (1.0 + np.sin(2 * np.pi * 3 * t))
    audio = (carrier * modulator).astype(np.float32)

    prosody = dsp.analyze_prosody(audio, sample_rate=sr)
    assert prosody is not None
    assert "pitch_variability" in prosody
    assert "energy_variability" in prosody
    assert "voiced_ratio" in prosody
    assert "pause_ratio" in prosody
    assert "speech_segment_count" in prosody

    # Verify no NaN or Infinity
    for k, v in prosody.items():
        if isinstance(v, float):
            assert math.isfinite(v), f"Key {k} has non-finite value {v}"


def test_prosody_insufficient_audio_handled_safely():
    sr = 16000
    assert dsp.analyze_prosody(None, sr) is None
    silence = np.zeros(sr, dtype=np.float32)
    assert dsp.analyze_prosody(silence, sr) is None


# ── 3. Rhythm and Pause Analysis Tests ────────────────────────────────────────

def test_rhythm_and_pause_segmentation_works():
    sr = 16000
    # Create 1s speech, 0.5s silence, 1s speech, 0.5s silence
    speech1 = 0.5 * np.sin(2 * np.pi * 200 * np.arange(sr) / sr).astype(np.float32)
    pause1 = np.zeros(int(sr * 0.5), dtype=np.float32)
    speech2 = 0.5 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr).astype(np.float32)
    pause2 = np.zeros(int(sr * 0.5), dtype=np.float32)
    audio = np.concatenate([speech1, pause1, speech2, pause2])

    result = dsp.analyze_rhythm_and_pauses(audio, sample_rate=sr)
    assert result is not None
    assert result["speech_segment_count"] >= 2
    assert result["pause_count"] >= 1
    assert result["total_speech_duration_ms"] > 1000
    assert result["total_pause_duration_ms"] > 500
    assert result["longest_pause_duration_ms"] >= 400.0
    assert 0.0 <= result["pause_to_speech_ratio"] <= 1.0
    assert result["speech_to_pause_ratio"] > 0.0


def test_rhythm_and_pause_silence_returns_none():
    sr = 16000
    silence = np.zeros(sr * 2, dtype=np.float32)
    result = dsp.analyze_rhythm_and_pauses(silence, sample_rate=sr)
    assert result is None, "Silence must produce None rather than fabricated pause ratios"


# ── 4. Microvariation Analysis Tests ──────────────────────────────────────────

def test_microvariation_returns_finite_metrics_without_nan():
    sr = 16000
    # Realistic speech-like modulated harmonic waveform
    t = np.arange(sr * 2) / float(sr)
    audio = 0.4 * np.sin(2 * np.pi * 160 * t) + 0.1 * np.random.randn(len(t))
    audio = audio.astype(np.float32)

    micro = dsp.analyze_microvariation(audio, sample_rate=sr)
    assert micro is not None
    assert "energy_variability" in micro
    assert "zcr_variability" in micro
    assert "spectral_variability" in micro
    assert "jitter_shimmer_status" in micro
    assert "not_implemented" in micro["jitter_shimmer_status"]

    for k, v in micro.items():
        if isinstance(v, float):
            assert math.isfinite(v), f"Microvariation field {k} is non-finite: {v}"
            assert not math.isnan(v), f"Microvariation field {k} is NaN"


# ── 5. Hindi / Hinglish Threat Classifier Tests ───────────────────────────────

@pytest.mark.parametrize(
    "phrase,expected_category,expected_consequence",
    [
        ("OTP batao", "otp_request", "critical"),
        ("paise turant transfer karo", "financial_request", "high"),
        ("police se baat karo", "authority_claim", "medium"),
        ("aapka KYC verify karna hai", "financial_request", "high"),
        ("you have won a lottery prize", "financial_request", "high"),
        ("digital arrest warrant nikla hai", "authority_claim", "medium"),
        ("aadhaar card number verify karo", "sensitive_information_request", "high"),
    ],
)
def test_hindi_hinglish_scam_detection(phrase, expected_category, expected_consequence):
    cc = ContextClassifier()
    res = cc.classify("session_test", phrase)
    assert res is not None
    assert getattr(res, expected_category) is True, f"Failed to detect {expected_category} in '{phrase}'"
    assert res.score > 0
    assert len(res.detected_phrases) > 0


def test_benign_conversations_do_not_trigger_critical_or_high_risk():
    cc = ContextClassifier()
    benign_sentences = [
        "Namaste, aap kaise hain?",
        "Kal hum office me meeting karenge.",
        "Mera train ticket confirm ho gaya hai.",
        "The weather is very pleasant in New Delhi today.",
        "Please pick up some groceries on your way home.",
    ]
    for sentence in benign_sentences:
        res = cc.classify("session_benign", sentence)
        assert res is not None
        assert res.score == 0, f"Benign sentence '{sentence}' falsely triggered score {res.score}"
        assert res.consequence == "low"
        assert res.social_engineering is False
        cc.reset("session_benign")


# ── 6. AuthenticityDetector DSP Integration Tests ─────────────────────────────

def test_authenticity_detector_includes_dsp_evidence():
    detector = AuthenticityDetector()
    sr = 16000
    t = np.arange(sr * 4) / float(sr)
    audio = 0.5 * np.sin(2 * np.pi * 175 * t) + 0.1 * np.random.randn(len(t))
    audio = audio.astype(np.float32)

    res = detector.analyze(audio)
    assert res is not None
    data = res.to_dict()

    assert "pitch" in data
    assert "prosody" in data
    assert "rhythm" in data
    assert "pause_analysis" in data
    assert "microvariation" in data
    assert "spectral_details" in data

    if data["pitch"] is not None:
        assert math.isfinite(data["pitch"]["mean_f0_hz"])
    if data["prosody"] is not None:
        assert data["prosody"]["note"] is not None
    if data["microvariation"] is not None:
        assert math.isfinite(data["microvariation"]["energy_variability"])


# ── 7. API Serialization & Numerical Safety Test ─────────────────────────────

def test_manual_analysis_api_serializes_phase2_fields():
    import io
    import soundfile as sf

    sr = 16000
    duration_s = 4.2
    t = np.arange(int(sr * duration_s)) / float(sr)
    audio = 0.4 * np.sin(2 * np.pi * 180 * t) + 0.1 * np.random.randn(len(t))
    buf = io.BytesIO()
    sf.write(buf, audio.astype(np.float32), sr, format="WAV", subtype="PCM_16")
    wav_bytes = buf.getvalue()

    files = {"file": ("speech_sample.wav", wav_bytes, "audio/wav")}
    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "completed"
    assert "authenticity" in data
    assert "prosody" in data
    assert "microvariation" in data
    assert "pitch" in data
    assert "pause_analysis" in data
    assert "window_timeline" in data

    # Verify no NaN or Infinity strings
    raw_json_str = response.text
    assert "NaN" not in raw_json_str
    assert "Infinity" not in raw_json_str
    assert "-Infinity" not in raw_json_str
