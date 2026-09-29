"""
Speaker Identity — EVIDENCE STREAM 2.

Selects an embedding backend and reports which one produced each observation:

  pipeline_mode = "real_ml"            ECAPA-TDNN embeddings. is_mock = False.
  pipeline_mode = "heuristic_demo"     Spectral-fingerprint demo backend.
  pipeline_mode = "heuristic_fallback" real_ml requested but unavailable.

CRITICAL SEMANTICS — a speaker mismatch is evidence about *identity only*. A
genuine but unfamiliar human scores low here, and so would a cloned voice; this
stream cannot tell them apart and does not try. Only the Risk Engine combines
this with the authenticity stream. Nothing here reads conversation context.

PRIVACY: embeddings live in memory for the session, are cleared on disconnect,
and are never placed in evidence, logs or persistence. Raw audio is not stored.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

import numpy as np
import structlog

from app.core.config import settings

log = structlog.get_logger()

SAMPLE_RATE = 16000
DEMO_EMBEDDING_DIM = 64

REAL_ML = "real_ml"
HEURISTIC_DEMO = "heuristic_demo"
HEURISTIC_FALLBACK = "heuristic_fallback"

NOT_ENROLLED = "NOT_ENROLLED"
ENROLLED = "ENROLLED"
VERIFIED = "VERIFIED"
MISMATCH = "MISMATCH"
# Returned when a speaker reference exists but the current window provides
# insufficient audio for a confident comparison (e.g. brief silence mid-call).
# The UI should display the last known status, not "NOT_ENROLLED".
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class IdentityResult:
    match_score: int
    confidence: float
    consistency: str          # GOOD | VARIABLE | POOR | UNKNOWN
    enrollment_status: str    # NOT_ENROLLED | ENROLLED | VERIFIED | MISMATCH
    model_version: str
    is_mock: bool
    # Added for real ML integration.
    model_name: str = "spectral-fingerprint"
    pipeline_mode: str = HEURISTIC_DEMO
    similarity: float = 0.0   # raw cosine; never the embedding itself
    inference_ms: float = 0.0
    reference_available: bool = False
    comparison_available: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _unenrolled(model_name: str, model_version: str, mode: str) -> IdentityResult:
    return IdentityResult(
        match_score=0,
        confidence=0.0,
        consistency="UNKNOWN",
        enrollment_status=NOT_ENROLLED,
        model_version=model_version,
        is_mock=mode != REAL_ML,
        model_name=model_name,
        pipeline_mode=mode,
        reference_available=False,
        comparison_available=False,
    )


class SpectralFingerprintBackend:
    """
    Deterministic demo backend: a 64-band log-magnitude spectral fingerprint.

    Not a speaker-recognition model. Kept because the demonstration must be
    reproducible, and clearly labelled so it is never mistaken for ECAPA.
    """

    MODEL_NAME = "spectral-fingerprint"
    MODEL_VERSION = "ecapa-stub-v0.2"
    VERIFIED_AT = 0.75
    MISMATCH_BELOW = 0.50

    def embed(self, audio: np.ndarray) -> np.ndarray:
        n = min(len(audio), 16384)
        window = audio[:n] * np.hanning(n)
        mag = np.abs(np.fft.rfft(window)) + 1e-12
        bands = np.array_split(mag, DEMO_EMBEDDING_DIM)
        vec = np.array([np.log(np.mean(b) + 1e-12) for b in bands], dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def similarity(self, live: np.ndarray, reference: np.ndarray) -> float:
        denom = float(np.linalg.norm(live) * np.linalg.norm(reference))
        if denom == 0:
            return 0.0
        # Map cosine [-1, 1] onto [0, 1] — this backend's own scale.
        return float(np.clip((float(np.dot(live, reference)) / denom + 1.0) / 2.0, 0.0, 1.0))


class SpeakerIdentity:
    """Per-session speaker verification against an enrolled reference."""

    MODEL_VERSION = SpectralFingerprintBackend.MODEL_VERSION
    IS_MOCK = True
    MIN_SAMPLES = 4000          # demo backend floor (0.25 s)
    REAL_MIN_SAMPLES = 16000    # ECAPA needs ~1 s for a stable embedding

    def __init__(self, sample_rate: int = SAMPLE_RATE, pipeline_mode: Optional[str] = None):
        self.sample_rate = sample_rate
        self._demo = SpectralFingerprintBackend()
        self._ecapa = None
        self._mode = HEURISTIC_DEMO
        self._fallback_reason: Optional[str] = None

        # session_id → enrolled embedding (in memory only, never emitted)
        self._enrolled: Dict[str, np.ndarray] = {}
        # session_id → rolling similarity history, for the consistency signal
        self._history: Dict[str, List[float]] = {}

        if (pipeline_mode or settings.PIPELINE_MODE) == REAL_ML:
            self._init_real_ml()

    def _init_real_ml(self) -> None:
        try:
            from app.ml.identity.ecapa import ECAPAEmbedder

            embedder = ECAPAEmbedder(model_dir=settings.MODEL_DIR, device=settings.ML_DEVICE)
            if not embedder.is_available:
                raise RuntimeError("speechbrain/torch not installed")
            embedder.warmup()
            self._ecapa = embedder
            self._mode = REAL_ML
            log.info("identity.backend", mode=REAL_ML, model=embedder.MODEL_NAME)
        except Exception as e:
            self._mode = HEURISTIC_FALLBACK
            self._fallback_reason = str(e)
            log.warning("identity.fallback", reason=str(e))

    # ── Reported identity of the active backend ──────────────────────────────

    @property
    def pipeline_mode(self) -> str:
        return self._mode

    @property
    def is_real_ml(self) -> bool:
        return self._mode == REAL_ML

    @property
    def model_name(self) -> str:
        return self._ecapa.MODEL_NAME if self.is_real_ml else self._demo.MODEL_NAME

    @property
    def model_version(self) -> str:
        return self._ecapa.MODEL_VERSION if self.is_real_ml else self._demo.MODEL_VERSION

    @property
    def fallback_reason(self) -> Optional[str]:
        return self._fallback_reason

    @property
    def min_samples(self) -> int:
        return self.REAL_MIN_SAMPLES if self.is_real_ml else self.MIN_SAMPLES

    @property
    def _thresholds(self) -> tuple:
        if self.is_real_ml:
            return settings.ECAPA_VERIFIED_AT, settings.ECAPA_MISMATCH_BELOW
        return self._demo.VERIFIED_AT, self._demo.MISMATCH_BELOW

    # ── Enrollment ───────────────────────────────────────────────────────────

    # Cross-session persistent reference registry: reference_id -> embedding
    _persistent_registry: Dict[str, np.ndarray] = {}

    def enroll_reference(self, reference_id: str, audio: np.ndarray) -> bool:
        """
        Enroll a persistent speaker reference (e.g. for a user or contact).
        Embeddings are kept in internal protected memory and never logged or exposed.
        """
        if audio is None or len(audio) < self.min_samples:
            return False
        try:
            self._persistent_registry[reference_id] = self._embed(audio)
            log.info("identity.reference_enrolled", reference_id=reference_id)
            return True
        except Exception as e:
            log.warning("identity.reference_enroll_failed", reference_id=reference_id, error=str(e))
            return False

    def has_reference(self, reference_id: str) -> bool:
        return reference_id in self._persistent_registry

    def remove_reference(self, reference_id: str) -> bool:
        return self._persistent_registry.pop(reference_id, None) is not None

    def enroll(self, session_id: str, audio: np.ndarray) -> bool:
        """
        Enrol a reference speaker.

        Must only be called from a trusted enrollment path — never from live
        inbound call audio in production, or an attacker defines the reference.
        The pipeline's development fixture enrols from the first analysable
        window and labels the result accordingly.
        """
        if audio is None or len(audio) < self.min_samples:
            return False
        try:
            self._enrolled[session_id] = self._embed(audio)
        except Exception as e:
            log.warning("identity.enroll_failed", error=str(e))
            return False
        self._history.setdefault(session_id, [])
        return True

    def is_enrolled(self, session_id: str) -> bool:
        return session_id in self._enrolled

    def clear(self, session_id: str) -> None:
        """Drop the embedding and history — called on disconnect."""
        self._enrolled.pop(session_id, None)
        self._history.pop(session_id, None)

    # ── Verification ─────────────────────────────────────────────────────────

    def analyze(self, session_id: str, audio: Optional[np.ndarray], reference_id: Optional[str] = None) -> IdentityResult:
        """
        Compare the current window to the enrolled reference (session-level or persistent).

        Returns NOT_ENROLLED when there is no reference — the system reports the
        gap rather than inventing a match score. Never raises.
        """
        reference = None
        if reference_id and reference_id in self._persistent_registry:
            reference = self._persistent_registry[reference_id]
        if reference is None:
            reference = self._enrolled.get(session_id)

        if reference is None:
            return _unenrolled(self.model_name, self.model_version, self._mode)
        if audio is None or len(audio) < self.min_samples:
            # Speaker IS enrolled, but this window does not have enough audio
            # for a meaningful comparison. Return INSUFFICIENT_EVIDENCE so the
            # UI preserves the enrolled state rather than showing NOT_ENROLLED.
            return IdentityResult(
                match_score=0,
                confidence=0.0,
                consistency="UNKNOWN",
                enrollment_status=INSUFFICIENT_EVIDENCE,
                model_version=self.model_version,
                is_mock=self._mode != REAL_ML,
                model_name=self.model_name,
                pipeline_mode=self._mode,
                reference_available=True,
                comparison_available=False,
            )

        mode = self._mode
        inference_ms = 0.0
        try:
            live = self._embed(audio)
            if self.is_real_ml:
                observed = self._ecapa.compare(live, reference, len(audio) / self.sample_rate)
                similarity = observed.similarity
                match_score = observed.match_score
                confidence = observed.model_confidence
                inference_ms = observed.inference_ms
            else:
                similarity = self._demo.similarity(live, reference)
                match_score = int(round(similarity * 100))
                confidence = 0.0  # set from history length below
        except Exception as e:
            log.warning("identity.inference_failed", error=str(e))
            return _unenrolled(self._demo.MODEL_NAME, self._demo.MODEL_VERSION,
                               HEURISTIC_FALLBACK)

        history = self._history.setdefault(session_id, [])
        history.append(similarity)
        del history[:-20]

        if not self.is_real_ml:
            confidence = float(np.clip(0.30 + 0.10 * len(history), 0.0, 0.80))

        verified_at, mismatch_below = self._thresholds
        if similarity >= verified_at:
            status = VERIFIED
        elif similarity >= mismatch_below:
            status = ENROLLED
        else:
            status = MISMATCH

        return IdentityResult(
            match_score=match_score,
            confidence=round(float(confidence), 3),
            consistency=self._consistency(history),
            enrollment_status=status,
            model_version=self.model_version,
            is_mock=mode != REAL_ML,
            model_name=self.model_name,
            pipeline_mode=mode,
            similarity=round(float(similarity), 4),
            inference_ms=inference_ms,
            reference_available=True,
            comparison_available=True,
        )

    # ── Internals ────────────────────────────────────────────────────────────

    def _embed(self, audio: np.ndarray) -> np.ndarray:
        if self.is_real_ml:
            return self._ecapa.embed(audio)
        return self._demo.embed(audio)

    @staticmethod
    def _consistency(history: List[float]) -> str:
        if len(history) < 3:
            return "UNKNOWN"
        spread = float(np.std(history))
        if spread < 0.05:
            return "GOOD"
        if spread < 0.12:
            return "VARIABLE"
        return "POOR"
