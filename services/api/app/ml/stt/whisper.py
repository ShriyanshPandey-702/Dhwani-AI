"""
Local offline faster-whisper STT provider implementation.
Acts as the fallback when cloud providers are unavailable or unconfigured.
"""

from __future__ import annotations

import io
import time
from typing import Optional
import numpy as np
import soundfile as sf
import structlog

from app.core.config import settings
from app.ml.context.whisper import WhisperTranscriber, Transcription
from app.ml.stt.provider import STTProvider, TranscriptionResult

log = structlog.get_logger()


class FasterWhisperSTTProvider(STTProvider):
    """Local faster-whisper transcription provider."""

    def __init__(self, transcriber: Optional[WhisperTranscriber] = None) -> None:
        self._transcriber = transcriber

    @property
    def provider_name(self) -> str:
        return "faster_whisper"

    @property
    def is_configured(self) -> bool:
        return True

    def _get_transcriber(self) -> WhisperTranscriber:
        if self._transcriber is None:
            self._transcriber = WhisperTranscriber(
                model_size=settings.WHISPER_MODEL_SIZE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                language=settings.WHISPER_LANGUAGE or "",
                download_root=f"{settings.MODEL_DIR}/whisper",
            )
        return self._transcriber


    def transcribe_chunk_sync(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> Optional[TranscriptionResult]:
        t0 = time.perf_counter()
        try:
            transcriber = self._get_transcriber()
            res: Optional[Transcription] = transcriber.transcribe(audio)
            if not res or not res.text.strip():
                return None

            return TranscriptionResult(
                text=res.text.strip(),
                language=res.language,
                language_probability=res.language_probability,
                confidence=res.confidence,
                inference_ms=round((time.perf_counter() - t0) * 1000, 1),
                model_name=res.model_name,
                model_version=res.model_version,
                provider="faster_whisper",
                is_final=True,
                provider_status="active",
            )
        except Exception as exc:
            log.warning("faster_whisper_chunk_failed", error=str(exc))
            return None

    async def transcribe_chunk(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> Optional[TranscriptionResult]:
        return self.transcribe_chunk_sync(audio, sample_rate=sample_rate)

    def transcribe_file_sync(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> Optional[TranscriptionResult]:
        t0 = time.perf_counter()
        try:
            data, sr = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            if data.ndim > 1:
                data = data.mean(axis=1)

            if sr != 16000:
                import scipy.signal
                num_samples = int(len(data) * 16000 / sr)
                data = scipy.signal.resample(data, num_samples).astype(np.float32)

            return self.transcribe_chunk_sync(data, sample_rate=16000)
        except Exception as exc:
            log.warning("faster_whisper_file_failed", error=str(exc))
            return None

    async def transcribe_file(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> Optional[TranscriptionResult]:
        return self.transcribe_file_sync(audio_bytes, mime_type=mime_type)

