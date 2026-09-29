"""
Real speech-to-text — faster-whisper backend (front half of EVIDENCE STREAM 3).

STATUS: REAL MODEL, PRETRAINED CHECKPOINT, NOT EVALUATED BY US.

  Model      Whisper via faster-whisper (CTranslate2 runtime)
  Source     Systran/faster-whisper-* on Hugging Face, fetched by the library
  Licence    MIT (faster-whisper); Whisper weights MIT (OpenAI)
  Input      16 kHz mono float32
  Output     transcript text, detected language, per-segment avg log-probability

What this is NOT:
  * Not fine-tuned by Dhwani AI.
  * Not evaluated for Indian-English, Hindi or code-mixed Hinglish accuracy.
    Whisper supports many languages; that is not the same as being production
    ready for them, and no such claim is made here.
  * `avg_logprob` is a decoder statistic, not a calibrated confidence.

Transcription runs on the same rolling analysis window the other streams use —
chunked window transcription, not a streaming ASR with cross-window context.

PRIVACY: audio is passed in memory as an array; no temporary WAV is written and
no raw audio is retained. Transcript text is not logged.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import structlog

log = structlog.get_logger()

SAMPLE_RATE = 16000
MIN_SAMPLES = int(SAMPLE_RATE * 1.0)
# Below this mean power a window carries no speech worth transcribing.
MIN_SPEECH_ENERGY = 1e-5

# Provisional no-speech probability ceiling (Phase 5.7).
# faster-whisper exposes ``segment.no_speech_prob`` — the model's own estimate
# that a decoded segment is noise rather than speech.  Segments above this
# ceiling are discarded before the text reaches the context classifier.
#
# 0.6 was chosen conservatively: it suppresses clearly non-speech segments
# while leaving room for legitimate low-confidence transcriptions.  Calibrate
# from in-domain (Indian-English phone-mic) held-out data before tightening.
# The check is attribute-safe; older faster-whisper versions that do not
# expose the field are unaffected.
_NO_SPEECH_PROB_CEIL = 0.6


class TranscriberUnavailable(RuntimeError):
    """Raised when the Whisper runtime or weights cannot be loaded."""


@dataclass
class Transcription:
    text: str
    language: str
    language_probability: float
    confidence: float          # from avg_logprob; uncalibrated
    inference_ms: float
    model_name: str
    model_version: str


def _confidence_from_logprob(avg_logprob: float) -> float:
    """
    Map a decoder average log-probability onto 0–1.

    This is a monotonic convenience transform for display and for the evidence
    confidence signal — deliberately capped, and not a calibrated probability
    that the transcript is correct.
    """
    return float(np.clip(np.exp(avg_logprob), 0.0, 1.0))


class WhisperTranscriber:
    """Local chunked transcription over the rolling analysis window."""

    MODEL_NAME = "faster-whisper"

    def __init__(
        self,
        model_size: str = "tiny",
        compute_type: str = "int8",
        language: str = "",
        beam_size: int = 1,
        download_root: str = "models/whisper",
    ):
        self.model_size = model_size
        self.compute_type = compute_type
        self.language = language or None
        self.beam_size = max(1, beam_size)
        self.download_root = download_root
        self._model = None

    @property
    def model_version(self) -> str:
        return f"whisper-{self.model_size}-{self.compute_type}"

    @property
    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise TranscriberUnavailable(f"faster-whisper not installed: {e}") from e
        try:
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
        except Exception as e:
            raise TranscriberUnavailable(
                f"could not load whisper '{self.model_size}': {e}"
            ) from e
        log.info("whisper.loaded", size=self.model_size, compute_type=self.compute_type)
        return self._model

    def warmup(self) -> None:
        model = self._load()
        list(model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32), beam_size=1)[0])

    def transcribe(self, audio: Optional[np.ndarray]) -> Optional[Transcription]:
        """
        Transcribe one analysis window.

        Returns None when there is too little audio, or when the model produced
        no speech — an empty transcript is not passed off as a real utterance.
        """
        if audio is None or len(audio) < MIN_SAMPLES:
            return None

        # Silence is not speech. Gate it here rather than letting the VAD find
        # nothing and raise — and never let a silent window be reported as an
        # utterance.
        if float(np.mean(np.asarray(audio, dtype=np.float64) ** 2)) < MIN_SPEECH_ENERGY:
            return None

        model = self._load()
        started = time.perf_counter()
        try:
            segments, info = model.transcribe(
                np.ascontiguousarray(audio, dtype=np.float32),
                beam_size=self.beam_size,
                language=self.language,
                vad_filter=True,
            )
            collected = list(segments)
        except ValueError:
            # The VAD found no speech regions. That is "nothing was said", not
            # a model failure, so report no transcript rather than falling back.
            return None
        elapsed = (time.perf_counter() - started) * 1000.0

        # Phase 5.7: discard segments the model itself classifies as non-speech.
        # no_speech_prob is the probability the segment is noise; segments above
        # the ceiling are hallucinations on near-threshold audio and must not
        # reach the context classifier (where keyword matches are sticky).
        # The attribute check is safe against older faster-whisper releases.
        collected = [
            s for s in collected
            if not (hasattr(s, "no_speech_prob") and s.no_speech_prob > _NO_SPEECH_PROB_CEIL)
        ]

        text = " ".join(s.text.strip() for s in collected).strip()
        if not text:
            return None

        logprobs = [s.avg_logprob for s in collected if s.avg_logprob is not None]
        confidence = (
            _confidence_from_logprob(float(np.mean(logprobs))) if logprobs else 0.0
        )

        return Transcription(
            text=text,
            language=getattr(info, "language", "") or "",
            language_probability=round(float(getattr(info, "language_probability", 0.0)), 3),
            confidence=round(confidence, 3),
            inference_ms=round(elapsed, 2),
            model_name=self.MODEL_NAME,
            model_version=self.model_version,
        )
