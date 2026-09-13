#!/usr/bin/env python3
"""
Phase 1.5 sustainability soak (§22) and multi-session isolation (§23).

Streams a long real-audio signal (looping the functional set) through the
production pipeline with async STT, and records whether the acoustic loop keeps
its cadence while Whisper works behind it.

    PIPELINE_MODE=real_ml python services/api/scripts/soak_async_stt.py \
        --seconds 120 --sessions 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import resource
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

try:
    import psutil  # noqa: F401
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False

from app.ml.preprocessing.ingest import iter_pcm_chunks, load_audio_file  # noqa: E402
from app.risk.policy import DEFAULT_POLICY_CONFIG  # noqa: E402
from app.websocket import gateway as gw  # noqa: E402
from app.websocket.manager import SessionState, manager  # noqa: E402
from app.websocket.pipeline import analyze_window, stream_windower, transcriber  # noqa: E402


def rss_mb() -> float:
    """
    Current resident set size in MB.

    ru_maxrss is a *peak* and its unit differs by platform (bytes on macOS,
    KB on Linux), so it cannot show growth. Prefer psutil's live RSS and fall
    back to a platform-correct peak only if psutil is unavailable.
    """
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024


def pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    return round(s[max(0, min(len(s) - 1, int(round(p / 100 * (len(s) - 1)))))], 2)


async def one_session(sid: str, audio: np.ndarray, seconds: float,
                      chunk_ms: int, q, realtime: bool) -> dict:
    stream_windower.reset(sid)
    state = SessionState(session_id=sid, user_id="soak",
                         policy_config=dict(DEFAULT_POLICY_CONFIG))
    manager._states[sid] = state
    q.reopen_session(sid)

    def submit(ws, a):
        state.context_pending = True
        q.submit(gw.STTJob(session_id=sid, window_seq=ws, audio=a))

    crit, depths = [], []
    chunks_sent = windows = 0
    deadline = time.perf_counter() + seconds
    chunks = list(iter_pcm_chunks(audio, chunk_ms))
    i = 0
    while time.perf_counter() < deadline:
        chunk = chunks[i % len(chunks)]      # loop the file to fill the duration
        i += 1
        t0 = time.perf_counter()
        analyze_window(state, chunk, pipeline_mode="live", stt_submit=submit)
        dt = (time.perf_counter() - t0) * 1000
        chunks_sent += 1
        if (state.last_stage_ms or {}).get("window_scored"):
            crit.append(dt)
            windows += 1
            depths.append(q.depth())
        if realtime:
            await asyncio.sleep(max(0.0, chunk_ms / 1000 - dt / 1000))
        else:
            await asyncio.sleep(0)

    return {"session_id": sid, "chunks_sent": chunks_sent,
            "windows_analyzed": windows,
            "critical_p50_ms": pct(crit, 50), "critical_p95_ms": pct(crit, 95),
            "max_queue_depth_seen": max(depths) if depths else 0,
            "context_applied_window": state.last_context_seq,
            "stale_results": state.stale_stt_results,
            "duplicate_results": state.duplicate_stt_results,
            "risk_history_len": len(state.risk_history),
            "final_risk": state.risk_history[-1] if state.risk_history else None}


async def run(args) -> dict:
    manifest = json.load(open(REPO / args.set))
    items = [i for i in manifest["items"] if (REPO / i["file"]).is_file()]
    audio, _ = load_audio_file(REPO / max(items, key=lambda i: i["duration_s"])["file"])

    await gw._ensure_stt_queue()
    q = gw.stt_queue
    rss0 = rss_mb()
    t0 = time.perf_counter()

    # Sample RSS during the run so one-time lazy model loading can be told
    # apart from genuine unbounded growth.
    samples = []

    async def sampler():
        while True:
            samples.append({"t_s": round(time.perf_counter() - t0, 1),
                            "rss_mb": round(rss_mb(), 1)})
            await asyncio.sleep(10)

    sample_task = asyncio.create_task(sampler())

    results = await asyncio.gather(*[
        one_session(f"soak-{n}", audio, args.seconds, args.chunk_ms, q, args.realtime)
        for n in range(args.sessions)
    ])

    sample_task.cancel()
    # Let outstanding STT drain before reporting.
    deadline = time.perf_counter() + 120
    while time.perf_counter() < deadline:
        done = q.metrics.completed + q.metrics.failed + q.metrics.timed_out
        if q.depth() == 0 and done >= q.metrics.submitted:
            break
        await asyncio.sleep(0.5)

    elapsed = time.perf_counter() - t0
    m = q.metrics.snapshot()
    for n in range(args.sessions):
        stream_windower.reset(f"soak-{n}")
        manager._states.pop(f"soak-{n}", None)
    await q.stop()

    return {
        "pipeline_mode_setting": args.set and __import__(
            "app.core.config", fromlist=["settings"]).settings.PIPELINE_MODE,
        "transcriber_is_real_ml": transcriber.is_real_ml,
        "requested_seconds": args.seconds, "sessions": args.sessions,
        "chunk_ms": args.chunk_ms, "realtime_paced": args.realtime,
        "wall_seconds": round(elapsed, 1),
        "per_session": results,
        "stt": m,
        "memory": {"rss_start_mb": round(rss0, 1), "rss_end_mb": round(rss_mb(), 1),
                   "growth_mb": round(rss_mb() - rss0, 1),
                   "source": "psutil rss" if _HAS_PSUTIL else "ru_maxrss peak",
                   "samples": samples,
                   "growth_second_half_mb": (
                       round(samples[-1]["rss_mb"] - samples[len(samples) // 2]["rss_mb"], 1)
                       if len(samples) >= 4 else None)},
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--sessions", type=int, default=1)
    ap.add_argument("--chunk-ms", type=int, default=100)
    ap.add_argument("--set", default="evaluation/functional/functional_test_set.json")
    ap.add_argument("--realtime", action="store_true", default=True)
    ap.add_argument("--no-realtime", dest="realtime", action="store_false")
    ap.add_argument("--out", default="evaluation/results/phase1_5_soak.json")
    args = ap.parse_args()

    rep = asyncio.run(run(args))
    (REPO / args.out).write_text(json.dumps(rep, indent=2))
    print(f"soak {args.seconds}s x {args.sessions} session(s), wall {rep['wall_seconds']}s")
    for s in rep["per_session"]:
        print(f"  {s['session_id']}: chunks={s['chunks_sent']} windows={s['windows_analyzed']} "
              f"crit p50={s['critical_p50_ms']} p95={s['critical_p95_ms']} "
              f"maxdepth={s['max_queue_depth_seen']} ctx@{s['context_applied_window']} "
              f"stale={s['stale_results']} dup={s['duplicate_results']}")
    print(f"  STT: {rep['stt']}")
    print(f"  memory: {rep['memory']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
