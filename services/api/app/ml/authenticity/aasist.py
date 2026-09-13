"""
Real synthetic-speech detection — AASIST inference backend.

STATUS: REAL MODEL, PRETRAINED CHECKPOINT, NOT EVALUATED BY US.

  Model      AASIST / AASIST-L (graph attention over raw waveform)
  Source     https://github.com/clovaai/aasist — MIT, (c) NAVER Corp
  Paper      Jung et al., ICASSP 2022
  Trained on ASVspoof 2019 Logical Access (by the original authors)
  Input      raw waveform, 16 kHz mono, 64600 samples (~4.04 s)
  Output     2 logits; index 1 is the bona-fide class (upstream convention)

What this is NOT:
  * Not trained or fine-tuned by VoiceShield.
  * Not evaluated on Indian telecom audio, codecs, or unseen generators.
  * Not calibrated — the softmax output is a raw decision score, not a
    probability you should read as a likelihood.

The DSP anomaly bands reported alongside come from `dsp.py` and are independent
measurements, not model outputs.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger()

SAMPLE_RATE = 16000
NB_SAMP = 64600  # the length the released checkpoints were trained on

# Architecture hyper-parameters, copied from the upstream config files so the
# released checkpoints load strictly. Do not change without new weights.
MODEL_CONFIGS = {
    "AASIST": {
        "architecture": "AASIST", "nb_samp": NB_SAMP, "first_conv": 128,
        "filts": [70, [1, 32], [32, 32], [32, 64], [64, 64]],
        "gat_dims": [64, 32], "pool_ratios": [0.5, 0.7, 0.5, 0.5],
        "temperatures": [2.0, 2.0, 100.0, 100.0],
    },
    "AASIST-L": {
        "architecture": "AASIST", "nb_samp": NB_SAMP, "first_conv": 128,
        "filts": [70, [1, 32], [32, 32], [32, 24], [24, 24]],
        "gat_dims": [24, 32], "pool_ratios": [0.4, 0.5, 0.7, 0.5],
        "temperatures": [2.0, 2.0, 100.0, 100.0],
    },
}

# Checkpoints are downloaded by scripts/fetch_models.py, never committed.
CHECKPOINTS = {
    "AASIST": (
        "AASIST.pth",
        "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0",
    ),
    "AASIST-L": (
        "AASIST-L.pth",
        "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a",
    ),
}


class CheckpointMissing(RuntimeError):
    """Raised when a required checkpoint is absent — never silently faked."""


@dataclass
class SpoofScore:
    """One model observation. Deliberately carries no identity or context."""

    synthetic_probability: float   # 0.0–1.0, higher = more synthetic
    model_confidence: float        # uncalibrated decisiveness, never 1.0
    model_name: str
    model_version: str
    tiers_run: tuple               # which cascade tiers actually executed
    inference_ms: float
    device: str


def resolve_device(requested: str) -> str:
    """Pick a torch device, preferring what is genuinely available."""
    import torch

    if requested and requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    # MPS is available on Apple silicon but AASIST's FFT ops fall back to CPU
    # anyway, so CPU is both simpler and, at this model size, not slower.
    return "cpu"


class AASISTDetector:
    """
    Wraps one or two AASIST checkpoints behind a single `score()` call.

    Models are loaded lazily on first use so importing this module never
    triggers a multi-hundred-millisecond torch graph build.
    """

    def __init__(
        self,
        model_dir: str = "models",
        variant: str = "AASIST-L",
        cascade: bool = True,
        cascade_margin: float = 0.25,
        device: str = "auto",
    ):
        self.model_dir = Path(model_dir) / "aasist"
        self.variant = variant if variant in MODEL_CONFIGS else "AASIST-L"
        self.cascade = cascade and self.variant != "AASIST"
        self.cascade_margin = cascade_margin
        self._requested_device = device
        self._device: Optional[str] = None
        self._models: dict = {}

    # ── Availability ─────────────────────────────────────────────────────────

    def checkpoint_path(self, name: str) -> Path:
        return self.model_dir / CHECKPOINTS[name][0]

    def missing_checkpoints(self) -> list:
        needed = [self.variant]
        if self.cascade:
            needed.append("AASIST")
        return [n for n in dict.fromkeys(needed) if not self.checkpoint_path(n).is_file()]

    @property
    def is_available(self) -> bool:
        try:
            import torch  # noqa: F401
        except ImportError:
            return False
        return not self.missing_checkpoints()

    # ── Loading ──────────────────────────────────────────────────────────────

    def _load(self, name: str):
        if name in self._models:
            return self._models[name]

        import torch
        from app.ml.authenticity.vendor.aasist_model import Model

        path = self.checkpoint_path(name)
        if not path.is_file():
            raise CheckpointMissing(
                f"{name} checkpoint not found at {path}. "
                f"Run: python scripts/fetch_models.py"
            )

        if self._device is None:
            self._device = resolve_device(self._requested_device)

        model = Model(MODEL_CONFIGS[name])
        state = torch.load(path, map_location="cpu")
        model.load_state_dict(state, strict=True)
        model.to(self._device)
        model.eval()
        self._models[name] = model
        log.info("aasist.loaded", model=name, device=self._device,
                 params=sum(p.numel() for p in model.parameters()))
        return model

    def warmup(self) -> None:
        """Load and run once so the first real window is not the slow one."""
        import torch

        for name in dict.fromkeys([self.variant] + (["AASIST"] if self.cascade else [])):
            model = self._load(name)
            with torch.no_grad():
                model(torch.zeros(1, NB_SAMP, device=self._device))

    # ── Inference ────────────────────────────────────────────────────────────

    @staticmethod
    def _fit_length(audio: np.ndarray) -> np.ndarray:
        """
        Match the training length: tile short audio, centre-crop long audio.

        Tiling (rather than zero-padding) is what the upstream evaluation code
        does, and zero padding would itself look like an artefact to the model.
        """
        n = len(audio)
        if n == NB_SAMP:
            return audio
        if n < NB_SAMP:
            reps = int(NB_SAMP / max(1, n)) + 1
            return np.tile(audio, reps)[:NB_SAMP]
        start = (n - NB_SAMP) // 2
        return audio[start:start + NB_SAMP]

    def _run(self, name: str, audio: np.ndarray) -> float:
        """Return this tier's synthetic probability (1 - P(bona fide))."""
        import torch

        model = self._load(name)
        x = torch.from_numpy(np.ascontiguousarray(self._fit_length(audio), dtype=np.float32))
        x = x.unsqueeze(0).to(self._device)
        with torch.no_grad():
            _, logits = model(x)
            probs = torch.softmax(logits, dim=1)[0]
        # Upstream convention: column 1 is the bona-fide class.
        return float(1.0 - probs[1].item())

    def score(self, audio: np.ndarray) -> SpoofScore:
        """
        Score one analysis window.

        Cascade: the light model runs first; the heavy model runs only when the
        light one lands inside the undecided band. This is a real tiering of two
        released checkpoints, not a synthetic benchmark.
        """
        started = time.perf_counter()
        tiers = []

        p = self._run(self.variant, audio)
        tiers.append(self.variant)

        if self.cascade and abs(p - 0.5) < self.cascade_margin:
            p = self._run("AASIST", audio)
            tiers.append("AASIST")

        elapsed_ms = (time.perf_counter() - started) * 1000.0

        # Decisiveness, not calibrated certainty. Capped well below 1.0 because
        # this checkpoint has not been evaluated on our audio conditions.
        decisiveness = min(1.0, abs(p - 0.5) * 2.0)
        duration_s = len(audio) / SAMPLE_RATE
        sufficiency = min(1.0, duration_s / (NB_SAMP / SAMPLE_RATE))
        confidence = float(np.clip(0.25 + 0.5 * decisiveness * sufficiency, 0.0, 0.80))

        return SpoofScore(
            synthetic_probability=round(float(np.clip(p, 0.0, 1.0)), 4),
            model_confidence=round(confidence, 3),
            model_name="AASIST",
            model_version=f"{'+'.join(tiers)}@asvspoof2019la",
            tiers_run=tuple(tiers),
            inference_ms=round(elapsed_ms, 2),
            device=self._device or "cpu",
        )
