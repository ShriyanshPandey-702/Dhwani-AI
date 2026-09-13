#!/usr/bin/env python3
"""
Measure real inference latency for the VoiceShield ML backends.

Every number this prints is measured on the machine it runs on. Nothing here is
a published or estimated figure, and a result from one machine says nothing
about another. Run it yourself before quoting latency anywhere.

    python scripts/benchmark_ml.py
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FIXTURE = ROOT / "tests" / "fixtures" / "audio" / "tts_synthetic_16k.wav"
SR = 16000
RUNS = 30
WARMUP = 3


def describe_host() -> dict:
    info = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "python": platform.python_version(),
    }
    try:
        import torch

        info["torch"] = torch.__version__
        info["torch_threads"] = torch.get_num_threads()
        info["cuda_available"] = torch.cuda.is_available()
    except ImportError:
        info["torch"] = None
    return info


def load_audio() -> np.ndarray:
    import soundfile as sf

    if not FIXTURE.is_file():
        raise SystemExit(f"fixture missing: {FIXTURE}")
    audio, sr = sf.read(FIXTURE, dtype="float32")
    assert sr == SR, f"expected {SR} Hz, got {sr}"
    return audio


def time_calls(fn, audio, runs=RUNS, warmup=WARMUP) -> dict:
    for _ in range(warmup):
        fn(audio)
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        fn(audio)
        samples.append((time.perf_counter() - started) * 1000.0)
    samples.sort()
    return {
        "runs": runs,
        "mean_ms": round(statistics.fmean(samples), 2),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(samples[int(0.95 * (len(samples) - 1))], 2),
        "max_ms": round(samples[-1], 2),
    }


def main() -> int:
    from app.core.config import settings
    from app.ml.authenticity.aasist import NB_SAMP, AASISTDetector
    from app.ml.authenticity.detector import AuthenticityDetector, HEURISTIC_DEMO

    audio = load_audio()
    window_ms = round(1000 * NB_SAMP / SR, 1)
    report = {
        "host": describe_host(),
        "window_ms": window_ms,
        "window_samples": NB_SAMP,
        "sample_rate": SR,
        "backends": {},
    }

    heuristic = AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO)
    report["backends"]["heuristic-dsp"] = time_calls(heuristic.analyze, audio)

    for variant in ("AASIST-L", "AASIST"):
        detector = AASISTDetector(model_dir=settings.MODEL_DIR, variant=variant, cascade=False)
        if not detector.is_available:
            report["backends"][variant] = {"skipped": "checkpoint missing"}
            continue
        detector.warmup()
        stats = time_calls(detector.score, audio)
        import torch

        model = detector._load(variant)
        stats["params"] = sum(p.numel() for p in model.parameters())
        stats["device"] = detector._device
        stats["realtime_factor_p95"] = round(stats["p95_ms"] / window_ms, 4)
        report["backends"][variant] = stats

    cascade = AASISTDetector(model_dir=settings.MODEL_DIR, variant="AASIST-L",
                             cascade=True, cascade_margin=settings.AASIST_CASCADE_MARGIN)
    if cascade.is_available:
        cascade.warmup()
        stats = time_calls(cascade.score, audio)
        stats["realtime_factor_p95"] = round(stats["p95_ms"] / window_ms, 4)
        stats["note"] = "heavy tier runs only when the light tier is undecided"
        report["backends"]["AASIST-L+cascade"] = stats

    print(json.dumps(report, indent=2))
    print("\nMeasured on this host only. Not a published benchmark, and not an "
          "accuracy claim of any kind.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
