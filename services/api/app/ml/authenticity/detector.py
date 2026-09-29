"""
Voice Authenticity — EVIDENCE STREAM 1.

Selects an inference backend and reports, on every observation, which one
actually produced the number:

  pipeline_mode = "real_ml"            AASIST checkpoint ran. is_mock = False.
  pipeline_mode = "heuristic_demo"     Mock mode was deliberately chosen for
                                       the deterministic demonstration.
  pipeline_mode = "heuristic_fallback" real_ml was requested but the model
                                       could not be used. is_mock = True.

The last case matters most: a fallback is never presented as real ML. The
dashboard reads `is_mock` and `model_name`, so a fallback is visibly labelled.

This stream never reads speaker identity or conversation context. A caller
asking for an OTP is not evidence that the audio is synthetic, and an unknown
speaker is not evidence that the audio is synthetic. Fusion happens only in the
Risk Engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np
import structlog

from app.core.config import settings
from app.ml.authenticity import dsp
from app.ml.preprocessing.audio import MIN_SPEECH_ENERGY

log = structlog.get_logger()

SAMPLE_RATE = 16000

REAL_ML = "real_ml"
HEURISTIC_DEMO = "heuristic_demo"
HEURISTIC_FALLBACK = "heuristic_fallback"

# Re-exported so existing callers keep working.
LOW, MEDIUM, HIGH = dsp.LOW, dsp.MEDIUM, dsp.HIGH


@dataclass
class AuthenticityResult:
    """
    One authenticity observation.

    Field meanings (names kept stable for the existing wire contract):
      score              authenticity risk index, 0–100
      spoof_probability  synthetic probability, 0.0–1.0
      confidence         model/heuristic confidence, 0.0–1.0, never 1.0
    """

    score: int
    spoof_probability: float
    confidence: float
    acoustic_anomaly: str
    spectral_anomaly: str
    prosody_anomaly: str
    model_version: str
    is_mock: bool
    # Added for real ML integration.
    model_name: str = "heuristic-dsp"
    pipeline_mode: str = HEURISTIC_DEMO
    inference_ms: float = 0.0
    device: str = "cpu"
    # Calibration. `spoof_probability` above is ALWAYS the raw model score;
    # these fields are additive and never overwrite it.
    calibrated_spoof_probability: Optional[float] = None
    calibration_method: Optional[str] = None
    calibration_version: Optional[str] = None
    pitch: Optional[dict] = None
    prosody: Optional[dict] = None
    rhythm: Optional[dict] = None
    pause_analysis: Optional[dict] = None
    microvariation: Optional[dict] = None
    spectral_details: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


class HeuristicBackend:
    """
    DSP stand-in for a trained detector.

    The features are real measurements; what is absent is a trained model that
    turns them into a calibrated probability. Deterministic, which is why the
    demonstration uses it.
    """

    MODEL_NAME = "heuristic-dsp"
    MODEL_VERSION = "heuristic-dsp-stub-v0.3"

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate

    def score(self, audio: np.ndarray) -> tuple:
        acoustic = dsp.acoustic_anomaly(audio, self.sample_rate)
        spectral = dsp.spectral_anomaly(audio, self.sample_rate)
        prosody = dsp.prosody_anomaly(audio, self.sample_rate)

        spoof = float(np.clip(0.40 * acoustic + 0.35 * spectral + 0.25 * prosody, 0.0, 1.0))
        duration_s = len(audio) / self.sample_rate
        confidence = float(np.clip(0.35 + 0.20 * duration_s, 0.0, 0.80))
        return spoof, confidence


class AuthenticityDetector:
    """Facade over the available authenticity backends."""

    # Kept as class attributes for backwards compatibility; the instance
    # properties below report what is actually in use.
    MODEL_VERSION = HeuristicBackend.MODEL_VERSION
    IS_MOCK = True

    def __init__(self, sample_rate: int = SAMPLE_RATE, pipeline_mode: Optional[str] = None):
        self.sample_rate = sample_rate
        self.min_samples = int(sample_rate * settings.MIN_ANALYSIS_MS / 1000)
        self._heuristic = HeuristicBackend(sample_rate)
        self._aasist = None
        self._mode = HEURISTIC_DEMO
        self._fallback_reason: Optional[str] = None
        self._calibrator = None
        self._load_calibrator()

        requested = pipeline_mode or settings.PIPELINE_MODE
        if requested == REAL_ML:
            self._init_real_ml()

    def _load_calibrator(self) -> None:
        """
        Load the score calibrator, if one is configured and present.

        Absence is not an error: calibration is additive, and a missing file
        simply means no calibrated probability is reported.
        """
        path = (settings.AUTHENTICITY_CALIBRATOR or "").strip()
        if not path:
            return
        try:
            from pathlib import Path

            from app.ml.authenticity.calibration import load_calibrator

            candidate = Path(path)
            if not candidate.is_absolute():
                candidate = Path(__file__).resolve().parents[3] / path
            if not candidate.is_file():
                log.info("authenticity.calibrator_absent", path=str(candidate))
                return
            self._calibrator = load_calibrator(candidate)
            log.info("authenticity.calibrator_loaded",
                     method=self._calibrator.method, version=self._calibrator.version)
        except Exception as e:
            # Calibration must never be able to break inference.
            log.warning("authenticity.calibrator_failed", error=str(e))
            self._calibrator = None

    def _init_real_ml(self) -> None:
        """Try to bring up AASIST; on any failure, fall back and record why."""
        try:
            from app.ml.authenticity.aasist import AASISTDetector

            detector = AASISTDetector(
                model_dir=settings.MODEL_DIR,
                variant=settings.AASIST_VARIANT,
                cascade=settings.AASIST_CASCADE,
                cascade_margin=settings.AASIST_CASCADE_MARGIN,
                device=settings.ML_DEVICE,
            )
            missing = detector.missing_checkpoints()
            if missing:
                raise FileNotFoundError(
                    f"missing checkpoints: {', '.join(missing)} — run scripts/fetch_models.py"
                )
            detector.warmup()
            self._aasist = detector
            self._mode = REAL_ML
            log.info("authenticity.backend", mode=REAL_ML,
                     variant=settings.AASIST_VARIANT, cascade=settings.AASIST_CASCADE)
        except Exception as e:
            self._mode = HEURISTIC_FALLBACK
            self._fallback_reason = str(e)
            log.warning("authenticity.fallback", reason=str(e))

    # ── Reported identity of the active backend ──────────────────────────────

    @property
    def pipeline_mode(self) -> str:
        return self._mode

    @property
    def is_real_ml(self) -> bool:
        return self._mode == REAL_ML

    @property
    def model_name(self) -> str:
        return "AASIST" if self.is_real_ml else HeuristicBackend.MODEL_NAME

    @property
    def model_version(self) -> str:
        if self.is_real_ml:
            variant = settings.AASIST_VARIANT
            suffix = "+cascade" if settings.AASIST_CASCADE and variant != "AASIST" else ""
            return f"{variant}{suffix}@asvspoof2019la"
        return HeuristicBackend.MODEL_VERSION

    @property
    def fallback_reason(self) -> Optional[str]:
        return self._fallback_reason

    # ── Inference ────────────────────────────────────────────────────────────

    def analyze(self, audio: Optional[np.ndarray]) -> Optional[AuthenticityResult]:
        """
        Score one window, or return None when there is not enough audio to make
        any claim — the Risk Engine then stays at INSUFFICIENT_EVIDENCE.

        Never raises: a model failure degrades to the heuristic for that window
        and is labelled as a fallback, so one bad window cannot end the session.
        """
        if audio is None or len(audio) < self.min_samples:
            return None

        # Refuse windows with no measurable speech. A trained anti-spoofing
        # model has no defined behaviour on silence or non-speech and will
        # still emit a confident-looking number; reporting "no evidence" is the
        # honest result. The live pipeline already gates silence upstream, but
        # this guard makes the detector safe to call directly.
        if float(np.mean(np.asarray(audio, dtype=np.float64) ** 2)) < MIN_SPEECH_ENERGY:
            return None

        # DSP evidence pass (independent observations, computed either way).
        dsp_evidence = dsp.extract_dsp_evidence(audio, self.sample_rate)
        bands = dsp_evidence["bands"]

        mode = self._mode
        model_name = self.model_name
        model_version = self.model_version
        inference_ms = 0.0
        device = "cpu"

        if self._aasist is not None:
            try:
                observed = self._aasist.score(audio)
                spoof = observed.synthetic_probability
                confidence = observed.model_confidence
                model_name = observed.model_name
                model_version = observed.model_version
                inference_ms = observed.inference_ms
                device = observed.device
            except Exception as e:
                log.warning("authenticity.inference_failed", error=str(e))
                spoof, confidence = self._heuristic.score(audio)
                mode = HEURISTIC_FALLBACK
                model_name = HeuristicBackend.MODEL_NAME
                model_version = HeuristicBackend.MODEL_VERSION
        else:
            spoof, confidence = self._heuristic.score(audio)

        calibrated = method = version = None
        if self._calibrator is not None and mode == REAL_ML:
            # Calibrated only for real model scores: the heuristic backend
            # produces a different quantity that this calibrator never saw.
            try:
                calibrated = round(float(self._calibrator.predict([spoof])[0]), 4)
                method = self._calibrator.method
                version = self._calibrator.version
            except Exception as e:
                log.warning("authenticity.calibration_failed", error=str(e))

        fused = spoof
        if settings.USE_CALIBRATED_SCORE_FOR_FUSION and calibrated is not None:
            fused = calibrated

        return AuthenticityResult(
            score=int(round(fused * 100)),
            spoof_probability=round(float(fused), 4),
            confidence=round(float(confidence), 3),
            model_version=model_version,
            is_mock=mode != REAL_ML,
            model_name=model_name,
            pipeline_mode=mode,
            inference_ms=inference_ms,
            device=device,
            calibrated_spoof_probability=calibrated,
            calibration_method=method,
            calibration_version=version,
            pitch=dsp_evidence.get("pitch"),
            prosody=dsp_evidence.get("prosody"),
            rhythm=dsp_evidence.get("rhythm"),
            pause_analysis=dsp_evidence.get("pause_analysis"),
            microvariation=dsp_evidence.get("microvariation"),
            spectral_details=dsp_evidence.get("spectral"),
            **bands,
        )

    # Backwards-compatible scalar API used by older call sites.
    def score(self, audio: np.ndarray) -> Optional[float]:
        result = self.analyze(audio)
        return result.spoof_probability if result else None
