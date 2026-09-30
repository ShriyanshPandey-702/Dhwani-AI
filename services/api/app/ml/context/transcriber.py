"""
Speech-to-Text — front half of EVIDENCE STREAM 3.

Selects a transcription backend and reports which one produced each segment:

  pipeline_mode = "real_ml"            faster-whisper transcribed real audio.
  pipeline_mode = "heuristic_demo"     Scripted transcript for the demo.
  pipeline_mode = "heuristic_fallback" real_ml requested but unavailable.

The transcript SOURCE and the contextual RISK derived from it are separate
concepts: `classifier.py` applies the same rules whichever backend produced the
text, and records the provenance alongside.

╔══════════════════════════════════════════════════════════════════════════╗
║  STATUS: MOCK / STUB. No speech recognition happens here.                ║
║                                                                          ║
║  PLANNED (Phase 3): faster-whisper (CTranslate2) streaming transcription ║
║  with a rolling context buffer, replacing this class outright.           ║
╚══════════════════════════════════════════════════════════════════════════╝

For the prototype this returns scripted utterances from a demo transcript so
that the downstream NLP classifier — which IS real and rule-based — can be
exercised end to end. Every result is flagged `is_mock=True` and the backend
propagates that flag to the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import structlog

from app.core.config import settings

log = structlog.get_logger()

REAL_ML = "real_ml"
HEURISTIC_DEMO = "heuristic_demo"
HEURISTIC_FALLBACK = "heuristic_fallback"


@dataclass
class TranscriptSegment:
    text: str
    is_mock: bool
    model_version: str
    # Added for real ML integration.
    model_name: str = "scripted-stt"
    pipeline_mode: str = HEURISTIC_DEMO
    language: str = ""
    language_probability: float = 0.0
    confidence: float = 0.0
    inference_ms: float = 0.0


# A scripted social-engineering call, used only when no real STT is wired up.
DEMO_TRANSCRIPT: List[str] = [
    "Hello, am I speaking with the account holder?",
    "This is Rajesh from the corporate finance team.",
    "I'm calling about an urgent matter, please stay on the line.",
    "We need to process a vendor payment before the cut-off today.",
    "Please transfer five lakh rupees to the account I'm about to give you.",
    "This is time sensitive, the director has already approved it.",
    "I'm sending an OTP now, please read it back to me.",
    "Do not discuss this with anyone else, it is confidential.",
    "Just confirm the OTP and I will complete the transfer.",
]


class Transcriber:
    """Scripted stand-in for faster-whisper streaming transcription."""

    MODEL_VERSION = "scripted-stt-stub-v0.2"
    IS_MOCK = True
    MIN_SAMPLES = 4000

    def __init__(self, pipeline_mode: Optional[str] = None):
        # session_id → index into DEMO_TRANSCRIPT
        self._cursor: Dict[str, int] = {}
        self._whisper = None
        self._mode = HEURISTIC_DEMO
        self._fallback_reason: Optional[str] = None

        if (pipeline_mode or settings.PIPELINE_MODE) == REAL_ML:
            self._init_real_ml()

    def _init_real_ml(self) -> None:
        try:
            from app.ml.stt.factory import get_stt_provider
            self._stt_provider = get_stt_provider()
            self._mode = REAL_ML
            log.info("stt.backend", mode=REAL_ML, provider=self._stt_provider.provider_name)
        except Exception as e:
            self._mode = HEURISTIC_FALLBACK
            self._fallback_reason = str(e)
            log.warning("stt.fallback", reason=str(e))

    @property
    def pipeline_mode(self) -> str:
        return self._mode

    @property
    def is_real_ml(self) -> bool:
        return self._mode == REAL_ML

    @property
    def model_name(self) -> str:
        if self.is_real_ml and hasattr(self, "_stt_provider") and self._stt_provider:
            return self._stt_provider.provider_name
        return "scripted-stt"

    @property
    def model_version(self) -> str:
        if self.is_real_ml and hasattr(self, "_stt_provider") and self._stt_provider:
            return f"{self._stt_provider.provider_name}-v1"
        return self.MODEL_VERSION

    @property
    def fallback_reason(self) -> Optional[str]:
        return self._fallback_reason

    def transcribe(
        self,
        session_id: str,
        audio: Optional[np.ndarray],
    ) -> Optional[TranscriptSegment]:
        """
        Transcribe the audio segment using the configured provider (Deepgram or faster-whisper),
        or return scripted utterances if in demo/mock mode.
        """
        if audio is None or len(audio) < self.MIN_SAMPLES:
            return None

        if self.is_real_ml and hasattr(self, "_stt_provider") and self._stt_provider is not None:
            try:
                res = self._stt_provider.transcribe_chunk_sync(audio)
                if res is None or not res.text.strip():
                    return None
                return TranscriptSegment(
                    text=res.text,
                    is_mock=False,
                    model_version=res.model_version,
                    model_name=res.model_name,
                    pipeline_mode=REAL_ML,
                    language=res.language,
                    language_probability=res.language_probability,
                    confidence=res.confidence,
                    inference_ms=res.inference_ms,
                )
            except Exception as e:
                log.warning("stt.inference_failed", error=str(e))
                return self._scripted(session_id, mode=HEURISTIC_FALLBACK)

        return self._scripted(session_id, mode=self._mode)

    def _scripted(self, session_id: str, mode: str) -> TranscriptSegment:
        idx = self._cursor.get(session_id, 0)
        if idx >= len(DEMO_TRANSCRIPT):
            # Hold on the final utterance rather than looping the script.
            idx = len(DEMO_TRANSCRIPT) - 1
        else:
            self._cursor[session_id] = idx + 1

        return TranscriptSegment(
            text=DEMO_TRANSCRIPT[idx],
            is_mock=True,
            model_version=self.MODEL_VERSION,
            model_name="scripted-stt",
            pipeline_mode=mode,
        )

    def reset(self, session_id: str) -> None:
        self._cursor.pop(session_id, None)
