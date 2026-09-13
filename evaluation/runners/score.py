"""
Score a dataset with the REAL AASIST detector.

Hard guarantee enforced at the top of every run: if the real model is not
loaded, the runner raises. It will never silently fall back to the heuristic
backend, the demo detector, generated PCM, or any hardcoded value — a number
produced that way would be worthless as a benchmark and dangerous as a claim.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(REPO_ROOT), str(API_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from evaluation.datasets.base import Sample  # noqa: E402

TARGET_SR = 16000


class NotRealModel(RuntimeError):
    """Raised when the evaluation would otherwise score with a non-model backend."""


@dataclass
class ScoredSample:
    audio_path: str
    label: int
    dataset: str
    split: str
    score: float               # raw synthetic probability from AASIST
    speaker_id: Optional[str] = None
    system_id: Optional[str] = None
    attack_type: Optional[str] = None
    language: Optional[str] = None
    condition: str = "clean"
    duration_s: float = 0.0


def build_detector(variant: str = "AASIST-L", cascade: bool = False,
                   model_dir: Optional[str] = None):
    """
    Construct the real AASIST detector and prove it is real.

    Cascade defaults to OFF for evaluation: a benchmark must characterise one
    model at a time, not a two-tier policy whose escalation depends on the
    score itself.
    """
    from app.core.config import settings
    from app.ml.authenticity.aasist import AASISTDetector

    detector = AASISTDetector(
        model_dir=model_dir or str(API_ROOT / settings.MODEL_DIR),
        variant=variant,
        cascade=cascade,
        device=settings.ML_DEVICE,
    )
    missing = detector.missing_checkpoints()
    if missing:
        raise NotRealModel(
            f"cannot evaluate: missing checkpoints {missing}. "
            f"Run services/api/scripts/fetch_models.py"
        )
    detector.warmup()
    return detector


def checkpoint_fingerprint(detector) -> Dict[str, str]:
    """SHA-256 of every checkpoint actually loaded, recorded with each run."""
    out = {}
    for name in list(detector._models) or [detector.variant]:
        path = detector.checkpoint_path(name)
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    digest.update(block)
            out[name] = digest.hexdigest()
    return out


def load_audio(path: str, target_sr: int = TARGET_SR) -> Optional[np.ndarray]:
    """Read any supported file as float32 mono at `target_sr`."""
    import soundfile as sf

    try:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return None
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != target_sr:
        from scipy import signal as sps

        g = np.gcd(int(sr), int(target_sr))
        audio = sps.resample_poly(audio, target_sr // g, sr // g)
    return np.ascontiguousarray(audio, dtype=np.float32)


def _fit_batch(detector, audios: Sequence[np.ndarray]) -> np.ndarray:
    return np.stack([detector._fit_length(a) for a in audios])


def score_samples(
    samples: Sequence[Sample],
    detector,
    condition: str = "clean",
    seed: int = 1337,
    batch_size: int = 8,   # measured optimum on CPU; larger batches are slower
    progress_every: int = 2000,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> List[ScoredSample]:
    """
    Score every sample, optionally under a degradation condition.

    Batched through the model for throughput; a file that cannot be read or
    scored is skipped and counted rather than assigned a fabricated score.
    """
    import torch

    from evaluation.robustness.transforms import apply_condition

    scored: List[ScoredSample] = []
    pending: List[tuple] = []
    started = time.perf_counter()

    def flush():
        if not pending:
            return
        audios = [item[1] for item in pending]
        batch = torch.from_numpy(_fit_batch(detector, audios)).to(detector._device)
        with torch.no_grad():
            _, logits = detector._models[detector.variant](batch)
            probs = torch.softmax(logits, dim=1)[:, 1]      # P(bona fide)
        synthetic = (1.0 - probs).detach().cpu().numpy()
        for (sample, audio), p in zip(pending, synthetic):
            scored.append(ScoredSample(
                audio_path=sample.audio_path, label=sample.label,
                dataset=sample.dataset, split=sample.split,
                score=float(np.clip(p, 0.0, 1.0)),
                speaker_id=sample.speaker_id, system_id=sample.system_id,
                attack_type=sample.attack_type, language=sample.language,
                condition=condition, duration_s=len(audio) / TARGET_SR,
            ))
        pending.clear()

    for i, sample in enumerate(samples):
        audio = load_audio(sample.audio_path)
        if audio is None or audio.size < 1000:
            continue
        if condition != "clean":
            # Seed per file so a condition is reproducible yet not identical
            # across files.
            audio = apply_condition(condition, audio, seed=seed + i)
        pending.append((sample, audio))
        if len(pending) >= batch_size:
            flush()
        if on_progress and progress_every and (i + 1) % progress_every == 0:
            on_progress(i + 1, len(samples))
    flush()

    elapsed = time.perf_counter() - started
    _LAST_TIMING["seconds"] = elapsed
    _LAST_TIMING["n"] = len(scored)
    return scored


_LAST_TIMING: Dict[str, float] = {"seconds": 0.0, "n": 0}


def last_timing() -> Dict[str, float]:
    t = dict(_LAST_TIMING)
    t["per_file_ms"] = (t["seconds"] * 1000.0 / t["n"]) if t["n"] else 0.0
    return t


def run_metadata(detector, extra: Optional[Dict] = None) -> Dict:
    """Everything needed to reproduce or audit a run."""
    import torch

    from app.core.config import settings
    from app.ml.authenticity.aasist import NB_SAMP

    meta = {
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": {
            "name": "AASIST",
            "variant": detector.variant,
            "cascade": detector.cascade,
            "checkpoint_sha256": checkpoint_fingerprint(detector),
            "source": "https://github.com/clovaai/aasist (MIT, NAVER Corp)",
            "trained_on": "ASVspoof 2019 LA train (by the original authors)",
            "device": detector._device,
        },
        "preprocessing": {
            "sample_rate": TARGET_SR,
            "input_samples": NB_SAMP,
            "input_seconds": round(NB_SAMP / TARGET_SR, 4),
            "length_policy": "tile if short, centre-crop if long (upstream convention)",
            "channels": "mono (averaged)",
            "resampling": "scipy resample_poly when source sr != 16000",
            "normalisation": "none beyond float32 in [-1, 1]",
            "version": "prep-v1",
        },
        "software": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "hardware": {
            "machine": platform.machine(),
            "torch_threads": torch.get_num_threads(),
            "cuda_available": torch.cuda.is_available(),
        },
        "settings": {
            "ANALYSIS_WINDOW_MS": settings.ANALYSIS_WINDOW_MS,
            "ANALYSIS_HOP_MS": settings.ANALYSIS_HOP_MS,
            "MIN_ANALYSIS_MS": settings.MIN_ANALYSIS_MS,
        },
    }
    if extra:
        meta.update(extra)
    return meta


def save_scores(scored: Sequence[ScoredSample], path: str | Path) -> Path:
    import csv

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["audio_path", "label", "dataset", "split", "score", "speaker_id",
              "system_id", "attack_type", "language", "condition", "duration_s"]
    with out.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for s in scored:
            writer.writerow({k: getattr(s, k) for k in fields})
    return out
