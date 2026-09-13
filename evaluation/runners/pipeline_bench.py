#!/usr/bin/env python3
"""
Phase 1.8 — Real-Time Pipeline Latency & Throughput Benchmark.
=============================================================
Measures latency distributions (p50, p90, p95, p99, mean, max) and throughput
for all components of the frozen VoiceShield production pipeline:
  • AASIST-L Authenticity inference
  • ECAPA-TDNN Speaker Identity embedding
  • faster-whisper STT transcription
  • Context Classifier
  • Risk Engine Fusion
  • End-to-end window turnaround time
  • Memory RSS stability & throughput
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import psutil

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(API_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Invariant check must run first
from evaluation.runners.invariant_check import verify_invariants

from app.core.config import settings
settings.MODEL_DIR = str(API_ROOT / "models")
settings.PIPELINE_MODE = "real_ml"

from app.ml.authenticity.aasist import AASISTDetector
from app.ml.context.classifier import ContextClassifier
from app.ml.context.transcriber import Transcriber
from app.ml.identity.ecapa import ECAPAEmbedder
from app.ml.preprocessing.ingest import load_audio_file
from app.ml.preprocessing.stream import SAMPLE_RATE, StreamWindower
from app.risk.engine import EvidenceBundle, compute_risk
from app.risk.policy import DEFAULT_POLICY_CONFIG, evaluate


def stats_of(values: List[float]) -> Dict[str, float]:
    if not values:
        return {}
    arr = np.array(values, dtype=float)
    return {
        "count": int(arr.size),
        "mean_ms": round(float(np.mean(arr)), 2),
        "std_ms": round(float(np.std(arr)), 2),
        "min_ms": round(float(np.min(arr)), 2),
        "p50_ms": round(float(np.percentile(arr, 50)), 2),
        "p90_ms": round(float(np.percentile(arr, 90)), 2),
        "p95_ms": round(float(np.percentile(arr, 95)), 2),
        "p99_ms": round(float(np.percentile(arr, 99)), 2),
        "max_ms": round(float(np.max(arr)), 2),
    }


def run_latency_benchmark(
    out_path: Optional[Path] = None,
    num_windows: int = 50,
    device: str = "auto",
) -> Dict[str, Any]:
    """Execute latency and throughput benchmarking across real audio windows."""
    verify_invariants(strict=True)

    print(f"[{time.strftime('%H:%M:%S')}] Initializing benchmark models (device={device})...")
    proc = psutil.Process(os.getpid())
    rss_start_mb = proc.memory_info().rss / (1024 * 1024)

    aasist = AASISTDetector(model_dir=str(API_ROOT / "models"), variant="AASIST-L", cascade=True, device=device)
    aasist.warmup()
    ecapa = ECAPAEmbedder(model_dir=str(API_ROOT / "models"), device=device)
    ecapa.warmup()
    stt = Transcriber(pipeline_mode="real_ml")
    ctx_cls = ContextClassifier()
    policy_cfg = dict(DEFAULT_POLICY_CONFIG)

    # Reference speaker embedding for verification
    ref_audio = np.random.randn(SAMPLE_RATE * 3).astype(np.float32)
    ref_emb = ecapa.embed(ref_audio)

    # Audio pool for realistic audio windows
    # Use existing audio files from repo
    test_files = list((REPO_ROOT / "data" / "external" / "InTheWild" / "release_in_the_wild").glob("*.wav"))[:10]
    real_windows: List[np.ndarray] = []
    for f in test_files:
        a, _ = load_audio_file(str(f))
        if len(a) >= 64608:
            for start in range(0, len(a) - 64608 + 1, 16000):
                real_windows.append(a[start:start + 64608])
                if len(real_windows) >= num_windows:
                    break
        if len(real_windows) >= num_windows:
            break

    # If short, tile to produce requested windows
    while len(real_windows) < num_windows:
        dummy = np.random.randn(64608).astype(np.float32)
        real_windows.append(dummy)

    print(f"[{time.strftime('%H:%M:%S')}] Benchmarking {num_windows} analysis windows (each 4.038s @ 16kHz)...")

    lat_aasist: List[float] = []
    lat_ecapa: List[float] = []
    lat_stt: List[float] = []
    lat_context: List[float] = []
    lat_fusion: List[float] = []
    lat_total: List[float] = []

    t_bench_start = time.perf_counter()

    for i, win in enumerate(real_windows[:num_windows]):
        sess_id = f"bench-sess-{i}"
        t_w_start = time.perf_counter()

        # AASIST
        t0 = time.perf_counter()
        prod_score = aasist.score(win)
        lat_aasist.append((time.perf_counter() - t0) * 1000.0)

        # ECAPA
        t0 = time.perf_counter()
        emb = ecapa.embed(win)
        sim = float(np.dot(emb, ref_emb))
        lat_ecapa.append((time.perf_counter() - t0) * 1000.0)

        # STT
        t0 = time.perf_counter()
        seg = stt.transcribe(sess_id, win)
        stt_text = seg.text if seg else ""
        lat_stt.append((time.perf_counter() - t0) * 1000.0)

        # Context
        t0 = time.perf_counter()
        ctx = ctx_cls.classify(sess_id, stt_text)
        lat_context.append((time.perf_counter() - t0) * 1000.0)

        # Risk Engine + Policy
        t0 = time.perf_counter()
        bundle = EvidenceBundle(
            authenticity=prod_score.synthetic_probability,
            authenticity_confidence=prod_score.model_confidence,
            identity_similarity=sim,
            identity_confidence=0.70,
            context_risk=(ctx.score / 100.0) if ctx else 0.0,
            context_confidence=0.60 if stt_text else 0.0,
            consequence=ctx.consequence if ctx else "low",
        )
        r = compute_risk(bundle, policy_cfg)
        d = evaluate(r.state, bundle.consequence, r.reasons, r.evidence_confidence, policy_cfg)
        lat_fusion.append((time.perf_counter() - t0) * 1000.0)

        lat_total.append((time.perf_counter() - t_w_start) * 1000.0)

    total_time_s = time.perf_counter() - t_bench_start
    rss_end_mb = proc.memory_info().rss / (1024 * 1024)

    throughput_fps = round(num_windows / total_time_s, 2)
    # Real-time factor: turnaround / window_duration (4.038s)
    # Hop budget: turnaround / hop_duration (1.000s)
    mean_turnaround_s = np.mean(lat_total) / 1000.0
    rtf = round(float(mean_turnaround_s / 4.038), 3)
    hop_utilization = round(float(mean_turnaround_s / 1.000) * 100.0, 1)

    results: Dict[str, Any] = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "windows_benchmarked": num_windows,
            "window_duration_seconds": 4.038,
            "hop_duration_seconds": 1.000,
            "device": device,
            "ml_pool_workers": settings.ML_POOL_WORKERS,
            "total_benchmark_time_seconds": round(total_time_s, 2),
        },
        "latencies": {
            "aasist_authenticity": stats_of(lat_aasist),
            "ecapa_speaker_identity": stats_of(lat_ecapa),
            "faster_whisper_stt": stats_of(lat_stt),
            "context_classifier": stats_of(lat_context),
            "risk_engine_and_policy": stats_of(lat_fusion),
            "end_to_end_window_turnaround": stats_of(lat_total),
        },
        "throughput": {
            "windows_per_second": throughput_fps,
            "real_time_factor_rtf": rtf,
            "hop_budget_utilization_pct": hop_utilization,
            "hop_realtime_satisfied": hop_utilization < 100.0,
        },
        "memory": {
            "rss_start_mb": round(rss_start_mb, 2),
            "rss_end_mb": round(rss_end_mb, 2),
            "rss_delta_mb": round(rss_end_mb - rss_start_mb, 2),
        },
    }

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(results, fh, indent=2)
        print(f"[{time.strftime('%H:%M:%S')}] Latency report saved to {out_path}")

    print("\n" + "=" * 64)
    print("  PHASE 1.8 PIPELINE LATENCY SCORECARD (CPU)")
    print("=" * 64)
    print(f"  • AASIST-L Authenticity: p50={results['latencies']['aasist_authenticity']['p50_ms']} ms, p95={results['latencies']['aasist_authenticity']['p95_ms']} ms")
    print(f"  • ECAPA-TDNN Identity:   p50={results['latencies']['ecapa_speaker_identity']['p50_ms']} ms, p95={results['latencies']['ecapa_speaker_identity']['p95_ms']} ms")
    print(f"  • faster-whisper STT:    p50={results['latencies']['faster_whisper_stt']['p50_ms']} ms, p95={results['latencies']['faster_whisper_stt']['p95_ms']} ms")
    print(f"  • Risk Fusion & Policy:  p50={results['latencies']['risk_engine_and_policy']['p50_ms']} ms, p95={results['latencies']['risk_engine_and_policy']['p95_ms']} ms")
    print(f"  • End-to-End Turnaround: p50={results['latencies']['end_to_end_window_turnaround']['p50_ms']} ms, p95={results['latencies']['end_to_end_window_turnaround']['p95_ms']} ms")
    print(f"  • Hop Budget (1.000s):   {hop_utilization}% used (Real-Time Satisfied: {hop_utilization < 100.0})")
    print(f"  • RSS Growth:            +{results['memory']['rss_delta_mb']} MB")
    print("=" * 64)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.8 Pipeline Latency Benchmark")
    parser.add_argument("--out", default="evaluation/results/phase1_8_multidomain/latency_bench.json", help="Output path")
    parser.add_argument("--windows", type=int, default=50, help="Number of windows to benchmark")
    parser.add_argument("--device", default="auto", help="Torch device")
    args = parser.parse_args()

    run_latency_benchmark(
        out_path=Path(args.out),
        num_windows=args.windows,
        device=args.device,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
