"""Speech-to-text (STT) package for Dhwani AI."""

from app.ml.stt.provider import STTProvider, TranscriptionResult
from app.ml.stt.deepgram import DeepgramSTTProvider
from app.ml.stt.whisper import FasterWhisperSTTProvider
from app.ml.stt.factory import get_stt_provider, reset_stt_provider

__all__ = [
    "STTProvider",
    "TranscriptionResult",
    "DeepgramSTTProvider",
    "FasterWhisperSTTProvider",
    "get_stt_provider",
    "reset_stt_provider",
]
