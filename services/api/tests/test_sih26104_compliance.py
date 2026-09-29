"""
Tests for SIH26104 Problem Statement Compliance:
- Multi-layer voice authenticity & VAD gating
- Acoustic and spectral analysis metrics
- Prosody & speech rhythm & pause analysis
- Microvariation metrics
- Speaker identity & cross-session reference consistency
- Contextual enrichment with English + Hindi/Hinglish vocabulary
- Context combinations preventing isolated single-word false positives
- Pre-transaction warning & recommended actions
- System capabilities, privacy, and policy endpoints
- Numerical safety (no NaN/Inf)
- Invariant preservation (weights 0.50/0.25/0.25, frozen risk states)
"""

import math
import numpy as np
import pytest
from fastapi.testclient import TestClient

from main import app
from app.ml.authenticity.dsp import (
    estimate_pitch_f0,
    analyze_rhythm_and_pauses,
    analyze_microvariation,
    analyze_prosody,
    extract_dsp_evidence,
    extract_spectral_details,
    safe_float,
    LOW,
)
from app.ml.preprocessing.audio import measure_quality, TARGET_SR
from app.ml.identity.speaker import SpeakerIdentity, NOT_ENROLLED, VERIFIED, MISMATCH, INSUFFICIENT_EVIDENCE
from app.ml.context.classifier import ContextClassifier
from app.risk.policy import DEFAULT_POLICY_CONFIG


client = TestClient(app)


def test_measure_quality_acoustic_fields():
    sr = TARGET_SR
    t = np.linspace(0, 1.0, sr, endpoint=False)
    # 440 Hz sine wave
    audio = 0.5 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    quality = measure_quality(audio, sr)

    assert quality.rms > 0.0
    assert quality.estimated_snr_db >= 0.0
    assert quality.clipping_ratio == 0.0
    assert not quality.is_silent
    assert quality.energy_variance >= 0.0
    assert quality.zcr > 0.0
    assert math.isfinite(quality.rms)
    assert math.isfinite(quality.energy_variance)
    assert math.isfinite(quality.zcr)


def test_pitch_f0_speech_vs_silence():
    sr = 16000
    # Silence or pure noise below voice range
    silence = np.zeros(sr * 2, dtype=np.float32)
    f0_silence = estimate_pitch_f0(silence, sr)
    assert f0_silence is None

    # Periodic harmonic signal (150 Hz pitch)
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    voice = (0.4 * np.sin(2 * np.pi * 150 * t) + 0.2 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    f0_voice = estimate_pitch_f0(voice, sr)
    assert f0_voice is not None
    assert f0_voice["mean_f0_hz"] is not None
    assert 120.0 <= f0_voice["mean_f0_hz"] <= 180.0
    assert f0_voice["voiced_frame_ratio"] > 0.5


def test_rhythm_and_pause_analysis():
    sr = 16000
    # Alternating 400ms speech and 300ms pause
    chunks = []
    t_chunk = np.linspace(0, 0.4, int(sr * 0.4), endpoint=False)
    speech_chunk = (0.5 * np.sin(2 * np.pi * 200 * t_chunk)).astype(np.float32)
    pause_chunk = np.zeros(int(sr * 0.3), dtype=np.float32)
    for _ in range(4):
        chunks.extend([speech_chunk, pause_chunk])
    audio = np.concatenate(chunks)

    rhythm = analyze_rhythm_and_pauses(audio, sr)
    assert rhythm is not None
    assert rhythm["speech_segment_count"] >= 3
    assert rhythm["total_speech_duration_ms"] > 0
    assert rhythm["total_pause_duration_ms"] > 0
    assert rhythm["speech_to_pause_ratio"] > 0.5


def test_microvariation_and_spectral():
    sr = 16000
    t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
    audio = (0.4 * np.sin(2 * np.pi * 300 * t) + 0.1 * np.random.randn(len(t))).astype(np.float32)
    micro = analyze_microvariation(audio, sr)
    assert micro is not None
    assert micro["energy_variability"] is not None
    assert micro["zcr_variability"] is not None
    assert micro["status"] == "available"
    assert "not_implemented" in micro["jitter_shimmer_status"]

    spectral = extract_spectral_details(audio, sr)
    assert spectral["centroid_hz"] is not None
    assert spectral["flatness"] is not None
    assert math.isfinite(spectral["centroid_hz"])
    assert math.isfinite(spectral["flatness"])


def test_dsp_evidence_unified_structure():
    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    audio = (0.4 * np.sin(2 * np.pi * 180 * t)).astype(np.float32)
    dsp = extract_dsp_evidence(audio, sr)

    assert "bands" in dsp
    assert "pitch" in dsp
    assert "prosody" in dsp
    assert "f0" in dsp
    assert "speech_rhythm" in dsp
    assert "behavioral" in dsp
    assert "microvariation" in dsp
    assert "spectral" in dsp

    assert dsp["f0"]["status"] in ("available", "unavailable")
    assert dsp["speech_rhythm"]["status"] in ("available", "unavailable")
    assert dsp["behavioral"]["status"] in ("available", "unavailable")


def test_speaker_identity_persistent_reference():
    spk = SpeakerIdentity(sample_rate=16000, pipeline_mode="heuristic_demo")
    sr = 16000
    t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
    ref_audio = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    # Initially no reference exists
    res_none = spk.analyze("session-1", ref_audio, reference_id="user-123")
    assert res_none.enrollment_status == NOT_ENROLLED
    assert not res_none.reference_available
    assert not res_none.comparison_available

    # Enroll persistent reference for user-123
    ok = spk.enroll_reference("user-123", ref_audio)
    assert ok
    assert spk.has_reference("user-123")

    # Match same audio
    res_match = spk.analyze("session-1", ref_audio, reference_id="user-123")
    assert res_match.reference_available
    assert res_match.comparison_available
    assert res_match.enrollment_status == VERIFIED
    assert res_match.match_score >= 70

    # Insufficient audio with reference present returns INSUFFICIENT_EVIDENCE
    short_audio = ref_audio[:500]
    res_short = spk.analyze("session-1", short_audio, reference_id="user-123")
    assert res_short.enrollment_status == INSUFFICIENT_EVIDENCE
    assert res_short.reference_available
    assert not res_short.comparison_available

    # Clean up
    assert spk.remove_reference("user-123")
    assert not spk.has_reference("user-123")


def test_context_combinations_prevent_false_positives():
    clf = ContextClassifier()

    # Isolated benign mention of bank without transaction intent
    res_benign = clf.classify("sess-test-1", "I parked my car near the bank yesterday")
    assert res_benign is not None
    assert not res_benign.financial_request
    assert res_benign.score < 20
    assert not res_benign.pre_transaction_warning

    # Actionable financial request: bank transfer / payment demand
    res_scam = clf.classify("sess-test-2", "Please do a bank transfer of the money immediately")
    assert res_scam is not None
    assert res_scam.financial_request
    assert res_scam.urgency
    assert res_scam.pre_transaction_warning
    assert "VERIFY CALLER" in res_scam.recommended_actions


def test_hindi_hinglish_context_detection():
    clf = ContextClassifier()

    # Hindi financial + urgency threat
    res_hi = clf.classify("sess-hi-1", "Aapka khata block ho gaya hai abhi ke abhi paise transfer karo")
    assert res_hi is not None
    assert res_hi.financial_request
    assert res_hi.urgency

    # Hindi OTP extraction
    res_otp = clf.classify("sess-hi-2", "Kripya turant otp batao verification ke liye")
    assert res_otp is not None
    assert res_otp.otp_request
    assert res_otp.urgency
    assert res_otp.pre_transaction_warning
    assert "USE MFA" in res_otp.recommended_actions


def test_system_capabilities_endpoint():
    resp = client.get("/system/capabilities")
    assert resp.status_code == 200
    data = resp.json()

    assert data["telephony"]["cellular_metadata"] == "available"
    assert data["telephony"]["cellular_audio"] == "unsupported"
    assert data["telephony"]["voip_media"] == "available"
    assert data["api"]["rest"] == "available"
    assert data["api"]["websocket"] == "available"
    assert data["alerts"]["email"] == "not_connected"
    assert data["alerts"]["sms"] == "not_connected"
    assert data["enterprise"]["multi_tenant"] is False
    assert data["privacy"]["raw_audio_retained"] is False


def test_system_privacy_and_policy_endpoints():
    r_priv = client.get("/system/privacy")
    assert r_priv.status_code == 200
    priv = r_priv.json()
    assert priv["raw_audio_retained"] is False
    assert priv["embeddings_protected"] is True

    r_pol = client.get("/system/policy")
    assert r_pol.status_code == 200
    pol = r_pol.json()
    assert pol["weights"]["authenticity"] == 0.50
    assert pol["weights"]["identity"] == 0.25
    assert pol["weights"]["context"] == 0.25
    assert pol["thresholds"]["suspicious"] == 40
    assert pol["thresholds"]["high"] == 65
    assert pol["thresholds"]["critical"] == 85
