#!/usr/bin/env python3
"""
End-to-end real-audio latency benchmark (§21).

Streams FUNCTIONAL_TEST audio through the production pipeline and reports the
measured cost of each stage. Cold start (first window, models warming) is
separated from steady state.

This measures SERVER-SIDE work only. It does not include network transport or
UI rendering, and it does not include the 4.038 s of audio that must accumulate
before the first window exists — that term is reported separately because it
dominates and is not reducible by optimisation.

    PIPELINE_MODE=real_ml python services/api/scripts/benchmark_realtime.py
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
API = REPO / "services" / "api"
for p in (str(API), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.ml.preprocessing.ingest import iter_pcm_chunks, load_audio_file  # noqa: E402
from app.risk.policy import DEFAULT_POLICY_CONFIG  # noqa: E402
from app.websocket.manager import SessionState  # noqa: E402
from app.websocket.pipeline import (  # noqa: E402
    MODEL_VERSIONS, analyze_window, stream_windower,
)


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round((p / 100.0) * (len(xs) - 1)))))
    return xs[k]


def summarise(name, xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"stage": name, "n": 0}
    return {"stage": name, "n": len(xs),
            "mean_ms": round(st.mean(xs), 2),
            "p50_ms": round(pct(xs, 50), 2),
            "p95_ms": round(pct(xs, 95), 2),
            "max_ms": round(max(xs), 2)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="evaluation/functional/functional_test_set.json")
    ap.add_argument("--chunk-ms", type=int, default=100)
    ap.add_argument("--out", default="evaluation/results/phase_realaudio_latency.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    manifest = json.load(open(REPO / args.set))
    items = manifest["items"][: args.limit] if args.limit else manifest["items"]

    cold, steady = {}, {}
    windows_scored = 0
    first = True

    for it in items:
        audio, meta = load_audio_file(REPO / it["file"])
        sid = f"bench-{Path(it['file']).stem}"
        stream_windower.reset(sid)
        state = SessionState(session_id=sid, user_id="bench",
                             policy_config=dict(DEFAULT_POLICY_CONFIG))
        for chunk in iter_pcm_chunks(audio, args.chunk_ms):
            t0 = time.perf_counter()
            analyze_window(state, chunk, pipeline_mode="live")
            wall = (time.perf_counter() - t0) * 1000
            stages = dict(getattr(state, "last_stage_ms", {}) or {})
            if not stages or not stages.pop("window_scored", False):
                # Silent chunk, or a chunk that only topped up the buffer: no
                # model ran, so including it would understate real latency.
                continue
            stages["server_event_generation"] = round(wall, 2)
            windows_scored += 1
            bucket = cold if first else steady
            for k, v in stages.items():
                bucket.setdefault(k, []).append(v)
            first = False
        stream_windower.reset(sid)

    order = ["authenticity", "identity", "stt", "context", "risk_fusion",
             "total", "server_event_generation"]
    report = {
        "pipeline_mode_setting": settings.PIPELINE_MODE,
        "model_versions": MODEL_VERSIONS,
        "chunk_ms": args.chunk_ms,
        "files": len(items),
        "windows_measured": windows_scored,
        "note_measurement": ("only chunks where the windower emitted a full analysis window are counted; buffer-fill chunks run no model"),
        "audio_window_accumulation_ms": settings.ANALYSIS_WINDOW_MS,
        "hop_ms": settings.ANALYSIS_HOP_MS,
        "cold_start_first_window": {k: summarise(k, cold.get(k, [])) for k in order},
        "steady_state": {k: summarise(k, steady.get(k, [])) for k in order},
        "excluded_from_these_numbers": [
            "network/WebSocket transport",
            "client rendering",
            f"the {settings.ANALYSIS_WINDOW_MS} ms of audio that must accumulate "
            "before any window can be scored",
        ],
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (REPO / args.out).write_text(json.dumps(report, indent=2))

    print(f"pipeline_mode={report['pipeline_mode_setting']}  "
          f"scored windows={windows_scored}  chunk={args.chunk_ms}ms  "
          f"(buffer-fill chunks excluded)")
    print(f"{'stage':<26}{'n':>5}{'mean':>9}{'p50':>9}{'p95':>9}{'max':>9}")
    for k in order:
        s = report["steady_state"][k]
        if s["n"]:
            print(f"{k:<26}{s['n']:>5}{s['mean_ms']:>9.1f}{s['p50_ms']:>9.1f}"
                  f"{s['p95_ms']:>9.1f}{s['max_ms']:>9.1f}")
    c = report["cold_start_first_window"].get("total", {})
    if c.get("n"):
        print(f"cold start (first window total): {c['mean_ms']:.1f} ms")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
