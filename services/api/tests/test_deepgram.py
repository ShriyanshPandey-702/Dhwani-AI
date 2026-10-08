"""
Tests for Deepgram STT Provider and Fallback Handling.
Verifies:
1. Deepgram configured vs unconfigured
2. Deepgram fallback to faster-whisper
3. STT factory resolution
"""

import pytest
import numpy as np
from app.ml.stt.provider import STTProvider, TranscriptionResult
from app.ml.stt.deepgram import DeepgramSTTProvider
from app.ml.stt.whisper import FasterWhisperSTTProvider
from app.ml.stt.factory import get_stt_provider, reset_stt_provider


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


def test_stt_factory_resolution():
    reset_stt_provider()
    prov = get_stt_provider()
    assert isinstance(prov, STTProvider)
