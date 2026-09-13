#!/usr/bin/env python3
"""
Streaming-compatibility and latency check for a Phase 1 checkpoint (§19).

Verifies the checkpoint is a drop-in replacement — same window, same hop, same
preprocessing, same output schema — and measures the real end-to-end budget.

Never reports "zero latency": a full 4038 ms window must accumulate before any
score exists, and that term dominates.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "services" / "api"))

from app.core.config import settings  # noqa: E402
from app.ml.authenticity.aasist import MODEL_CONFIGS, NB_SAMP, SAMPLE_RATE  # noqa: E402
from app.ml.authenticity.vendor.aasist_model import Model  # noqa: E402
from app.risk import policy  # noqa: E402
from app.risk.engine import EvidenceBundle, compute_risk  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--out", default="evaluation/results")
    args = ap.parse_args()

    m = Model(MODEL_CONFIGS["AASIST-L"])
    m.load_state_dict(torch.load(args.checkpoint, map_location="cpu"), strict=True)
    m.to(args.device).eval()

    sr = SAMPLE_RATE
    t = np.arange(NB_SAMP) / sr
    x = (0.3 * np.sin(2 * np.pi * 140 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
    x += (np.random.default_rng(0).standard_normal(x.size) * 0.01).astype(np.float32)
    xt = torch.from_numpy(x).unsqueeze(0).to(args.device)

    with torch.no_grad():
        out = m(xt)
    schema_ok = isinstance(out, (tuple, list)) and len(out) == 2 and tuple(out[1].shape) == (1, 2)

    lat = []
    with torch.no_grad():
        for _ in range(3):
            m(xt)
        for _ in range(args.n):
            t0 = time.perf_counter(); m(xt); lat.append((time.perf_counter() - t0) * 1000)
    lat = np.array(lat)

    ev = EvidenceBundle(authenticity=0.8, authenticity_confidence=0.9,
                        identity_similarity=0.4, identity_confidence=0.8,
                        context_risk=0.5, context_confidence=0.8, consequence="high")
    pol = []
    for _ in range(3000):
        t0 = time.perf_counter()
        r = compute_risk(ev)
        policy.evaluate(r.state, ev.consequence, r.reasons, r.evidence_confidence)
        pol.append((time.perf_counter() - t0) * 1e6)
    pol = np.array(pol)

    win_ms = settings.ANALYSIS_WINDOW_MS
    hop_ms = settings.ANALYSIS_HOP_MS
    rec = {
        "model_version": args.tag, "checkpoint": args.checkpoint, "device": args.device,
        "streaming_contract": {
            "sample_rate": sr, "input_samples": NB_SAMP,
            "ANALYSIS_WINDOW_MS": win_ms, "ANALYSIS_HOP_MS": hop_ms,
            "MIN_ANALYSIS_MS": settings.MIN_ANALYSIS_MS,
            "unchanged_from_baseline": (sr == 16000 and NB_SAMP == 64600
                                        and win_ms == 4038 and hop_ms == 1000),
            "output_schema_ok": bool(schema_ok),
            "loads_with_strict_true": True,
        },
        "inference_ms": {"mean": float(lat.mean()), "p50": float(np.percentile(lat, 50)),
                         "p95": float(np.percentile(lat, 95)), "max": float(lat.max()),
                         "n": args.n},
        "risk_and_policy_ms": {"mean": float(pol.mean() / 1000),
                               "p95": float(np.percentile(pol, 95) / 1000)},
        "end_to_end_budget": {
            "window_accumulation_ms": win_ms,
            "hop_quantisation_ms": [0, hop_ms],
            "network_transport": "not measured",
            "cold_start_s": round((win_ms + lat.mean()) / 1000, 2),
            "steady_state_s": [round(lat.mean() / 1000, 2),
                               round((hop_ms + lat.mean()) / 1000, 2)],
            "note": "never zero — a full window must accumulate before any score exists",
        },
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    dest = REPO / args.out / f"phase1_latency_{args.tag}.json"
    dest.write_text(json.dumps(rec, indent=2))
    print(json.dumps(rec["streaming_contract"], indent=2))
    print(f"inference p50 {rec['inference_ms']['p50']:.1f} ms  "
          f"p95 {rec['inference_ms']['p95']:.1f} ms")
    print(f"cold start {rec['end_to_end_budget']['cold_start_s']} s  "
          f"steady state {rec['end_to_end_budget']['steady_state_s']} s")
    print(f"-> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
