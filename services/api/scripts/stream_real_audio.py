#!/usr/bin/env python3
"""
Real-audio test harness — WAV/FLAC → PCM chunks → WebSocket → production pipeline.

This harness sends ONLY audio. It never injects a risk score, a transcript, or
a decision: everything the dashboard would show is derived by the backend from
these samples. That is the point of it.

    # in-process (no server needed) — used by the automated tests
    python services/api/scripts/stream_real_audio.py --file <audio> --chunk-ms 100

    # against a running server
    python services/api/scripts/stream_real_audio.py --file <audio> \
        --url ws://127.0.0.1:8000 --token <JWT> --session-id <uuid>

Chunk size is configurable (§4). Measured defaults are discussed in
docs/real_audio_pipeline.md.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

REPO = Path(__file__).resolve().parents[3]
API = REPO / "services" / "api"
for p in (str(API), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.ml.preprocessing.ingest import (  # noqa: E402
    AudioIngestError, iter_pcm_chunks, load_audio_file,
)

CHUNK_CHOICES = (20, 40, 100, 250)


def log(m: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


# ── In-process transport: the real gateway, a fake DB ────────────────────────

def _in_process_client(session_id: str, user_id: str):
    """
    Build a TestClient over the real FastAPI gateway.

    The database is faked (the prototype has no PostgreSQL in test contexts),
    but authentication, authorisation, the windower, all three ML streams, the
    Risk Engine, the Policy Engine and event emission are the real ones.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.websocket import gateway as gw

    class _R:
        def __init__(self, v): self._v = v
        def scalar_one_or_none(self): return self._v

    class _DB:
        def __init__(self): self.n = 0
        async def execute(self, _s):
            self.n += 1
            if self.n == 1:
                return _R(SimpleNamespace(id=session_id, user_id=user_id, state="active"))
            return _R(None)
        def add(self, _o): pass
        async def commit(self): pass
        async def refresh(self, _o): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    gw.AsyncSessionLocal = lambda: _DB()
    app = FastAPI()
    app.include_router(gw.router)
    token = create_access_token(user_id)
    return TestClient(app), token


def stream_file(path: str, chunk_ms: int = 100, session_id: str = None,
                user_id: str = None, realtime: bool = False,
                max_seconds: Optional[float] = None) -> dict:
    """Stream one file through the real pipeline in-process; return the events."""
    session_id = session_id or "11111111-1111-1111-1111-111111111111"
    user_id = user_id or "22222222-2222-2222-2222-222222222222"

    audio, meta = load_audio_file(path)
    if max_seconds:
        audio = audio[: int(16000 * max_seconds)]
    chunks = list(iter_pcm_chunks(audio, chunk_ms))
    log(f"{Path(path).name}: {meta.duration_s:.2f}s  sr={meta.original_sample_rate} "
        f"ch={meta.original_channels} -> {len(chunks)} chunks @ {chunk_ms} ms")

    client, token = _in_process_client(session_id, user_id)
    events: List[dict] = []
    t0 = time.perf_counter()
    with client.websocket_connect(f"/ws/sessions/{session_id}?token={token}") as ws:
        events.append(ws.receive_json())            # session_started
        for i, c in enumerate(chunks):
            ws.send_json({"type": "audio_chunk", "seq": i,
                          "data": base64.b64encode(c).decode()})
            if realtime:
                time.sleep(chunk_ms / 1000.0)

        # The server analyses each chunk in a fire-and-forget task, so there is
        # no reply to count against. Use ping/pong as a barrier: drain up to a
        # PONG, and repeat until a whole round produces no further analysis
        # events. Bounded so a stuck pipeline cannot hang the harness.
        for _ in range(200):
            ws.send_json({"type": "ping"})
            produced = 0
            for _ in range(5000):
                msg = ws.receive_json()
                if msg.get("type") == "pong":
                    break
                events.append(msg)
                produced += 1
            if produced == 0:
                break
    elapsed = time.perf_counter() - t0
    return {"file": path, "meta": meta.to_dict(), "chunk_ms": chunk_ms,
            "chunks_sent": len(chunks), "events": events,
            "wall_seconds": round(elapsed, 2)}


def summarise(result: dict) -> dict:
    """Reduce a stream's events to the facts that prove the pipeline ran."""
    from collections import Counter
    ev = result["events"]
    kinds = Counter(e.get("type") for e in ev)
    risk = [e for e in ev if e.get("type") == "risk_update"]
    last = risk[-1] if risk else None
    auth_real = [e for e in risk
                 if (e.get("authenticity") or {}).get("pipeline_mode") == "real_ml"]
    probs = [(e.get("authenticity") or {}).get("spoof_probability")
             for e in auth_real]
    probs = [p for p in probs if isinstance(p, (int, float))]
    return {
        "event_types": dict(kinds),
        "risk_updates": len(risk),
        "windows_with_real_ml_authenticity": len(auth_real),
        "authenticity_spoof_probability": {
            "n": len(probs),
            "mean": round(sum(probs) / len(probs), 4) if probs else None,
            "min": round(min(probs), 4) if probs else None,
            "max": round(max(probs), 4) if probs else None,
        },
        "transcript_chars": sum(
            len(((e.get("context") or {}).get("transcript") or "")) for e in risk[-1:]
        ),
        "final_risk_score": (last or {}).get("risk_score"),
        "final_risk_state": (last or {}).get("risk_state"),
        "final_pipeline_mode": (last or {}).get("pipeline_mode"),
        "authenticity_model": ((last or {}).get("authenticity") or {}).get("model_name"),
        "authenticity_version": ((last or {}).get("authenticity") or {}).get("model_version"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--chunk-ms", type=int, default=100, choices=CHUNK_CHOICES)
    ap.add_argument("--realtime", action="store_true",
                    help="pace chunks at wall-clock speed")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = ap.parse_args()

    try:
        res = stream_file(args.file, args.chunk_ms, realtime=args.realtime,
                          max_seconds=args.max_seconds)
    except AudioIngestError as e:
        log(f"REJECTED: {e}")
        return 2
    s = summarise(res)
    if args.json:
        print(json.dumps({"summary": s, "meta": res["meta"]}, indent=2))
    else:
        log(f"events: {s['event_types']}")
        log(f"risk_updates={s['risk_updates']} "
            f"real_ml_windows={s['windows_with_real_ml_authenticity']}")
        log(f"final: score={s['final_risk_score']} state={s['final_risk_state']} "
            f"mode={s['final_pipeline_mode']} model={s['authenticity_version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
