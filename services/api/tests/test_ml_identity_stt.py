"""
Real identity (ECAPA-TDNN) and STT (faster-whisper) seams.

Model-dependent tests skip cleanly when the library or weights are absent, so
the suite still runs on a machine that has not fetched models.
"""

from pathlib import Path

import numpy as np
import pytest

from app.ml.context.classifier import ContextClassifier
from app.ml.context.transcriber import (
    DEMO_TRANSCRIPT, HEURISTIC_DEMO, HEURISTIC_FALLBACK, REAL_ML, Transcriber,
)
from app.ml.identity.speaker import (
    MISMATCH, NOT_ENROLLED, VERIFIED, SpeakerIdentity,
)

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
SR = 16000


def _read(name: str) -> np.ndarray:
    import soundfile as sf

    path = FIXTURES / name
    if not path.is_file():
        pytest.skip(f"fixture {name} missing")
    audio, sr = sf.read(path, dtype="float32")
    assert sr == SR
    return audio


@pytest.fixture(scope="module")
def voice_a() -> np.ndarray:
    return _read("tts_synthetic_16k.wav")


@pytest.fixture(scope="module")
def voice_b() -> np.ndarray:
    return _read("tts_synthetic_16k_b.wav")


def _real_identity() -> SpeakerIdentity:
    identity = SpeakerIdentity(pipeline_mode=REAL_ML)
    if not identity.is_real_ml:
        pytest.skip(f"ECAPA unavailable: {identity.fallback_reason}")
    return identity


# ── Identity: demo backend regression ─────────────────────────────────────────

def test_demo_identity_backend_is_unchanged(voice_a):
    identity = SpeakerIdentity(pipeline_mode=HEURISTIC_DEMO)
    assert identity.is_real_ml is False
    assert identity.model_name == "spectral-fingerprint"
    assert identity.enroll("s", voice_a) is True
    result = identity.analyze("s", voice_a)
    assert result.enrollment_status == VERIFIED
    assert result.is_mock is True


def test_identity_without_enrolment_reports_the_gap(voice_a):
    identity = SpeakerIdentity(pipeline_mode=HEURISTIC_DEMO)
    result = identity.analyze("never-enrolled", voice_a)
    assert result.enrollment_status == NOT_ENROLLED
    assert result.match_score == 0 and result.confidence == 0.0


# ── Identity: real ECAPA ──────────────────────────────────────────────────────

def test_ecapa_matches_the_same_speaker_on_unseen_audio(voice_a):
    identity = _real_identity()
    half = len(voice_a) // 2
    assert identity.enroll("s", voice_a[:half]) is True
    result = identity.analyze("s", voice_a[half:])
    assert result.is_mock is False
    assert result.pipeline_mode == REAL_ML
    assert result.model_name == "ECAPA-TDNN"
    assert result.enrollment_status == VERIFIED
    assert result.similarity > 0.5


def test_ecapa_separates_a_different_speaker(voice_a, voice_b):
    """A different voice must score materially lower than the enrolled one."""
    identity = _real_identity()
    identity.enroll("s", voice_a[: len(voice_a) // 2])
    same = identity.analyze("s", voice_a[len(voice_a) // 2:])
    other = identity.analyze("s", voice_b)
    assert same.similarity > other.similarity
    assert other.enrollment_status == MISMATCH


def test_identity_evidence_never_exposes_the_embedding(voice_a):
    """PRIVACY: embeddings stay in memory and out of evidence entirely."""
    identity = _real_identity()
    identity.enroll("s", voice_a)
    emitted = identity.analyze("s", voice_a).to_dict()
    assert not any(k in emitted for k in ("embedding", "vector", "features"))
    for value in emitted.values():
        assert not isinstance(value, (list, tuple, np.ndarray)), \
            "no array-shaped field may appear in identity evidence"


def test_clearing_a_session_drops_the_enrolment(voice_a):
    identity = _real_identity()
    identity.enroll("s", voice_a)
    assert identity.is_enrolled("s") is True
    identity.clear("s")
    assert identity.is_enrolled("s") is False
    assert identity.analyze("s", voice_a).enrollment_status == NOT_ENROLLED


def test_identity_evidence_carries_no_authenticity_or_context(voice_a):
    """Stream independence — a mismatch must not imply synthesis."""
    identity = SpeakerIdentity(pipeline_mode=HEURISTIC_DEMO)
    identity.enroll("s", voice_a)
    emitted = identity.analyze("s", voice_a).to_dict()
    for leaked in ("spoof_probability", "acoustic_anomaly", "otp_request", "transcript"):
        assert leaked not in emitted


def test_identity_falls_back_with_a_reason_when_unavailable(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "MODEL_DIR", "/nonexistent")
    monkeypatch.setattr(
        "app.ml.identity.ecapa.ECAPAEmbedder.warmup",
        lambda self: (_ for _ in ()).throw(RuntimeError("simulated load failure")),
    )
    identity = SpeakerIdentity(pipeline_mode=REAL_ML)
    assert identity.is_real_ml is False
    assert identity.pipeline_mode == HEURISTIC_FALLBACK
    assert identity.fallback_reason


# ── STT: demo backend regression ──────────────────────────────────────────────

def test_scripted_transcript_sequence_is_unchanged():
    transcriber = Transcriber(pipeline_mode=HEURISTIC_DEMO)
    audio = np.random.default_rng(0).standard_normal(16000).astype(np.float32) * 0.1
    assert transcriber.transcribe("s", audio).text == DEMO_TRANSCRIPT[0]
    assert transcriber.transcribe("s", audio).text == DEMO_TRANSCRIPT[1]
    assert transcriber.is_real_ml is False


def test_scripted_transcript_is_labelled_mock():
    transcriber = Transcriber(pipeline_mode=HEURISTIC_DEMO)
    segment = transcriber.transcribe("s", np.ones(16000, dtype=np.float32) * 0.1)
    assert segment.is_mock is True
    assert segment.pipeline_mode == HEURISTIC_DEMO


def test_transcriber_ignores_too_little_audio():
    transcriber = Transcriber(pipeline_mode=HEURISTIC_DEMO)
    assert transcriber.transcribe("s", None) is None
    assert transcriber.transcribe("s", np.zeros(100, dtype=np.float32)) is None


# ── STT: real Whisper ─────────────────────────────────────────────────────────

def _real_transcriber() -> Transcriber:
    transcriber = Transcriber(pipeline_mode=REAL_ML)
    if not transcriber.is_real_ml:
        pytest.skip(f"faster-whisper unavailable: {transcriber.fallback_reason}")
    return transcriber


def test_whisper_transcribes_real_audio_with_language_metadata(voice_a):
    segment = _real_transcriber().transcribe("s", voice_a)
    assert segment is not None
    assert segment.is_mock is False
    assert segment.pipeline_mode == REAL_ML
    assert segment.model_name == "faster-whisper"
    assert segment.language == "en"
    assert 0.0 <= segment.confidence <= 1.0
    assert segment.inference_ms > 0
    assert len(segment.text) > 10


def test_whisper_output_is_not_the_scripted_transcript(voice_a):
    """Proves the transcript came from audio, not the demo script."""
    segment = _real_transcriber().transcribe("s", voice_a)
    assert segment.text not in DEMO_TRANSCRIPT


def test_whisper_returns_none_for_silence():
    transcriber = _real_transcriber()
    assert transcriber.transcribe("s", np.zeros(SR * 3, dtype=np.float32)) is None


# ── Context consumes the real transcript ──────────────────────────────────────

def test_context_rules_fire_on_a_real_transcript(voice_a):
    """The rules are unchanged; only their input source became real."""
    segment = _real_transcriber().transcribe("s", voice_a)
    result = ContextClassifier().classify(
        "s", segment.text,
        transcript_is_mock=segment.is_mock,
        transcript_model=segment.model_name,
        transcript_pipeline_mode=segment.pipeline_mode,
        transcript_language=segment.language,
        transcript_confidence=segment.confidence,
    )
    assert result is not None
    assert result.otp_request is True, f"expected an OTP signal in: {segment.text!r}"
    assert result.transcript_is_mock is False
    assert result.transcript_model == "faster-whisper"
    assert result.transcript_language == "en"
    assert result.consequence == "critical"


def test_context_records_transcript_provenance_in_demo_mode():
    result = ContextClassifier().classify("s", "Please read me the OTP")
    assert result.transcript_is_mock is True
    assert result.transcript_model == "scripted-stt"
    assert result.is_mock is False   # the RULES are real either way


def test_context_evidence_carries_no_authenticity_fields():
    result = ContextClassifier().classify("s", "Please transfer the money now").to_dict()
    for leaked in ("spoof_probability", "acoustic_anomaly", "match_score", "similarity"):
        assert leaked not in result
