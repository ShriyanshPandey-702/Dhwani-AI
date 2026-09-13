"""
ML evidence streams — the deterministic demo backends.

Every detector here is constructed with an explicit demo mode so these tests
assert demo behaviour regardless of the ambient PIPELINE_MODE. Real-model
behaviour lives in test_ml_authenticity.py and test_ml_identity_stt.py.
"""

import numpy as np
import pytest

from app.ml.authenticity.detector import HEURISTIC_DEMO, AuthenticityDetector
from app.ml.context.classifier import ContextClassifier
from app.ml.context.transcriber import (
    HEURISTIC_DEMO as STT_DEMO, DEMO_TRANSCRIPT, Transcriber,
)
from app.ml.identity.speaker import HEURISTIC_DEMO as ID_DEMO, SpeakerIdentity
from app.ml.preprocessing.audio import (
    decode_pcm, extract_windows, measure_quality, preprocess_audio_chunk,
)
from app.simulation.mock_audio import generate_frame, generate_silence


# ── Preprocessing ─────────────────────────────────────────────────────────────

def test_decode_pcm_rejects_short_and_empty_buffers():
    assert decode_pcm(b"") is None
    assert decode_pcm(b"\x00\x01") is None


def test_decode_pcm_tolerates_an_odd_trailing_byte():
    audio = decode_pcm(generate_frame(0) + b"\x7f")
    assert audio is not None and audio.size > 0


def test_silence_is_gated_out_so_it_is_never_scored():
    assert preprocess_audio_chunk(generate_silence()) is None


def test_quality_reports_silence_as_poor():
    quality = measure_quality(decode_pcm(generate_silence()))
    assert quality.is_silent is True
    assert quality.quality == "POOR"


def test_quality_of_mock_speech_is_measurable():
    quality = measure_quality(preprocess_audio_chunk(generate_frame(0)))
    assert quality.is_silent is False
    assert quality.estimated_snr_db > 0
    assert quality.quality in {"GOOD", "FAIR", "POOR"}


def test_extract_windows_never_returns_partial_garbage():
    audio = np.zeros(16000 * 3, dtype=np.float32)
    windows = extract_windows(audio)
    assert len(windows) >= 1
    assert all(w.size > 0 for w in windows)


# ── Authenticity ──────────────────────────────────────────────────────────────

def test_authenticity_returns_none_for_insufficient_audio():
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    assert detector.analyze(None) is None
    assert detector.analyze(np.zeros(100, dtype=np.float32)) is None


def test_authenticity_is_flagged_as_a_stub():
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    result = detector.analyze(preprocess_audio_chunk(generate_frame(0)))
    assert result.is_mock is True
    assert "stub" in result.model_version


def test_authenticity_rises_with_synthetic_artefacts():
    """The scripted scenario degrades toward vocoded audio; the score must follow."""
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    early = detector.analyze(preprocess_audio_chunk(generate_frame(0, 12)))
    late = detector.analyze(preprocess_audio_chunk(generate_frame(11, 12)))
    assert late.spoof_probability > early.spoof_probability


def test_authenticity_outputs_are_within_contract_bounds():
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    for step in range(12):
        result = detector.analyze(preprocess_audio_chunk(generate_frame(step, 12)))
        assert 0 <= result.score <= 100
        assert 0.0 <= result.spoof_probability <= 1.0
        assert 0.0 <= result.confidence <= 1.0
        assert result.acoustic_anomaly in {"LOW", "MEDIUM", "HIGH"}
        assert result.spectral_anomaly in {"LOW", "MEDIUM", "HIGH"}
        assert result.prosody_anomaly in {"LOW", "MEDIUM", "HIGH"}


def test_authenticity_confidence_never_claims_certainty():
    detector = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    result = detector.analyze(preprocess_audio_chunk(generate_frame(11, 12)))
    assert result.confidence < 1.0


# ── Identity ──────────────────────────────────────────────────────────────────

def test_identity_without_enrolment_reports_no_reference():
    speaker = SpeakerIdentity(pipeline_mode=ID_DEMO)
    result = speaker.analyze("sess-a", preprocess_audio_chunk(generate_frame(0)))
    assert result.enrollment_status == "NOT_ENROLLED"
    assert result.match_score == 0
    assert result.confidence == 0.0


def test_identity_matches_the_same_voice_after_enrolment():
    speaker = SpeakerIdentity(pipeline_mode=ID_DEMO)
    audio = preprocess_audio_chunk(generate_frame(0))
    assert speaker.enroll("sess-b", audio) is True
    result = speaker.analyze("sess-b", audio)
    assert result.enrollment_status == "VERIFIED"
    assert result.match_score > 90


def test_identity_enrolment_rejects_too_little_audio():
    speaker = SpeakerIdentity(pipeline_mode=ID_DEMO)
    assert speaker.enroll("sess-c", np.zeros(10, dtype=np.float32)) is False
    assert speaker.is_enrolled("sess-c") is False


def test_identity_state_is_cleared_between_sessions():
    speaker = SpeakerIdentity(pipeline_mode=ID_DEMO)
    speaker.enroll("sess-d", preprocess_audio_chunk(generate_frame(0)))
    speaker.clear("sess-d")
    assert speaker.is_enrolled("sess-d") is False


# ── Context ───────────────────────────────────────────────────────────────────

def test_context_ignores_empty_transcripts():
    classifier = ContextClassifier()
    assert classifier.classify("s", None) is None
    assert classifier.classify("s", "   ") is None


@pytest.mark.parametrize("text,flag", [
    ("Please transfer five lakh rupees now", "financial_request"),
    ("Read me the OTP you just received", "otp_request"),
    ("What is your net banking password?", "credential_request"),
    ("This is urgent, do it immediately", "urgency"),
    ("Do not discuss this with anyone", "sensitive_information_request"),
    ("This is the director speaking", "authority_claim"),
])
def test_context_detects_each_signal(text, flag):
    classifier = ContextClassifier()
    result = classifier.classify("sess-ctx", text)
    assert getattr(result, flag) is True


def test_context_signals_are_sticky_across_a_call():
    """A caller who asked for an OTP does not become safe on the next sentence."""
    classifier = ContextClassifier()
    classifier.classify("sess-sticky", "Please read me the OTP.")
    later = classifier.classify("sess-sticky", "Lovely weather today.")
    assert later.otp_request is True


def test_social_engineering_needs_both_pressure_and_a_request():
    classifier = ContextClassifier()
    only_ask = classifier.classify("sess-ask", "Please transfer the payment.")
    assert only_ask.social_engineering is False

    classifier.classify("sess-ask", "This is urgent, the director approved it.")
    combined = classifier.classify("sess-ask", "Send it now.")
    assert combined.social_engineering is True


def test_context_consequence_escalates_with_the_ask():
    classifier = ContextClassifier()
    assert classifier.classify("s1", "Hello there").consequence == "low"
    assert classifier.classify("s2", "Please transfer the amount").consequence == "high"
    assert classifier.classify("s3", "Give me the OTP").consequence == "critical"


def test_context_rules_are_real_but_transcript_is_flagged_mock():
    classifier = ContextClassifier()
    result = classifier.classify("s", "Send the OTP", transcript_is_mock=True)
    assert result.is_mock is False          # the rules run for real
    assert result.transcript_is_mock is True  # the transcript does not


def test_context_state_resets_between_sessions():
    classifier = ContextClassifier()
    classifier.classify("sess-reset", "Give me the OTP")
    classifier.reset("sess-reset")
    fresh = classifier.classify("sess-reset", "Hello")
    assert fresh.otp_request is False


# ── Transcriber (stub) ────────────────────────────────────────────────────────

def test_transcriber_is_flagged_as_a_stub_and_advances():
    transcriber = Transcriber(pipeline_mode=STT_DEMO)
    audio = preprocess_audio_chunk(generate_frame(0))
    first = transcriber.transcribe("sess-t", audio)
    second = transcriber.transcribe("sess-t", audio)
    assert first.is_mock is True
    assert first.text == DEMO_TRANSCRIPT[0]
    assert second.text == DEMO_TRANSCRIPT[1]


def test_transcriber_returns_nothing_for_silence():
    transcriber = Transcriber(pipeline_mode=STT_DEMO)
    assert transcriber.transcribe("sess-t2", None) is None


def test_transcriber_holds_at_the_end_rather_than_looping():
    transcriber = Transcriber(pipeline_mode=STT_DEMO)
    audio = preprocess_audio_chunk(generate_frame(0))
    last = None
    for _ in range(len(DEMO_TRANSCRIPT) + 5):
        last = transcriber.transcribe("sess-t3", audio)
    assert last.text == DEMO_TRANSCRIPT[-1]
