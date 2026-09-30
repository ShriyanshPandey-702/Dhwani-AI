"""
Deepgram Speech-to-Text provider implementation.
Performs real-time streaming and pre-recorded audio file transcription via Deepgram Nova-2 API.
Automatically falls back to local faster-whisper if credentials are missing or network fails.
"""

from __future__ import annotations

import io
import time
from typing import Optional
import httpx
import numpy as np
import soundfile as sf
import structlog

from app.core.config import settings
from app.ml.stt.provider import STTProvider, TranscriptionResult
from app.ml.stt.whisper import FasterWhisperSTTProvider

log = structlog.get_logger()

DEEPGRAM_API_URL = "https://api.deepgram.com/v1/listen"


class DeepgramSTTProvider(STTProvider):
    """Deepgram cloud transcription provider with automatic local fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        fallback_provider: Optional[STTProvider] = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.DEEPGRAM_API_KEY
        self._fallback = fallback_provider or FasterWhisperSTTProvider()


    @property
    def provider_name(self) -> str:
        return "deepgram"

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    def transcribe_chunk_sync(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> Optional[TranscriptionResult]:
        """Convert float32 PCM window to WAV and transcribe via Deepgram synchronously."""
        if not self.is_configured:
            return self._fallback.transcribe_chunk_sync(audio, sample_rate)

        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        return self.transcribe_file_sync(wav_bytes, mime_type="audio/wav")

    async def transcribe_chunk(
        self, audio: np.ndarray, sample_rate: int = 16000
    ) -> Optional[TranscriptionResult]:
        """Convert float32 PCM window to WAV and transcribe via Deepgram asynchronously."""
        if not self.is_configured:
            return await self._fallback.transcribe_chunk(audio, sample_rate)

        # Convert float32 array to 16-bit PCM WAV bytes
        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        return await self.transcribe_file(wav_bytes, mime_type="audio/wav")

    def transcribe_file_sync(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> Optional[TranscriptionResult]:
        """Transcribe audio file payload via Deepgram REST API synchronously."""
        if not self.is_configured:
            log.info("deepgram_not_configured_using_fallback")
            return self._fallback.transcribe_file_sync(audio_bytes, mime_type)

        t0 = time.perf_counter()
        headers = {
            "Authorization": f"Token {self._api_key.strip()}",
            "Content-Type": mime_type or "audio/wav",
        }
        params = {
            "model": "nova-2",
            "smart_format": "true",
            "punctuate": "true",
            "detect_language": "true",
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    DEEPGRAM_API_URL,
                    headers=headers,
                    params=params,
                    content=audio_bytes,
                )

            if resp.status_code == 200:
                data = resp.json()
                channels = data.get("results", {}).get("channels", [])
                if channels:
                    alts = channels[0].get("alternatives", [])
                    if alts:
                        top = alts[0]
                        transcript_text = top.get("transcript", "").strip()
                        conf = float(top.get("confidence", 1.0))
                        lang = top.get("languages", ["en"])[0] if top.get("languages") else "en"
                        return TranscriptionResult(
                            text=transcript_text,
                            language=lang,
                            language_probability=1.0,
                            confidence=conf,
                            inference_ms=round((time.perf_counter() - t0) * 1000, 1),
                            model_name="deepgram-nova-2",
                            model_version="2024-live",
                            provider="deepgram",
                            is_final=True,
                            provider_status="active",
                        )
                return None

            log.warning(
                "deepgram_request_non_200",
                status_code=resp.status_code,
                detail=resp.text[:200],
            )
        except Exception as exc:
            log.warning("deepgram_transcribe_exception", error=str(exc))

        # Seamless local fallback
        log.info("deepgram_fallback_to_faster_whisper")
        return self._fallback.transcribe_file_sync(audio_bytes, mime_type)

    async def transcribe_file(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> Optional[TranscriptionResult]:
        """Transcribe audio file payload via Deepgram REST API asynchronously."""
        if not self.is_configured:
            log.info("deepgram_not_configured_using_fallback")
            return await self._fallback.transcribe_file(audio_bytes, mime_type)

        t0 = time.perf_counter()
        headers = {
            "Authorization": f"Token {self._api_key.strip()}",
            "Content-Type": mime_type or "audio/wav",
        }
        params = {
            "model": "nova-2",
            "smart_format": "true",
            "punctuate": "true",
            "detect_language": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    DEEPGRAM_API_URL,
                    headers=headers,
                    params=params,
                    content=audio_bytes,
                )

            if resp.status_code == 200:
                data = resp.json()
                channels = data.get("results", {}).get("channels", [])
                if channels:
                    alts = channels[0].get("alternatives", [])
                    if alts:
                        top = alts[0]
                        transcript_text = top.get("transcript", "").strip()
                        conf = float(top.get("confidence", 1.0))
                        lang = top.get("languages", ["en"])[0] if top.get("languages") else "en"
                        return TranscriptionResult(
                            text=transcript_text,
                            language=lang,
                            language_probability=1.0,
                            confidence=conf,
                            inference_ms=round((time.perf_counter() - t0) * 1000, 1),
                            model_name="deepgram-nova-2",
                            model_version="2024-live",
                            provider="deepgram",
                            is_final=True,
                            provider_status="active",
                        )
                return None

            log.warning(
                "deepgram_request_non_200",
                status_code=resp.status_code,
                detail=resp.text[:200],
            )
        except Exception as exc:
            log.warning("deepgram_transcribe_exception", error=str(exc))

        # Seamless local fallback
        log.info("deepgram_fallback_to_faster_whisper")
        return await self._fallback.transcribe_file(audio_bytes, mime_type)

