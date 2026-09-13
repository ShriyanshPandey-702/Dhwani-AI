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
            from app.ml.context.whisper import WhisperTranscriber

            transcriber = WhisperTranscriber(
                model_size=settings.WHISPER_MODEL_SIZE,
                compute_type=settings.WHISPER_COMPUTE_TYPE,
                language=settings.WHISPER_LANGUAGE,
                beam_size=settings.WHISPER_BEAM_SIZE,
                download_root=f"{settings.MODEL_DIR}/whisper",
            )
            if not transcriber.is_available:
                raise RuntimeError("faster-whisper not installed")
            transcriber.warmup()
            self._whisper = transcriber
            self._mode = REAL_ML
            log.info("stt.backend", mode=REAL_ML, size=settings.WHISPER_MODEL_SIZE)
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
        return "faster-whisper" if self.is_real_ml else "scripted-stt"

    @property
    def model_version(self) -> str:
        return self._whisper.model_version if self.is_real_ml else self.MODEL_VERSION

    @property
    def fallback_reason(self) -> Optional[str]:
        return self._fallback_reason

    def transcribe(
        self,
        session_id: str,
        audio: Optional[np.ndarray],
    ) -> Optional[TranscriptSegment]:
        """
        Return the next scripted utterance for the session.

        Returns None when there is not enough audio, so silence never
        fabricates conversation context.
        """
        if audio is None or len(audio) < self.MIN_SAMPLES:
            return None

        if self._whisper is not None:
            try:
                spoken = self._whisper.transcribe(audio)
                if spoken is None:
                    return None      # no speech in this window
                return TranscriptSegment(
                    text=spoken.text,
                    is_mock=False,
                    model_version=spoken.model_version,
                    model_name=spoken.model_name,
                    pipeline_mode=REAL_ML,
                    language=spoken.language,
                    language_probability=spoken.language_probability,
                    confidence=spoken.confidence,
                    inference_ms=spoken.inference_ms,
                )
            except Exception as e:
                # One failed window must not end the call; fall back and say so.
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
