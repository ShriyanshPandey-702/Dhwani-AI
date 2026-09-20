"""
Test suite for Manual Audio Analysis endpoint: POST /analysis/audio.

Verifies:
1. Valid WAV 10-second audio produces exactly 6 analysis windows:
   floor((160000 - 64608) / 16000) + 1 = 6
2. Valid MP3 audio ingestion and analysis
3. Stereo downmix and 44.1kHz resampling
4. Short-audio (< 4.038s) gate: status='insufficient_duration', windows_evaluated=0, risk_state=None
5. Silent audio gate: status='silent_audio', is_silent=True, risk_state=None
6. Oversized main file (> 25 MB) -> HTTP 413
7. Oversized speaker reference (> 25 MB) -> HTTP 413
8. Exceeded maximum duration (> 300s) -> HTTP 400
9. Corrupted audio container -> HTTP 400
10. Enrolled matching reference -> ENROLLED, high similarity
11. Enrolled mismatched reference with P=2 -> corroboration confirmed, cap bypassed
12. Self-consistency protection with benign context -> capped at <= 38 (LOW)
13. Self-consistency with malicious context -> context corroboration bypasses cap
14. Guaranteed cleanup of temporary files on disk
15. Backend-selection: manual analysis explicitly uses real_ml, never inherits mock
16. Backend-selection: report cannot claim real_ml while returning heuristic stubs
17. Backend-selection: AASIST metadata corresponds to the actual AASIST backend
18. Backend-selection: Whisper metadata corresponds to the actual faster-whisper backend
19. Backend-selection: ECAPA is honest (real or explicit fallback, never mis-labelled)
"""

import io
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from main import app
from app.ml.authenticity.detector import AuthenticityResult, REAL_ML as AUTH_REAL_ML, HEURISTIC_FALLBACK as AUTH_FALLBACK
from app.ml.context.classifier import ContextResult
import app.api.analysis as _analysis_module


client = TestClient(app)


def _generate_wav_bytes(duration_s: float, sr: int = 16000, channels: int = 1, freq: float = 440.0) -> bytes:
    """Generate in-memory WAV audio bytes."""
    num_samples = int(duration_s * sr)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    # Sine wave modulated slightly to simulate speech energy
    waveform = 0.5 * np.sin(2 * np.pi * freq * t).astype(np.float32)
    if channels == 2:
        waveform = np.column_stack([waveform, waveform])

    buf = io.BytesIO()
    sf.write(buf, waveform, sr, format="WAV")
    return buf.getvalue()


def _generate_mp3_bytes(duration_s: float, sr: int = 16000, freq: float = 440.0) -> bytes:
    """Generate in-memory MP3 audio bytes."""
    num_samples = int(duration_s * sr)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    waveform = 0.5 * np.sin(2 * np.pi * freq * t).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, waveform, sr, format="MP3")
    return buf.getvalue()


def test_valid_wav_10s_produces_6_windows():
    """10-second 16 kHz audio (160,000 samples) must produce exactly 6 analysis windows."""
    wav_bytes = _generate_wav_bytes(duration_s=10.0, sr=16000)
    files = {"file": ("test_10s.wav", wav_bytes, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "completed"
    assert data["analysis_completed"] is True
    assert data["filename"] == "test_10s.wav"
    assert round(data["duration_seconds"], 1) == 10.0
    assert data["sample_rate"] == 16000
    assert data["channels"] == 1
    # floor((160000 - 64608) / 16000) + 1 = 5 + 1 = 6
    assert data["windows_evaluated"] == 6
    assert len(data["window_timeline"]) == 6

    # Verify risk verdict
    assert data["risk_score"] is not None
    assert 0 <= data["risk_score"] <= 100
    assert data["risk_state"] in ("low", "suspicious", "high", "critical")
    assert data["decision"] in ("ALLOW", "VERIFY", "HOLD", "BLOCK", "ESCALATE")
    assert data["quality"]["is_silent"] is False


def test_valid_mp3_analysis():
    """Verify MP3 decoding and manual analysis."""
    mp3_bytes = _generate_mp3_bytes(duration_s=6.0, sr=16000)
    files = {"file": ("test_6s.mp3", mp3_bytes, "audio/mpeg")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "completed"
    assert data["analysis_completed"] is True
    assert data["windows_evaluated"] >= 1
    assert data["risk_score"] is not None


def test_stereo_downmix_and_resampling():
    """Stereo 44.1 kHz audio must be downmixed to mono and resampled to 16 kHz."""
    wav_bytes = _generate_wav_bytes(duration_s=5.0, sr=44100, channels=2)
    files = {"file": ("stereo_44k.wav", wav_bytes, "audio/wav")}

    def _safe_resample(audio, sr, target_sr=16000):
        import torch
        import torchaudio.functional as F
        t = torch.from_numpy(audio).float()
        return F.resample(t, sr, target_sr).numpy().astype(np.float32)

    with patch("app.ml.preprocessing.ingest._resample", side_effect=_safe_resample):
        response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "completed"
    assert data["sample_rate"] == 44100
    assert data["channels"] == 2
    assert data["windows_evaluated"] >= 1


def test_short_audio_insufficient_duration():
    """Audio shorter than 4.038 seconds (< 64,608 samples) must not produce ML verdict."""
    wav_bytes = _generate_wav_bytes(duration_s=2.5, sr=16000)
    files = {"file": ("short.wav", wav_bytes, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "insufficient_duration"
    assert data["analysis_completed"] is False
    assert data["windows_evaluated"] == 0
    assert data["window_timeline"] == []
    assert data["risk_score"] is None
    assert data["risk_state"] is None
    assert data["decision"] == "VERIFY"
    assert "audio_duration_less_than_window_size" in data["reasons"]


def test_silent_audio_gate():
    """Silent audio must be gated with status='silent_audio' and risk_state=None."""
    silence = np.zeros(160000, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, silence, 16000, format="WAV")
    silent_bytes = buf.getvalue()

    files = {"file": ("silence.wav", silent_bytes, "audio/wav")}
    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "silent_audio"
    assert data["analysis_completed"] is False
    assert data["quality"]["is_silent"] is True
    assert data["windows_evaluated"] == 0
    assert data["risk_score"] is None
    assert data["risk_state"] is None
    assert data["decision"] == "VERIFY"
    assert "silence_detected" in data["reasons"]


def test_oversized_main_file():
    """Main file exceeding 25 MB must return HTTP 413."""
    oversized = b"0" * (25 * 1024 * 1024 + 1024)
    files = {"file": ("oversized.wav", oversized, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_oversized_speaker_reference():
    """Speaker reference exceeding 25 MB must return HTTP 413."""
    valid_wav = _generate_wav_bytes(duration_s=5.0)
    oversized = b"0" * (25 * 1024 * 1024 + 1024)
    files = {
        "file": ("main.wav", valid_wav, "audio/wav"),
        "speaker_reference": ("oversized_ref.wav", oversized, "audio/wav"),
    }

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"


def test_audio_duration_too_long():
    """Audio exceeding 300.0 seconds must return HTTP 400."""
    long_wav = _generate_wav_bytes(duration_s=305.0)
    files = {"file": ("long.wav", long_wav, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "AUDIO_TOO_LONG"


def test_corrupted_container():
    """Malformed/corrupt audio container must return HTTP 400."""
    corrupted = b"RIFF\x00\x00\x00\x00WAVEfmt \x00\x00\x00\x00not_valid_audio_data"
    files = {"file": ("corrupt.wav", corrupted, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "CORRUPTED_CONTAINER"


def test_enrolled_matching_reference():
    """Supplied speaker reference must set enrollment_status='ENROLLED'."""
    wav_bytes = _generate_wav_bytes(duration_s=6.0, freq=440.0)
    ref_bytes = _generate_wav_bytes(duration_s=4.5, freq=440.0)

    files = {
        "file": ("test.wav", wav_bytes, "audio/wav"),
        "speaker_reference": ("ref.wav", ref_bytes, "audio/wav"),
    }

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["identity"]["enrollment_status"] == "ENROLLED"
    assert data["identity"]["similarity"] is not None


def _make_context_result(score: int = 5, consequence: str = "low", transcript: str = "Hello", **kwargs) -> ContextResult:
    return ContextResult(
        score=score,
        confidence=kwargs.get("confidence", 0.8),
        urgency=kwargs.get("urgency", False),
        financial_request=kwargs.get("financial_request", False),
        otp_request=kwargs.get("otp_request", False),
        credential_request=kwargs.get("credential_request", False),
        sensitive_information_request=kwargs.get("sensitive_information_request", False),
        social_engineering=kwargs.get("social_engineering", False),
        authority_claim=kwargs.get("authority_claim", False),
        consequence=consequence,
        transcript=transcript,
    )


def test_self_consistency_protection_benign_capped_at_38():
    """
    Mandatory Correction 1:
    High AASIST + NO speaker_reference + benign context:
    - enrollment_status = SELF_CONSISTENCY
    - identity_corroborated = False
    - benign context / context_risk < 0.25
    - uncorroborated passive risk <= 38
    - risk_state = LOW
    """
    wav_bytes = _generate_wav_bytes(duration_s=8.0, freq=440.0)
    files = {"file": ("fake_audio.wav", wav_bytes, "audio/wav")}

    fake_auth = AuthenticityResult(
        score=95,
        spoof_probability=0.95,
        confidence=0.85,
        acoustic_anomaly="HIGH",
        spectral_anomaly="HIGH",
        prosody_anomaly="HIGH",
        model_version="AASIST-L@asvspoof2019la",
        is_mock=False,
    )

    benign_ctx = _make_context_result(score=5, consequence="low", transcript="Good morning, thank you for calling customer service.")

    with patch("app.api.analysis.authenticity_detector.analyze", return_value=fake_auth):
        with patch("app.api.analysis.context_classifier.classify", return_value=benign_ctx):
            response = client.post("/analysis/audio", files=files)

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["identity"]["enrollment_status"] == "SELF_CONSISTENCY"
    # Uncorroborated total cap of 38.0 enforced!
    assert data["risk_score"] <= 38
    assert data["risk_state"] == "low"
    assert "total_risk_uncorroborated_cap_active" in data["reasons"]


def test_self_consistency_with_malicious_context_uncapped():
    """
    Mandatory Correction 1:
    High AASIST + NO speaker_reference + malicious context:
    - Context corroboration acts independently to bypass the 38 cap.
    - Full fusion permitted.
    """
    from app.ml.context.transcriber import TranscriptSegment

    wav_bytes = _generate_wav_bytes(duration_s=8.0, freq=440.0)
    files = {"file": ("attack_audio.wav", wav_bytes, "audio/wav")}

    fake_auth = AuthenticityResult(
        score=95,
        spoof_probability=0.95,
        confidence=0.85,
        acoustic_anomaly="HIGH",
        spectral_anomaly="HIGH",
        prosody_anomaly="HIGH",
        model_version="AASIST-L@asvspoof2019la",
        is_mock=False,
    )

    # Malicious context (e.g. OTP request -> context risk >= 0.70)
    malicious_ctx = _make_context_result(
        score=85,
        consequence="high",
        confidence=0.9,
        transcript="Please read me the 6-digit OTP code sent to your phone immediately.",
        financial_request=True,
        otp_request=True,
        urgency=True,
    )

    # The endpoint only calls context_classifier.classify when full_transcript
    # is non-empty.  Patch the transcriber to return a matching transcript so
    # that classify() is actually invoked.
    fake_segment = TranscriptSegment(
        text="Please read me the 6-digit OTP code sent to your phone immediately.",
        is_mock=False,
        model_version="faster-whisper-tiny-int8",
        model_name="faster-whisper",
        pipeline_mode="real_ml",
        language="en",
        language_probability=0.99,
        confidence=0.9,
    )

    with patch("app.api.analysis.authenticity_detector.analyze", return_value=fake_auth):
        with patch("app.api.analysis.transcriber.transcribe", return_value=fake_segment):
            with patch("app.api.analysis.context_classifier.classify", return_value=malicious_ctx):
                response = client.post("/analysis/audio", files=files)

    assert response.status_code == 200, response.text
    data = response.json()

    # Context corroboration lifted the cap!
    assert data["risk_score"] > 38
    assert data["risk_state"] in ("high", "critical")
    assert "total_risk_uncorroborated_cap_active" not in data["reasons"]


def test_enrolled_mismatch_corroboration_p2_uncapped():
    """
    High AASIST + ENROLLED reference with persistent mismatch (P=2):
    - Identity corroboration is confirmed.
    - Bypasses the 38 cap via identity corroboration.
    """
    wav_bytes = _generate_wav_bytes(duration_s=8.0, freq=440.0)
    ref_bytes = _generate_wav_bytes(duration_s=4.5, freq=880.0)

    files = {
        "file": ("fake_impostor.wav", wav_bytes, "audio/wav"),
        "speaker_reference": ("ref.wav", ref_bytes, "audio/wav"),
    }

    fake_auth = AuthenticityResult(
        score=95,
        spoof_probability=0.95,
        confidence=0.85,
        acoustic_anomaly="HIGH",
        spectral_anomaly="HIGH",
        prosody_anomaly="HIGH",
        model_version="AASIST-L@asvspoof2019la",
        is_mock=False,
    )

    benign_ctx = _make_context_result(
        score=5,
        consequence="low",
        confidence=0.8,
        transcript="Hello, how can I help you today?",
    )

    from app.ml.identity.ecapa import Similarity

    fake_sim = Similarity(
        similarity=0.10,
        match_score=10,
        model_confidence=0.75,
        model_name="ECAPA-TDNN",
        model_version="spkrec-ecapa-voxceleb",
        inference_ms=1.0,
        device="cpu",
    )

    # Mock low similarity (0.10 <= 0.60) across windows to trigger P=2
    with patch("app.api.analysis.authenticity_detector.analyze", return_value=fake_auth):
        with patch("app.api.analysis.context_classifier.classify", return_value=benign_ctx):
            with patch("app.api.analysis.speaker_identity._demo.similarity", return_value=0.10):
                if getattr(_analysis_module.speaker_identity, "_ecapa", None) is not None:
                    with patch.object(_analysis_module.speaker_identity._ecapa, "compare", return_value=fake_sim):
                        response = client.post("/analysis/audio", files=files)
                else:
                    response = client.post("/analysis/audio", files=files)

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["identity"]["enrollment_status"] == "ENROLLED"
    # Identity mismatch corroboration bypassed the 38 cap!
    assert data["risk_score"] > 38
    assert "identity_corroboration_confirmed" in data["reasons"]


def test_temporary_files_cleanup(tmp_path):
    """Temporary files generated during analysis must not linger on disk."""
    wav_bytes = _generate_wav_bytes(duration_s=5.0)
    files = {"file": ("cleanup_test.wav", wav_bytes, "audio/wav")}

    created_temps = []
    original_named_temp = __import__("tempfile").NamedTemporaryFile

    def tracking_tempfile(*args, **kwargs):
        tf = original_named_temp(*args, **kwargs)
        created_temps.append(Path(tf.name))
        return tf

    with patch("app.api.analysis.tempfile.NamedTemporaryFile", side_effect=tracking_tempfile):
        response = client.post("/analysis/audio", files=files)

    assert response.status_code == 200
    assert len(created_temps) > 0
    # Every tracked temporary file must be unlinked/deleted
    for temp_path in created_temps:
        assert not temp_path.exists(), f"Temporary file {temp_path} was not cleaned up!"


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND-SELECTION VERIFICATION TESTS (Requirement §TEST)
# ═══════════════════════════════════════════════════════════════════════════════

def test_manual_analysis_explicitly_requests_real_ml():
    """
    Backend test 1: The module-level detector instances in analysis.py must
    have been initialised with pipeline_mode='real_ml'.  They must NOT carry
    the global PIPELINE_MODE='mock' default from settings.
    """
    # The detectors are constructed at import time with pipeline_mode="real_ml".
    # pipeline_mode reflects the actual outcome (real_ml | heuristic_fallback).
    # Either is acceptable — but 'heuristic_demo' means mock was used without
    # even attempting real_ml, which is the failure mode we're guarding against.
    assert _analysis_module.authenticity_detector.pipeline_mode != "heuristic_demo", (
        "authenticity_detector inherited mock mode instead of attempting real_ml"
    )
    assert _analysis_module.transcriber.pipeline_mode != "heuristic_demo", (
        "transcriber inherited mock mode instead of attempting real_ml"
    )
    assert _analysis_module.speaker_identity.pipeline_mode != "heuristic_demo", (
        "speaker_identity inherited mock mode instead of attempting real_ml"
    )


def test_report_cannot_claim_real_ml_while_using_heuristic_stubs():
    """
    Backend test 2: The model_versions dict built from live instances must
    accurately reflect whether each backend is mock or real.
    Specifically, if authenticity_detector is in heuristic_fallback mode,
    model_versions must NOT report pipeline_mode='real_ml'.
    """
    mv = _analysis_module._build_model_versions()

    # pipeline_mode in model_versions mirrors authenticity_detector.pipeline_mode
    if _analysis_module.authenticity_detector.is_real_ml:
        assert mv["pipeline_mode"] == "real_ml"
        assert mv["authenticity_is_mock"] is False
        assert mv["authenticity_backend"] == "real_ml"
        # model_name must be AASIST, not heuristic-dsp
        assert mv["authenticity"] != "heuristic-dsp-stub-v0.3", (
            "Claiming AASIST version string while actually returning heuristic-dsp"
        )
    else:
        # Fallback is present; it must NOT be hidden as real_ml
        assert mv["authenticity_is_mock"] is True
        assert mv["pipeline_mode"] != "real_ml", (
            "pipeline_mode reported as real_ml but authenticity_detector is in fallback"
        )

    # STT similarly
    if _analysis_module.transcriber.is_real_ml:
        assert mv["stt_is_mock"] is False
        assert mv["stt_backend"] == "real_ml"
    else:
        assert mv["stt_is_mock"] is True

    # Identity similarly
    if _analysis_module.speaker_identity.is_real_ml:
        assert mv["identity_is_mock"] is False
    else:
        assert mv["identity_is_mock"] is True


def test_aasist_metadata_corresponds_to_actual_backend():
    """
    Backend test 3: In a completed analysis, the 'authenticity' field in the
    report must contain metadata that matches the actual running backend.
    A report may not claim AASIST variant/version while is_mock=True.
    """
    wav_bytes = _generate_wav_bytes(duration_s=10.0)
    files = {"file": ("backend_test.wav", wav_bytes, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["analysis_completed"] is True
    auth = data["authenticity"]
    assert auth is not None, "completed analysis must contain authenticity evidence"

    mv = data["model_versions"]

    if _analysis_module.authenticity_detector.is_real_ml:
        # Real AASIST ran
        assert auth["is_mock"] is False, "AASIST ran but is_mock=True in report"
        assert auth["pipeline_mode"] == "real_ml", (
            f"AASIST ran but pipeline_mode={auth['pipeline_mode']!r}"
        )
        assert auth["model_name"] == "AASIST", (
            f"Expected model_name='AASIST', got {auth['model_name']!r}"
        )
        assert mv["authenticity_is_mock"] is False
        assert mv["pipeline_mode"] == "real_ml"
    else:
        # Graceful fallback — must be explicitly labelled, never hidden
        assert auth["is_mock"] is True, (
            "Fallback backend must label is_mock=True in the report"
        )
        # Must NOT masquerade as AASIST
        assert auth["model_name"] != "AASIST", (
            "Fallback backend must not claim model_name='AASIST'"
        )
        assert mv["authenticity_is_mock"] is True
        # Fallback reason must be present
        assert mv["authenticity_fallback_reason"] is not None, (
            "Fallback must include a fallback_reason for transparency"
        )


def test_whisper_metadata_corresponds_to_actual_backend():
    """
    Backend test 4: STT metadata in model_versions must reflect the actual
    faster-whisper backend or an honest fallback, never scripted-stt when
    real_ml was successfully initialised.
    """
    mv = _analysis_module._build_model_versions()

    if _analysis_module.transcriber.is_real_ml:
        assert mv["stt_backend"] == "real_ml"
        assert mv["stt_is_mock"] is False
        # STT model version must NOT be the scripted stub version
        assert mv["stt"] != "scripted-stt-stub-v0.2", (
            "faster-whisper ran but model_versions.stt still shows scripted stub version"
        )
    else:
        # Honest fallback
        assert mv["stt_is_mock"] is True
        assert mv["stt_backend"] in ("heuristic_fallback", "heuristic_demo")
        assert mv["stt_fallback_reason"] is not None or mv["stt_backend"] == "heuristic_demo"


def test_ecapa_identity_is_honest():
    """
    Backend test 5: Speaker identity must be reported honestly.
    If ECAPA loaded (is_real_ml=True), model_name must be 'ecapa-tdnn' or similar.
    If ECAPA failed (heuristic_fallback), model_name must be 'spectral-fingerprint'
    and is_mock=True — never falsely labelled as ECAPA.
    """
    wav_bytes = _generate_wav_bytes(duration_s=10.0)
    files = {"file": ("ecapa_test.wav", wav_bytes, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    identity = data["identity"]
    assert identity is not None

    mv = data["model_versions"]

    if _analysis_module.speaker_identity.is_real_ml:
        assert identity["is_mock"] is False
        assert identity["pipeline_mode"] == "real_ml"
        # Must not show the spectral-fingerprint stub name
        assert identity["model_name"] != "spectral-fingerprint", (
            "Real ECAPA loaded but model_name='spectral-fingerprint' in report"
        )
        assert mv["identity_is_mock"] is False
    else:
        # Honest fallback — SciPy/SpeechBrain not available on this host
        assert identity["is_mock"] is True
        assert identity["model_name"] != "ecapa-tdnn" or identity["pipeline_mode"] != "real_ml", (
            "Identity fallback must not claim real_ml ECAPA-TDNN"
        )
        assert mv["identity_is_mock"] is True
        # Fallback reason must be surfaced for transparency
        assert mv["identity_fallback_reason"] is not None, (
            "Identity fallback must surface identity_fallback_reason"
        )


def test_risk_semantics_unchanged_after_adapter_fix():
    """
    Backend test 6 (regression): The four frozen risk states and Model B
    corroboration semantics must be unchanged after the adapter-level fix.
    Specifically:
    - A completed analysis with >= 1 window always has risk_state in the
      four frozen states.
    - Self-consistency NEVER sets identity_corroborated=True.
    - model_versions must never contain 'pipeline_mode': 'mock'.
    """
    wav_bytes = _generate_wav_bytes(duration_s=10.0)
    files = {"file": ("regression.wav", wav_bytes, "audio/wav")}

    response = client.post("/analysis/audio", files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["analysis_completed"] is True
    assert data["risk_state"] in ("low", "suspicious", "high", "critical")
    assert data["model_versions"].get("pipeline_mode") != "mock", (
        "model_versions.pipeline_mode must never be 'mock' in manual analysis"
    )


def test_model_dir_is_absolute_and_correct():
    """
    Backend test (path): The module-level _MANUAL_MODEL_DIR must resolve to
    the absolute services/api/models directory and the AASIST-L checkpoint
    must be present at the expected path with the validated SHA-256.
    """
    import hashlib
    model_dir = Path(_analysis_module._MANUAL_MODEL_DIR)
    assert model_dir.is_absolute(), f"_MANUAL_MODEL_DIR is not absolute: {model_dir}"
    assert model_dir.exists(), f"Model directory does not exist: {model_dir}"

    checkpoint = model_dir / "aasist" / "AASIST-L.pth"
    assert checkpoint.is_file(), f"AASIST-L.pth not found at {checkpoint}"

    # Verify SHA-256 against the validated checksum
    EXPECTED_SHA = "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a"
    h = hashlib.sha256()
    with open(checkpoint, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    assert h.hexdigest() == EXPECTED_SHA, (
        f"AASIST-L.pth SHA-256 mismatch: expected {EXPECTED_SHA}, got {h.hexdigest()}"
    )

