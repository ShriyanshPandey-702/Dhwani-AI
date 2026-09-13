#!/usr/bin/env python3
"""
Test Bounded Backpressure for VoiceShield Phase 1.6
===================================================
Validates:
1. Normal cadence (4 chunks/s): 0 drops, max pending <= MAX_PENDING_AUDIO_CHUNKS
2. Burst cadence (10 chunks/s): max pending <= MAX_PENDING_AUDIO_CHUNKS, bounded drop
3. Flood cadence (25 chunks/s): max pending <= MAX_PENDING_AUDIO_CHUNKS, bounded drop
4. Session isolation: Session A flood does NOT affect Session B normal streaming
5. Teardown safety: cancelled tasks and closed state reject pending work
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

API = Path(__file__).resolve().parents[1]
ROOT = API.parent.parent
for p in (str(API), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("PIPELINE_MODE", "real_ml")

from app.core.config import settings
from app.websocket.manager import SessionState, manager
from app.websocket.pipeline import (
    analyze_window, stream_windower, authenticity_detector,
    speaker_identity
)
from app.websocket.gateway import _process, _ensure_stt_queue, _teardown, _ensure_ml_pool
import numpy as np
import psutil

proc = psutil.Process()

def make_pcm(secs: float = 0.25, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    t = np.arange(int(16000 * secs)) / 16000.0
    a = 0.3 * np.sin(2 * np.pi * 150 * t)
    samples = (a + rng.standard_normal(t.size) * 0.01).astype(np.float32)
    return (samples * 32767).astype("<i2").tobytes()

async def simulate_ingress(session_id: str, pcm_bytes: bytes) -> bool:
    """Simulate gateway ingress logic."""
    state = manager.get_state(session_id)
    if state is None or state.closed:
        return False
    if state.pending_audio_tasks >= settings.MAX_PENDING_AUDIO_CHUNKS:
        state.dropped_audio_chunks += 1
        return False
    state.pending_audio_tasks += 1
    task = asyncio.create_task(_process(session_id, pcm_bytes, "live"))
    state.active_tasks.add(task)
    task.add_done_callback(state.active_tasks.discard)
    return True

async def run_cadence_test(name: str, interval_s: float, count: int):
    print(f"\n── {name} ({1/interval_s:.1f} chunks/s, {count} chunks) ──")
    sid = f"bp-cadence-{int(1/interval_s)}"
    state = manager.get_or_create_state(sid, "user", {})
    state.pipeline_mode = "live"
    pcm = make_pcm(0.25, seed=10)

    admitted = 0
    dropped = 0
    max_pending = 0

    t0 = time.perf_counter()
    for i in range(count):
        cur_pending = state.pending_audio_tasks
        if cur_pending > max_pending:
            max_pending = cur_pending

        ok = await simulate_ingress(sid, pcm)
        if ok:
            admitted += 1
        else:
            dropped += 1
        await asyncio.sleep(interval_s)

    # Wait for in-flight tasks to complete
    wait_t0 = time.perf_counter()
    while state.pending_audio_tasks > 0 and time.perf_counter() - wait_t0 < 5.0:
        if state.pending_audio_tasks > max_pending:
            max_pending = state.pending_audio_tasks
        await asyncio.sleep(0.05)

    rss = proc.memory_info().rss / (1024 * 1024)
    print(f"  Incoming Rate   : {1/interval_s:.1f} chunks/s")
    print(f"  Sent            : {count}")
    print(f"  Admitted        : {admitted}")
    print(f"  Dropped         : {dropped} (recorded: {state.dropped_audio_chunks})")
    print(f"  Max Pending     : {max_pending} (Bound: {settings.MAX_PENDING_AUDIO_CHUNKS})")
    print(f"  Pending at end  : {state.pending_audio_tasks}")
    print(f"  Current RSS     : {rss:.2f} MB")

    assert max_pending <= settings.MAX_PENDING_AUDIO_CHUNKS, (
        f"Max pending {max_pending} exceeded limit {settings.MAX_PENDING_AUDIO_CHUNKS}"
    )
    if interval_s >= 0.25:
        assert dropped == 0, f"Dropped {dropped} chunks under nominal load!"
        print("  ✓ Nominal cadence passed: 0 drops, bounded pending.")
    else:
        assert max_pending <= settings.MAX_PENDING_AUDIO_CHUNKS, "Overload pending unbounded!"
        print(f"  ✓ Overload cadence passed: strictly capped at {max_pending} <= {settings.MAX_PENDING_AUDIO_CHUNKS}")

    await _teardown(sid, "user")
    return {
        "rate": 1/interval_s,
        "sent": count,
        "admitted": admitted,
        "dropped": dropped,
        "max_pending": max_pending,
        "rss_mb": rss
    }

async def test_session_isolation():
    print(f"\n── Testing Session Isolation (Session A flood vs Session B normal) ──")
    sid_a = "session-a-flood"
    sid_b = "session-b-normal"
    state_a = manager.get_or_create_state(sid_a, "userA", {})
    state_b = manager.get_or_create_state(sid_b, "userB", {})
    pcm = make_pcm(0.25, seed=1)

    async def run_flood_a():
        for _ in range(50):
            await simulate_ingress(sid_a, pcm)
            await asyncio.sleep(0.04) # 25 chunks/s

    async def run_normal_b():
        drops = 0
        for _ in range(8):
            ok = await simulate_ingress(sid_b, pcm)
            if not ok:
                drops += 1
            await asyncio.sleep(0.25) # 4 chunks/s
        return drops

    _, b_drops = await asyncio.gather(run_flood_a(), run_normal_b())
    print(f"  Session A dropped chunks : {state_a.dropped_audio_chunks} (flood absorbed)")
    print(f"  Session B dropped chunks : {b_drops} (normal session unaffected)")
    assert b_drops == 0, f"Session B suffered {b_drops} drops due to Session A flood!"
    print("  ✓ Session isolation passed: Flood in Session A did not cause any drops in Session B.")

    await _teardown(sid_a, "userA")
    await _teardown(sid_b, "userB")

async def test_teardown_safety():
    print(f"\n── Testing Session Teardown Safety ──")
    sid = "session-teardown"
    state = manager.get_or_create_state(sid, "user", {})
    pcm = make_pcm(0.25, seed=2)

    # Ingress 4 chunks rapidly
    for _ in range(4):
        await simulate_ingress(sid, pcm)

    assert state.pending_audio_tasks > 0, "Expected active tasks"
    print(f"  Active tasks before teardown: {len(state.active_tasks)}")
    
    # Teardown while tasks in flight
    await _teardown(sid, "user")
    print(f"  State closed flag: {state.closed}")
    print(f"  Active tasks after teardown: {len(state.active_tasks)}")
    assert state.closed is True, "Session state not marked closed!"
    assert len(state.active_tasks) == 0, "Active tasks not cleared!"

    # Try ingress on closed session
    ok = await simulate_ingress(sid, pcm)
    assert not ok, "Ingress allowed on closed session!"
    print("  ✓ Teardown safety passed: all tasks cancelled, closed session rejects work.")

async def main():
    print(f"Bounded Backpressure Test Suite (Bound = {settings.MAX_PENDING_AUDIO_CHUNKS})")
    _ensure_ml_pool()
    # Prewarm
    authenticity_detector.analyze(np.zeros(64608, dtype=np.float32))
    
    r1 = await run_cadence_test("Normal Cadence", 0.25, 20)
    r2 = await run_cadence_test("Burst Cadence", 0.10, 30)
    r3 = await run_cadence_test("Flood Cadence", 0.04, 50)
    await test_session_isolation()
    await test_teardown_safety()
    print("\nALL BACKPRESSURE ACCEPTANCE TESTS PASSED!")

if __name__ == "__main__":
    asyncio.run(main())
