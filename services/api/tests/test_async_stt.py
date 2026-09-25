"""
Phase 1.5 — asynchronous STT.

The security property under test is not "it is faster". It is that moving
transcription off the critical path cannot corrupt authoritative state: a late,
duplicated, out-of-order, failed or cross-session transcript must never change
what the Risk Engine already decided from newer evidence.

Most tests drive a fake transcriber so they are fast and deterministic. One
integration test exercises the real faster-whisper path (§29).
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.websocket import gateway as gw
from app.websocket.manager import SessionState, manager
from app.websocket.pipeline import analyze_window, stream_windower, transcriber
from app.websocket.stt_queue import (
    STT_EVERY_N_WINDOWS, STTJob, STTQueue,
)

REPO = Path(__file__).resolve().parents[3]
FUNCTIONAL = REPO / "evaluation" / "functional" / "functional_test_set.json"


def _audio(seconds=4.1, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(16000 * seconds)) / 16000
    a = 0.3 * np.sin(2 * np.pi * 150 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
    return (a + rng.standard_normal(t.size) * 0.01).astype(np.float32)


def _seg(text="please send the otp code now", conf=0.9):
    return SimpleNamespace(text=text, is_mock=False, model_name="faster-whisper",
                           pipeline_mode="real_ml", language="en", confidence=conf)


def _state(sid="s1"):
    st = SessionState(session_id=sid, user_id="u",
                      policy_config=dict(DEFAULT_POLICY_CONFIG))
    manager._states[sid] = st
    return st


@pytest.fixture
def clean_manager():
    yield
    manager._states.clear()


# ══ 1-5  ASYNC BEHAVIOUR ═════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stt_job_is_queued_and_the_worker_executes_it():
    seen = []

    def fake_transcribe(sid, audio):
        seen.append(sid)
        return _seg()

    applied = []

    async def apply(job, seg):
        applied.append((job.session_id, job.window_seq, seg.text))

    q = STTQueue(fake_transcribe, apply, max_queue=4, workers=1)
    await q.start()
    assert q.submit(STTJob("s", 4, _audio()))
    for _ in range(100):
        if applied:
            break
        await asyncio.sleep(0.02)
    await q.stop()

    assert seen == ["s"]
    assert applied and applied[0][:2] == ("s", 4)
    assert q.metrics.submitted == 1 and q.metrics.completed == 1


@pytest.mark.asyncio
async def test_submitting_never_blocks_the_caller_even_when_stt_is_slow():
    def slow(sid, audio):
        time.sleep(0.4)
        return _seg()

    async def apply(job, seg):
        pass

    q = STTQueue(slow, apply, max_queue=8, workers=1)
    await q.start()
    t0 = time.perf_counter()
    for i in range(4):
        q.submit(STTJob("s", i, _audio()))
    submit_ms = (time.perf_counter() - t0) * 1000
    await q.stop()
    # Four jobs that take 400 ms each must still enqueue in ~no time.
    assert submit_ms < 50, submit_ms


def test_analyze_window_does_not_run_whisper_when_an_async_sink_is_given(clean_manager):
    """The critical path must not include transcription (§A, §B)."""
    if not transcriber.is_real_ml:
        pytest.skip("scripted transcriber: mock mode stays synchronous by design")
    st = _state("nosync")
    stream_windower.reset("nosync")
    submitted = []
    # Long enough for the cadence to fire: the first window needs 4.038 s and
    # STT runs every 4th window, so at least ~8 s of audio is required.
    audio = _audio(10.0)
    from app.ml.preprocessing.ingest import iter_pcm_chunks
    for chunk in iter_pcm_chunks(audio, 100):
        analyze_window(st, chunk, pipeline_mode="live",
                       stt_submit=lambda ws, a: submitted.append(ws))
        if (st.last_stage_ms or {}).get("window_scored"):
            assert st.last_stage_ms["stt"] == 0.0, "Whisper ran on the critical path"
    stream_windower.reset("nosync")
    assert submitted, "no STT work was ever queued"


@pytest.mark.asyncio
async def test_transcript_updates_context_and_triggers_a_new_decision(clean_manager):
    st = _state("ctx")
    st.last_authenticity = {"spoof_probability": 0.6, "confidence": 0.7}
    st.last_identity = {"match_score": 60, "confidence": 0.7,
                        "enrollment_status": "ENROLLED"}
    before = st.last_context
    published = []

    async def fake_publish_many(sid, msgs):
        published.extend(msgs)

    orig = manager.publish_many
    manager.publish_many = fake_publish_many
    try:
        await gw._apply_transcript(STTJob("ctx", 4, _audio()), _seg())
    finally:
        manager.publish_many = orig

    assert before is None and st.last_context is not None, "context never arrived"
    assert st.last_context_seq == 4
    assert any(m["type"] == "risk_update" for m in published), \
        "no authoritative recomputation was published"


# ══ 6-9  ORDERING ════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stale_result_cannot_overwrite_newer_context(clean_manager):
    st = _state("stale")
    await gw._apply_transcript(STTJob("stale", 12, _audio()), _seg("newer text"))
    newer = dict(st.last_context or {})
    assert st.last_context_seq == 12

    await gw._apply_transcript(STTJob("stale", 8, _audio()), _seg("older text"))
    assert st.last_context_seq == 12, "an older window moved the applied cursor"
    assert st.last_context == newer, "stale transcript overwrote newer context"
    assert st.stale_stt_results == 1


@pytest.mark.asyncio
async def test_duplicate_result_is_idempotent(clean_manager):
    st = _state("dup")
    await gw._apply_transcript(STTJob("dup", 4, _audio()), _seg())
    snapshot = dict(st.last_context or {})
    await gw._apply_transcript(STTJob("dup", 4, _audio()), _seg("different text"))
    assert st.last_context == snapshot
    assert st.duplicate_stt_results == 1


@pytest.mark.asyncio
async def test_out_of_order_completion_settles_on_the_newest_window(clean_manager):
    st = _state("ooo")
    for seq, text in ((12, "twelve"), (4, "four"), (8, "eight"), (16, "sixteen")):
        await gw._apply_transcript(STTJob("ooo", seq, _audio()), _seg(text))
    assert st.last_context_seq == 16
    assert st.stale_stt_results == 2      # 4 and 8 arrived after 12


@pytest.mark.asyncio
async def test_a_late_transcript_cannot_move_risk_backwards(clean_manager):
    """§14: newer authoritative risk must survive an older STT result."""
    st = _state("mono")
    st.last_authenticity = {"spoof_probability": 0.9, "confidence": 0.8}
    st.last_identity = {"match_score": 10, "confidence": 0.8,
                        "enrollment_status": "ENROLLED"}
    await gw._apply_transcript(STTJob("mono", 10, _audio()),
                               _seg("send the otp and transfer the money now"))
    high = st.last_context_seq
    risk_after_new = st.risk_history[-1] if st.risk_history else None

    await gw._apply_transcript(STTJob("mono", 2, _audio()), _seg("hello"))
    assert st.last_context_seq == high
    if risk_after_new is not None:
        assert st.risk_history[-1] == risk_after_new, "risk regressed on a stale result"


# ══ 10-12  SESSION ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_a_result_for_one_session_never_touches_another(clean_manager):
    a, b = _state("A"), _state("B")
    await gw._apply_transcript(STTJob("A", 4, _audio()), _seg("only for A"))
    assert a.last_context is not None
    assert b.last_context is None, "cross-session contamination"
    assert b.last_context_seq == -1


@pytest.mark.asyncio
async def test_terminated_session_ignores_a_late_transcript(clean_manager):
    st = _state("gone")
    gw.stt_queue.close_session("gone")
    try:
        await gw._apply_transcript(STTJob("gone", 4, _audio()), _seg())
        assert st.last_context is None, "a closed session was resurrected"
    finally:
        gw.stt_queue.reopen_session("gone")


@pytest.mark.asyncio
async def test_result_for_a_vanished_session_is_dropped_safely(clean_manager):
    before = gw.stt_queue.metrics.dropped_session_gone
    await gw._apply_transcript(STTJob("never-existed", 4, _audio()), _seg())
    assert gw.stt_queue.metrics.dropped_session_gone == before + 1


@pytest.mark.asyncio
async def test_closed_session_refuses_new_work():
    q = STTQueue(lambda s, a: _seg(), lambda j, s: asyncio.sleep(0),
                 max_queue=4, workers=1)
    await q.start()
    q.close_session("x")
    assert q.submit(STTJob("x", 1, _audio())) is False
    q.reopen_session("x")
    assert q.submit(STTJob("x", 1, _audio())) is True
    await q.stop()


# ══ 13-15  QUEUE ═════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_queue_is_bounded_and_drops_oldest_with_a_counter():
    started = asyncio.Event()

    def blocking(sid, audio):
        started.set()
        time.sleep(1.5)
        return _seg()

    async def apply(job, seg):
        pass

    q = STTQueue(blocking, apply, max_queue=2, workers=1)
    await q.start()
    q.submit(STTJob("s", 1, _audio()))
    await asyncio.wait_for(started.wait(), timeout=5)
    for i in range(2, 8):                 # overflow a 2-slot queue
        q.submit(STTJob("s", i, _audio()))
    assert q.depth() <= 2, q.depth()
    assert q.metrics.dropped_queue_full > 0
    await q.stop()


@pytest.mark.asyncio
async def test_queue_depth_never_exceeds_its_configured_maximum():
    def slow(sid, audio):
        time.sleep(0.3)
        return _seg()

    q = STTQueue(slow, lambda j, s: asyncio.sleep(0), max_queue=3, workers=1)
    await q.start()
    for i in range(30):
        q.submit(STTJob("s", i, _audio()))
        assert q.depth() <= 3
    await q.stop()
    assert q.metrics.max_queue_depth <= 3


# ══ 16-18  FAILURE ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_whisper_exception_is_contained_and_counted():
    def boom(sid, audio):
        raise RuntimeError("whisper exploded")

    applied = []

    async def apply(job, seg):
        applied.append(job)

    q = STTQueue(boom, apply, max_queue=4, workers=1)
    await q.start()
    q.submit(STTJob("s", 1, _audio()))
    for _ in range(100):
        if q.metrics.failed:
            break
        await asyncio.sleep(0.02)
    # The worker must still be alive and able to take the next job.
    ok = []

    def fine(sid, audio):
        ok.append(1)
        return _seg()
    q._transcribe = fine
    q.submit(STTJob("s", 2, _audio()))
    for _ in range(100):
        if ok:
            break
        await asyncio.sleep(0.02)
    await q.stop()
    assert q.metrics.failed == 1
    assert ok, "the worker died after one failure"
    # Job 1 raised and must never have been applied; job 2 succeeded and must.
    assert [j.window_seq for j in applied] == [2], \
        "a failed transcription was applied, or a good one was lost"


@pytest.mark.asyncio
async def test_whisper_timeout_is_handled_without_killing_the_worker():
    def hang(sid, audio):
        time.sleep(2.0)
        return _seg()

    q = STTQueue(hang, lambda j, s: asyncio.sleep(0), max_queue=4, workers=1,
                 timeout_s=0.2)
    await q.start()
    q.submit(STTJob("s", 1, _audio()))
    for _ in range(200):
        if q.metrics.timed_out:
            break
        await asyncio.sleep(0.02)
    await q.stop()
    assert q.metrics.timed_out == 1


@pytest.mark.asyncio
async def test_stt_failure_leaves_context_unavailable_not_safe(clean_manager):
    """A failed transcript must not be read as an absence of threat."""
    st = _state("failctx")
    st.last_authenticity = {"spoof_probability": 0.9, "confidence": 0.8}
    await gw._apply_transcript(STTJob("failctx", 4, _audio()), None)
    assert st.last_context is None, "missing STT invented context evidence"
    assert st.last_context_seq == 4       # cursor advances; evidence does not
    assert st.context_pending is False


def test_submitting_to_a_stopped_queue_is_a_no_op_not_a_crash():
    q = STTQueue(lambda s, a: _seg(), lambda j, s: asyncio.sleep(0))
    assert q.submit(STTJob("s", 1, _audio())) is False


# ══ 19-23  PIPELINE ══════════════════════════════════════════════════════════

def test_stt_cadence_is_paced_by_analysis_windows_not_chunks(clean_manager):
    """Overlapping windows would otherwise transcribe the same audio ~4x."""
    if not transcriber.is_real_ml:
        pytest.skip("scripted transcriber runs inline")
    from app.ml.preprocessing.ingest import iter_pcm_chunks
    st = _state("cadence")
    stream_windower.reset("cadence")
    submitted, scored = [], 0
    for chunk in iter_pcm_chunks(_audio(20.0), 100):
        analyze_window(st, chunk, pipeline_mode="live",
                       stt_submit=lambda ws, a: submitted.append(ws))
        if (st.last_stage_ms or {}).get("window_scored"):
            scored += 1
    stream_windower.reset("cadence")
    assert scored > 0
    assert all(ws == 1 or ws % STT_EVERY_N_WINDOWS == 0 for ws in submitted), submitted
    assert len(submitted) <= scored // STT_EVERY_N_WINDOWS + 2


@pytest.mark.skipif(not FUNCTIONAL.is_file(), reason="functional set absent")
@pytest.mark.asyncio
async def test_integration_real_whisper_reaches_context_and_risk(clean_manager):
    """
    §29: at least one test must exercise the real Whisper worker end to end.

    Real audio -> AASIST/ECAPA on the critical path -> real faster-whisper in a
    worker -> real context classification -> authoritative recomputation.
    """
    if not transcriber.is_real_ml:
        pytest.skip(f"real STT unavailable: {transcriber.fallback_reason}")

    from app.ml.preprocessing.ingest import iter_pcm_chunks, load_audio_file
    items = [i for i in json.load(open(FUNCTIONAL))["items"]
             if (REPO / i["file"]).is_file()]
    item = max(items, key=lambda i: i["duration_s"])
    audio, _ = load_audio_file(REPO / item["file"])

    await gw._ensure_stt_queue()
    q = gw.stt_queue
    sid = "integration-real"
    stream_windower.reset(sid)
    st = _state(sid)
    q.reopen_session(sid)
    before = q.metrics.completed

    def submit(ws, a):
        q.submit(STTJob(sid, ws, a))

    for chunk in iter_pcm_chunks(audio, 100):
        analyze_window(st, chunk, pipeline_mode="live", stt_submit=submit)
        await asyncio.sleep(0)

    deadline = time.perf_counter() + 90
    while time.perf_counter() < deadline:
        if q.depth() == 0 and q.metrics.completed > before:
            break
        await asyncio.sleep(0.25)

    stream_windower.reset(sid)
    assert q.metrics.submitted > 0, "no real STT work was queued"
    assert q.metrics.completed > before, "the real Whisper worker never finished"
    assert st.last_context_seq >= 0, "no transcript was ever applied"


# ══ 30  MOCK REGRESSION ══════════════════════════════════════════════════════

def test_mock_mode_keeps_transcription_inline_and_unchanged(clean_manager):
    """Async STT must not leak into the deterministic mock pipeline (§17)."""
    from app.ml.context.transcriber import Transcriber
    scripted = Transcriber(pipeline_mode="mock")
    assert scripted.is_real_ml is False

    st = _state("mockmode")
    stream_windower.reset("mockmode")
    calls = []
    # Even with a sink supplied, a scripted transcriber must run synchronously.
    import app.websocket.pipeline as pl
    real = pl.transcriber
    pl.transcriber = scripted
    try:
        from app.ml.preprocessing.ingest import to_int16_pcm
        for _ in range(6):
            analyze_window(st, to_int16_pcm(_audio(1.0)), pipeline_mode="mock",
                           stt_submit=lambda ws, a: calls.append(ws))
    finally:
        pl.transcriber = real
        stream_windower.reset("mockmode")
    assert calls == [], "mock mode queued asynchronous STT work"
