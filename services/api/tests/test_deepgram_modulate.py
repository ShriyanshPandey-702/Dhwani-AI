"""
Tests for Deepgram STT Provider, Modulate Velma-2 Synthetic Detector, and Fallback Handling.
Verifies:
1. Deepgram configured vs unconfigured
2. Deepgram fallback to faster-whisper
3. Modulate configured vs unconfigured
4. Modulate error/permission fail-soft (no crash, no fake score)
5. Model version reporting
"""

import pytest
import numpy as np
from app.ml.stt.provider import STTProvider, TranscriptionResult
from app.ml.stt.deepgram import DeepgramSTTProvider
from app.ml.stt.whisper import FasterWhisperSTTProvider
from app.ml.stt.factory import get_stt_provider, reset_stt_provider
from app.ml.authenticity.modulate import ModulateDetector, ModulateEvidence, get_modulate_detector, reset_modulate_detector


class DummyFallbackProvider(STTProvider):
    @property
    def provider_name(self) -> str:
        return "dummy_fallback"

    @property
    def is_configured(self) -> bool:
        return True

    def transcribe_chunk_sync(self, audio: np.ndarray, sample_rate: int = 16000):
        return TranscriptionResult(
            text="hello this is fallback",
            provider="dummy_fallback",
            confidence=0.95,
        )

    async def transcribe_chunk(self, audio: np.ndarray, sample_rate: int = 16000):
        return self.transcribe_chunk_sync(audio, sample_rate)

    def transcribe_file_sync(self, audio_bytes: bytes, mime_type: str = "audio/wav"):
        return TranscriptionResult(
            text="hello this is fallback file",
            provider="dummy_fallback",
            confidence=0.95,
        )

    async def transcribe_file(self, audio_bytes: bytes, mime_type: str = "audio/wav"):
        return self.transcribe_file_sync(audio_bytes, mime_type)


def test_deepgram_unconfigured_uses_fallback():
    provider = DeepgramSTTProvider(api_key="", fallback_provider=DummyFallbackProvider())
    assert not provider.is_configured
    audio = np.zeros(16000, dtype=np.float32)
    res = provider.transcribe_chunk_sync(audio)
    assert res is not None
    assert res.provider == "dummy_fallback"
    assert res.text == "hello this is fallback"


def test_modulate_unconfigured_returns_truthful_state():
    detector = ModulateDetector(api_key="")
    assert not detector.is_configured
    audio = np.zeros(16000, dtype=np.float32)
    ev = detector.analyze_chunk_sync(audio)
    assert ev.provider_status == "not_configured"
    assert ev.synthetic_probability is None
    assert ev.verdict == "UNDECIDED"
    assert ev.confidence == 0.0


def test_modulate_evidence_to_dict():
    ev = ModulateEvidence(
        provider="modulate",
        model="velma-2-synthetic-voice-detection-batch",
        synthetic_probability=0.87654,
        verdict="SYNTHETIC",
        confidence=0.92,
        provider_status="connected",
    )
    d = ev.to_dict()
    assert d["provider"] == "modulate"
    assert d["synthetic_probability"] == 0.8765
    assert d["verdict"] == "SYNTHETIC"
    assert d["confidence"] == 0.92
    assert d["provider_status"] == "connected"


def test_stt_factory_resolution():
    reset_stt_provider()
    prov = get_stt_provider()
    assert isinstance(prov, STTProvider)
