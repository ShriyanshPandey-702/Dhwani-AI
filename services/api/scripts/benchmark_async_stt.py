#!/usr/bin/env python3
"""
Phase 1.5 benchmark — critical path vs asynchronous STT.

Measures, separately and honestly:

  A. critical path        VAD -> AASIST -> ECAPA -> fuse -> policy -> events
  B. STT queue wait       submitted -> worker picks it up
  C. Whisper execution    worker start -> transcript returned
  D. semantic update      submitted -> context applied and re-decided

The comparison against Phase 1 is apples-to-apples only for (A): the Phase 1
"server total" included Whisper inline, which is exactly what this change
removes. Both numbers are reported so the difference is explicit.

Chunks are paced at wall-clock speed by default (`--realtime`), because running
them as fast as possible makes AASIST and Whisper contend for the same cores
and inflates the critical path in a way a real 1 s hop never would.

    PIPELINE_MODE=real_ml python services/api/scripts/benchmark_async_stt.py
"""

from __future__ import annotations

import argparse
import asyncio
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

from app.core.config import settings  # noqa: E402
from app.ml.preprocessing.ingest import iter_pcm_chunks, load_audio_file  # noqa: E402
from app.risk.policy import DEFAULT_POLICY_CONFIG  # noqa: E402
from app.websocket import gateway as gw  # noqa: E402
from app.websocket.manager import SessionState, manager  # noqa: E402
from app.websocket.pipeline import (  # noqa: E402
    MODEL_VERSIONS, analyze_window, stream_windower, transcriber,
)


def pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
    return round(s[k], 2)


def stats(name, xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"stage": name, "n": 0}
    return {"stage": name, "n": len(xs), "mean_ms": round(st.mean(xs), 2),
            "p50_ms": pct(xs, 50), "p95_ms": pct(xs, 95), "max_ms": round(max(xs), 2)}


async def run(args) -> dict:
    manifest = json.load(open(REPO / args.set))
    items = manifest["items"][: args.limit] if args.limit else manifest["items"]

    await gw._ensure_stt_queue()
    q = gw.stt_queue
    if args.workers != q.workers:
        await q.stop()
        q.workers = args.workers
        await q.start()

    critical, semantic = [], []
    windows = 0
    applied_at = {}

    original_apply = q._apply

    async def timed_apply(job, segment):
        await original_apply(job, segment)
        semantic.append((time.perf_counter() - job.submitted_at) * 1000)
    q._apply = timed_apply

    for it in items:
        audio, _ = load_audio_file(REPO / it["file"])
        sid = f"bench-{Path(it['file']).stem}"
        stream_windower.reset(sid)
        state = SessionState(session_id=sid, user_id="bench",
                             policy_config=dict(DEFAULT_POLICY_CONFIG))
        manager._states[sid] = state
        q.reopen_session(sid)

        def submit(ws, a, _sid=sid, _st=state):
            _st.context_pending = True
            q.submit(gw.STTJob(session_id=_sid, window_seq=ws, audio=a))

        for chunk in iter_pcm_chunks(audio, args.chunk_ms):
            t0 = time.perf_counter()
            analyze_window(state, chunk, pipeline_mode="live", stt_submit=submit)
            dt = (time.perf_counter() - t0) * 1000
            if (state.last_stage_ms or {}).get("window_scored"):
                critical.append(dt)
                windows += 1
            if args.realtime:
                await asyncio.sleep(max(0.0, args.chunk_ms / 1000 - dt / 1000))
            else:
                await asyncio.sleep(0)

        # Drain this session's STT before moving on.
        deadline = time.perf_counter() + 60
        while time.perf_counter() < deadline:
            done = q.metrics.completed + q.metrics.failed + q.metrics.timed_out
            if q.depth() == 0 and done >= q.metrics.submitted:
                break
            await asyncio.sleep(0.25)
        applied_at[sid] = state.last_context_seq
        stream_windower.reset(sid)
        manager._states.pop(sid, None)

    m = q.metrics.snapshot()
    q._apply = original_apply
    await q.stop()

    return {
        "pipeline_mode_setting": settings.PIPELINE_MODE,
        "transcriber_is_real_ml": transcriber.is_real_ml,
        "model_versions": MODEL_VERSIONS,
        "chunk_ms": args.chunk_ms, "realtime_paced": args.realtime,
        "stt_workers": args.workers, "stt_max_queue": q.max_queue,
        "stt_every_n_windows": gw.STTJob and __import__(
            "app.websocket.stt_queue", fromlist=["x"]).STT_EVERY_N_WINDOWS,
        "windows_scored": windows,
        "critical_path": stats("critical_path", critical),
        "semantic_update": stats("semantic_update", semantic),
        "stt": m,
        "audio_window_accumulation_ms": settings.ANALYSIS_WINDOW_MS,
        "hop_ms": settings.ANALYSIS_HOP_MS,
        "context_applied_window_per_session": applied_at,
        "note": ("critical_path excludes Whisper by construction — that is the "
                 "point of the change, not a measurement trick. Whisper is "
                 "reported in full under stt.exec_ms_*."),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="evaluation/functional/functional_test_set.json")
    ap.add_argument("--chunk-ms", type=int, default=100)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--realtime", action="store_true", default=True)
    ap.add_argument("--no-realtime", dest="realtime", action="store_false")
    ap.add_argument("--out", default="evaluation/results/phase1_5_async_stt.json")
    args = ap.parse_args()

    report = asyncio.run(run(args))
    out = REPO / args.out
    out.write_text(json.dumps(report, indent=2))

    c, s = report["critical_path"], report["semantic_update"]
    print(f"workers={args.workers} chunk={args.chunk_ms}ms paced={args.realtime} "
          f"windows={report['windows_scored']}")
    print(f"  CRITICAL PATH   p50 {c.get('p50_ms')} ms   p95 {c.get('p95_ms')} ms "
          f"(n={c.get('n')})")
    print(f"  SEMANTIC UPDATE p50 {s.get('p50_ms')} ms   p95 {s.get('p95_ms')} ms "
          f"(n={s.get('n')})")
    print(f"  STT {report['stt']}")
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
