"""
Factory for obtaining the active STT provider based on application settings.
"""

from __future__ import annotations

from typing import Optional
from app.core.config import settings
from app.ml.stt.provider import STTProvider
from app.ml.stt.deepgram import DeepgramSTTProvider
from app.ml.stt.whisper import FasterWhisperSTTProvider

_active_provider: Optional[STTProvider] = None


def get_stt_provider() -> STTProvider:
    """Return the configured STT provider (Deepgram with fallback, or FasterWhisper)."""
    global _active_provider
    if _active_provider is not None:
        return _active_provider

    if settings.STT_PROVIDER.lower() == "deepgram" and settings.DEEPGRAM_API_KEY:
        _active_provider = DeepgramSTTProvider(api_key=settings.DEEPGRAM_API_KEY)
    else:
        _active_provider = FasterWhisperSTTProvider()

    return _active_provider


def reset_stt_provider() -> None:
    """Reset provider instance for testing or configuration changes."""
    global _active_provider
    _active_provider = None
