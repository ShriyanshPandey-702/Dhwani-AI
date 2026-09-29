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

# Module-level VAD imports — optional; None when faster_whisper is not installed.
# Defined at module level so tests can patch `app.ml.context.whisper.get_speech_timestamps`.
try:
    from faster_whisper.vad import get_speech_timestamps, VadOptions as VadOptions
except Exception:
    get_speech_timestamps = None  # type: ignore[assignment]
    VadOptions = None  # type: ignore[assignment]


SAMPLE_RATE = 16000
MIN_SAMPLES = int(SAMPLE_RATE * 1.0)
# Below this mean power a window carries no speech worth transcribing.
MIN_SPEECH_ENERGY = 1e-5

# ── Hallucination guard thresholds (Demo Stabilization) ──────────────────
#
# 1. no_speech_prob: faster-whisper's model-internal estimate that a segment
#    is noise rather than speech.  Values above the ceiling are discarded.
#    Tightened from 0.6 → 0.40 for whisper-tiny on phone microphone audio;
#    the tiny model is more prone to hallucination on near-threshold audio.
#    Raise only with calibration data from in-domain (Indian-English mic).
_NO_SPEECH_PROB_CEIL = 0.40

# 2. avg_logprob floor: per-segment average decoder log-probability.
#    Segments below this threshold are very-low-confidence; on whisper-tiny
#    they almost always represent hallucinated text on ambient noise.
#    -1.0 allows the model some room for foreign-language or accented speech.
_MIN_AVG_LOGPROB = -1.0

# 3. Minimum VAD-confirmed speech duration before decoding.
#    If the faster_whisper VAD finds fewer than this many samples of confirmed
#    speech in the window, we skip the decode entirely and return None.
#    500 ms at 16 kHz = 8000 samples.
_MIN_SPEECH_SAMPLES = int(SAMPLE_RATE * 0.50)


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

        Returns None when:
        - Audio is too short
        - Window energy is below the silence threshold
        - VAD-confirmed speech is below the minimum required duration
        - All decoded segments are classified as non-speech
        - All decoded segments have avg_logprob below the quality floor
        - No text remains after filtering

        An empty or low-confidence transcript is never passed off as real speech.
        This guards against Whisper-tiny hallucination on ambient mic noise.
        """
        if audio is None or len(audio) < MIN_SAMPLES:
            log.debug("whisper.skip.too_short", samples=len(audio) if audio is not None else 0)
            return None

        # Silence gate: below minimum energy, do not invoke the model.
        rms_sq = float(np.mean(np.asarray(audio, dtype=np.float64) ** 2))
        if rms_sq < MIN_SPEECH_ENERGY:
            log.debug("whisper.skip.silence", rms_sq=rms_sq)
            return None

        # ── Pre-decode VAD: require sufficient confirmed-speech duration ──────
        # If the faster_whisper VAD finds fewer than _MIN_SPEECH_SAMPLES of
        # confirmed speech, decoding would run on near-silence and almost
        # certainly hallucinate. Skip it and report no transcript instead.
        # get_speech_timestamps is the module-level import (patchable in tests).
        if get_speech_timestamps is not None and VadOptions is not None:
            try:
                audio_f32 = np.ascontiguousarray(audio, dtype=np.float32)
                timestamps = get_speech_timestamps(audio_f32, VadOptions())
                confirmed_samples = sum(ts["end"] - ts["start"] for ts in timestamps)
                if confirmed_samples < _MIN_SPEECH_SAMPLES:
                    log.info(
                        "whisper.skip.insufficient_speech",
                        confirmed_ms=round(confirmed_samples / SAMPLE_RATE * 1000),
                        required_ms=round(_MIN_SPEECH_SAMPLES / SAMPLE_RATE * 1000),
                    )
                    return None
            except Exception as e:
                # VAD error: fall through to energy-based gate that already passed.
                log.debug("whisper.vad_error", error=str(e))


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

        # Guard 1: discard segments the model itself classifies as non-speech.
        # no_speech_prob > ceiling = hallucination on near-threshold audio.
        n_before = len(collected)
        collected = [
            s for s in collected
            if not (hasattr(s, "no_speech_prob") and s.no_speech_prob > _NO_SPEECH_PROB_CEIL)
        ]
        if len(collected) < n_before:
            log.info(
                "whisper.dropped_no_speech",
                dropped=n_before - len(collected),
                kept=len(collected),
            )

        # Guard 2: discard very-low-confidence segments (logprob floor).
        # These are most likely hallucinations on noise or very faint audio.
        n_before = len(collected)
        collected = [
            s for s in collected
            if not (s.avg_logprob is not None and s.avg_logprob < _MIN_AVG_LOGPROB)
        ]
        if len(collected) < n_before:
            log.info(
                "whisper.dropped_low_logprob",
                dropped=n_before - len(collected),
                kept=len(collected),
                floor=_MIN_AVG_LOGPROB,
            )

        text = " ".join(s.text.strip() for s in collected).strip()
        if not text:
            log.info("whisper.empty_after_filtering", elapsed_ms=round(elapsed, 1))
            return None

        logprobs = [s.avg_logprob for s in collected if s.avg_logprob is not None]
        confidence = (
            _confidence_from_logprob(float(np.mean(logprobs))) if logprobs else 0.0
        )

        log.info(
            "whisper.transcribed",
            chars=len(text),
            lang=getattr(info, "language", ""),
            conf=round(confidence, 3),
            elapsed_ms=round(elapsed, 1),
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
