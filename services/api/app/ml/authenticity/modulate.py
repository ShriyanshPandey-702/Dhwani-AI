"""
Modulate Velma-2 Synthetic Voice Detection Provider (Evidence Stream 1 Extension).

STATUS: THIRD-PARTY MULTI-MODAL SYNTHETIC DETECTION PROVIDER.
Contract: Velma-2 Streaming and REST Synthetic Voice Detection.

Integrates alongside the canonical local AASIST-L model without modifying
AASIST-L checkpoint weights, StreamWindower invariants, or risk fusion formulas.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
import httpx
import numpy as np
import soundfile as sf
import structlog

from app.core.config import settings

log = structlog.get_logger()

MODULATE_API_URL = "https://platform.modulate.ai/api/velma-2-synthetic-voice-detection-batch"


@dataclass
class ModulateEvidence:
    """Standardized evidence payload from Modulate Velma-2 detector."""
    provider: str = "modulate"
    model: str = "velma-2-synthetic-voice-detection-batch"
    synthetic_probability: Optional[float] = None
    verdict: str = "UNDECIDED"  # "synthetic" | "natural" | "no-content" | "UNDECIDED"
    confidence: float = 0.0
    window_start: float = 0.0
    window_duration: float = 4.0
    provider_status: str = "not_configured"  # "connected" | "not_configured" | "unavailable"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "synthetic_probability": (
                round(self.synthetic_probability, 4)
                if self.synthetic_probability is not None
                else None
            ),
            "verdict": self.verdict,
            "confidence": round(self.confidence, 4),
            "window_start": round(self.window_start, 2),
            "window_duration": round(self.window_duration, 2),
            "provider_status": self.provider_status,
        }


class ModulateDetector:
    """Client for Modulate Velma-2 synthetic voice detection."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key if api_key is not None else settings.MODULATE_API_KEY


    @property
    def is_configured(self) -> bool:
        return bool(self._api_key and self._api_key.strip())

    async def analyze_chunk(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        window_start: float = 0.0,
        window_duration: float = 4.0,
    ) -> ModulateEvidence:
        """Analyze a PCM float32/int16 chunk for synthetic voice likelihood."""
        if not self.is_configured:
            return ModulateEvidence(
                provider_status="not_configured",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )

        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        return await self.analyze_file(
            wav_bytes,
            mime_type="audio/wav",
            window_start=window_start,
            window_duration=window_duration,
        )

    def analyze_chunk_sync(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        window_start: float = 0.0,
        window_duration: float = 4.0,
    ) -> ModulateEvidence:
        """Synchronous version for thread-pool execution."""
        if not self.is_configured:
            return ModulateEvidence(
                provider_status="not_configured",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )

        buf = io.BytesIO()
        sf.write(buf, audio, sample_rate, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()

        return self.analyze_file_sync(
            wav_bytes,
            mime_type="audio/wav",
            window_start=window_start,
            window_duration=window_duration,
        )

    def analyze_file_sync(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        window_start: float = 0.0,
        window_duration: float = 4.0,
    ) -> ModulateEvidence:
        """Synchronous HTTP call to Modulate Velma-2 API."""
        if not self.is_configured:
            return ModulateEvidence(
                provider_status="not_configured",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )

        headers = {"X-API-Key": self._api_key.strip()}
        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.post(
                    MODULATE_API_URL,
                    headers=headers,
                    files={"upload_file": ("audio.wav", audio_bytes, mime_type)},
                )

            if resp.status_code == 200:
                data = resp.json()
                frames = data.get("frames", [])
                synth_probs = []
                verdict = "UNDECIDED"
                conf = 0.0
                if frames:
                    for f in frames:
                        v = f.get("verdict", "")
                        c = float(f.get("confidence", 0.0))
                        if v == "synthetic":
                            synth_probs.append(c)
                        elif v == "natural":
                            synth_probs.append(1.0 - c)
                        elif v == "no-content":
                            synth_probs.append(0.0)
                    if synth_probs:
                        avg_prob = sum(synth_probs) / len(synth_probs)
                        verdict = "SYNTHETIC" if avg_prob >= 0.65 else ("NATURAL" if avg_prob <= 0.35 else "UNDECIDED")
                        conf = float(frames[0].get("confidence", 0.90))
                        return ModulateEvidence(
                            synthetic_probability=avg_prob,
                            verdict=verdict,
                            confidence=conf,
                            window_start=window_start,
                            window_duration=window_duration,
                            provider_status="connected",
                        )

            log.warning(
                "modulate_api_non_200",
                status_code=resp.status_code,
                detail=resp.text[:200],
            )
            return ModulateEvidence(
                provider_status="unavailable",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )
        except Exception as exc:
            log.warning("modulate_detection_failed", error=str(exc))
            return ModulateEvidence(
                provider_status="unavailable",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )

    async def analyze_file(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
        window_start: float = 0.0,
        window_duration: float = 4.0,
    ) -> ModulateEvidence:
        """Async call to Modulate Velma-2 API."""
        if not self.is_configured:
            return ModulateEvidence(
                provider_status="not_configured",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )

        headers = {"X-API-Key": self._api_key.strip()}
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    MODULATE_API_URL,
                    headers=headers,
                    files={"upload_file": ("audio.wav", audio_bytes, mime_type)},
                )

            if resp.status_code == 200:
                data = resp.json()
                frames = data.get("frames", [])
                synth_probs = []
                if frames:
                    for f in frames:
                        v = f.get("verdict", "")
                        c = float(f.get("confidence", 0.0))
                        if v == "synthetic":
                            synth_probs.append(c)
                        elif v == "natural":
                            synth_probs.append(1.0 - c)
                        elif v == "no-content":
                            synth_probs.append(0.0)
                    if synth_probs:
                        avg_prob = sum(synth_probs) / len(synth_probs)
                        verdict = "SYNTHETIC" if avg_prob >= 0.65 else ("NATURAL" if avg_prob <= 0.35 else "UNDECIDED")
                        conf = float(frames[0].get("confidence", 0.90))
                        return ModulateEvidence(
                            synthetic_probability=avg_prob,
                            verdict=verdict,
                            confidence=conf,
                            window_start=window_start,
                            window_duration=window_duration,
                            provider_status="connected",
                        )

            log.warning(
                "modulate_api_non_200",
                status_code=resp.status_code,
                detail=resp.text[:200],
            )
            return ModulateEvidence(
                provider_status="unavailable",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )
        except Exception as exc:
            log.warning("modulate_detection_failed", error=str(exc))
            return ModulateEvidence(
                provider_status="unavailable",
                synthetic_probability=None,
                confidence=0.0,
                verdict="UNDECIDED",
                window_start=window_start,
                window_duration=window_duration,
            )


# Global singleton instance
_modulate_detector: Optional[ModulateDetector] = None


def get_modulate_detector() -> ModulateDetector:
    global _modulate_detector
    if _modulate_detector is None:
        _modulate_detector = ModulateDetector(api_key=settings.MODULATE_API_KEY)
    return _modulate_detector


def reset_modulate_detector() -> None:
    global _modulate_detector
    _modulate_detector = None
