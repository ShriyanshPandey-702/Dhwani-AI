"""
Real speaker verification — ECAPA-TDNN embedding backend.

STATUS: REAL MODEL, PRETRAINED CHECKPOINT, THRESHOLDS NOT CALIBRATED BY US.

  Model      ECAPA-TDNN speaker embeddings (192-d)
  Source     speechbrain/spkrec-ecapa-voxceleb (Hugging Face)
  Licence    Apache-2.0
  Trained on VoxCeleb 1 + 2 (by the SpeechBrain authors)
  Input      16 kHz mono waveform
  Output     192-d embedding; speakers compared by cosine similarity

What this is NOT:
  * Not trained or fine-tuned by Dhwani AI.
  * Decision thresholds below are the model card's typical operating region,
    not a calibration against Indian telecom audio, codecs or our channel.
  * A similarity score is evidence about IDENTITY only. A low score means the
    voice does not match the enrolled reference; it is not, and must never be
    presented as, evidence that the audio is synthetic.

PRIVACY: embeddings stay in memory for the life of a session and are never
emitted in evidence, logged, or persisted. Raw audio is not retained.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import structlog

log = structlog.get_logger()

SAMPLE_RATE = 16000
EMBEDDING_DIM = 192
HF_SOURCE = "speechbrain/spkrec-ecapa-voxceleb"
# ECAPA needs a reasonable amount of speech for a stable embedding.
MIN_SAMPLES = int(SAMPLE_RATE * 1.0)


class EmbedderUnavailable(RuntimeError):
    """Raised when the ECAPA checkpoint cannot be loaded — never silently faked."""


@dataclass
class Similarity:
    """One identity observation. Carries no embedding and no audio."""

    similarity: float          # raw cosine, -1.0 → 1.0
    match_score: int           # 0–100, clamped cosine
    model_confidence: float
    model_name: str
    model_version: str
    inference_ms: float
    device: str


class ECAPAEmbedder:
    """Loads ECAPA-TDNN lazily and produces L2-normalised embeddings."""

    MODEL_NAME = "ECAPA-TDNN"
    MODEL_VERSION = "spkrec-ecapa-voxceleb"

    def __init__(self, model_dir: str = "models", device: str = "auto"):
        self.savedir = str(Path(model_dir) / "ecapa")
        self._requested_device = device
        self._device: Optional[str] = None
        self._encoder = None

    @property
    def is_available(self) -> bool:
        try:
            import speechbrain  # noqa: F401
            import torch  # noqa: F401
        except ImportError:
            return False
        return True

    def _load(self):
        if self._encoder is not None:
            return self._encoder
        try:
            import torch
            from speechbrain.inference.speaker import EncoderClassifier
        except ImportError as e:
            raise EmbedderUnavailable(f"speechbrain/torch unavailable: {e}") from e

        if self._device is None:
            self._device = (
                self._requested_device
                if self._requested_device and self._requested_device != "auto"
                else ("cuda" if torch.cuda.is_available() else "cpu")
            )
        try:
            self._encoder = EncoderClassifier.from_hparams(
                source=HF_SOURCE,
                savedir=self.savedir,
                run_opts={"device": self._device},
            )
        except Exception as e:
            raise EmbedderUnavailable(
                f"could not load {HF_SOURCE}: {e}. "
                f"Check network access, or pre-populate {self.savedir}."
            ) from e
        log.info("ecapa.loaded", source=HF_SOURCE, device=self._device)
        return self._encoder

    def warmup(self) -> None:
        import torch

        encoder = self._load()
        encoder.encode_batch(torch.zeros(1, MIN_SAMPLES, device=self._device))

    def embed(self, audio: np.ndarray) -> np.ndarray:
        """Return one L2-normalised 192-d embedding. Never logged or emitted."""
        import torch

        encoder = self._load()
        wav = torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32))
        wav = wav.unsqueeze(0).to(self._device)
        with torch.no_grad():
            emb = encoder.encode_batch(wav).squeeze()
        vec = emb.detach().cpu().numpy().astype(np.float32).ravel()
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 0 else vec

    def compare(self, live: np.ndarray, reference: np.ndarray,
                duration_s: float) -> Similarity:
        """Cosine similarity between a live window and an enrolled reference."""
        started = time.perf_counter()
        cosine = float(np.dot(live, reference))
        elapsed = (time.perf_counter() - started) * 1000.0

        # Confidence reflects how much speech backed the comparison, capped
        # because these thresholds are not calibrated for our conditions.
        sufficiency = min(1.0, duration_s / 3.0)
        confidence = float(np.clip(0.30 + 0.45 * sufficiency, 0.0, 0.80))

        return Similarity(
            similarity=round(cosine, 4),
            match_score=int(round(float(np.clip(cosine, 0.0, 1.0)) * 100)),
            model_confidence=round(confidence, 3),
            model_name=self.MODEL_NAME,
            model_version=self.MODEL_VERSION,
            inference_ms=round(elapsed, 3),
            device=self._device or "cpu",
        )
