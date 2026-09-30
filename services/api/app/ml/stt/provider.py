"""
Abstract base class and data model for Speech-to-Text (STT) providers.
Supports both cloud streaming (Deepgram) and local offline inference (faster-whisper).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class TranscriptionResult:
    text: str
    language: str = "en"
    language_probability: float = 1.0
    confidence: float = 1.0
    inference_ms: float = 0.0
    model_name: str = "deepgram-nova-2"
    model_version: str = "v1"
    provider: str = "deepgram"
    is_final: bool = True
    provider_status: str = "active"


class STTProvider(ABC):
    """Unified interface for live chunk and pre-recorded audio file transcription."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier (e.g. 'deepgram', 'faster_whisper')."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether valid credentials and runtime dependencies are available."""
        pass

    @abstractmethod
    async def transcribe_chunk(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> Optional[TranscriptionResult]:
        """Transcribe a window of float32/int16 PCM audio asynchronously."""
        pass

    @abstractmethod
    def transcribe_chunk_sync(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> Optional[TranscriptionResult]:
        """Transcribe a window of float32/int16 PCM audio synchronously."""
        pass

    @abstractmethod
    async def transcribe_file(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> Optional[TranscriptionResult]:
        """Transcribe pre-recorded audio file bytes asynchronously."""
        pass

    @abstractmethod
    def transcribe_file_sync(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> Optional[TranscriptionResult]:
        """Transcribe pre-recorded audio file bytes synchronously."""
        pass

