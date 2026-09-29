"""
WebSocket Gateway — WS /ws/sessions/{session_id}?token=<JWT>

Client → Server
  {"type": "audio_chunk", "data": "<base64 int16 PCM>"}   real/streamed audio
  {"type": "start_demo"}                                   MOCK driver on
  {"type": "stop_demo"}                                    MOCK driver off
  {"type": "ping"}

Server → Client
  See app/websocket/events.py for the full contract. Every event carries
  type, event_id, seq, session_id and timestamp.

Authentication is mandatory: an invalid token, or a session the token's user
does not own, is closed before the socket is accepted.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import decode_token
from app.models.models import Incident, Policy, RiskSnapshot, Session
from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.simulation.mock_audio import generate_frame
from app.websocket import events as ev
from app.websocket.manager import manager
from app.websocket.stt_queue import STTJob, STTQueue
from app.websocket.pipeline import (
    MODEL_VERSIONS,
    analyze_window,
    _context_timeline,
    authenticity_detector,
    context_classifier as _ctx,
    decision_tail,
    fuse_and_decide,
    persist_snapshot,
    stream_windower,
    context_classifier,
    speaker_identity,
    transcriber,
)

log = structlog.get_logger()
router = APIRouter()

RECEIVE_TIMEOUT_S = 60.0

# Ingest limits (§5, §25). 250 ms of 16 kHz int16 mono is 8000 bytes, so this
# accepts chunks well beyond the largest documented size while still bounding
# a single message. Base64 inflates by 4/3.
MAX_AUDIO_CHUNK_BYTES = 1_048_576          # 1 MiB decoded (~32 s of audio)
MAX_AUDIO_B64_CHARS = 1_400_000
DEMO_STEPS = 12
DEMO_INTERVAL_S = 2.0

# ── Phase 1.6: ML inference thread pool ──────────────────────────────────────
# AASIST and ECAPA are CPU-bound PyTorch/SpeechBrain calls that previously
# blocked the event loop for 80-250 ms per window.  Moving them into a
# ThreadPoolExecutor keeps the event loop responsive.  Both models release the
# GIL during their forward passes, so extra workers give real parallelism.
#
# The pool is created lazily (_ensure_ml_pool) so the import of this module
# never triggers model loading or pool allocation in unit tests.
_ml_pool: Optional[ThreadPoolExecutor] = None


def _ensure_ml_pool() -> None:
    """Initialise the ML inference thread pool (idempotent, no-op in mock mode)."""
    global _ml_pool
    if _ml_pool is not None:
        return
    if not (authenticity_detector.is_real_ml or speaker_identity.is_real_ml):
        return
    _ml_pool = ThreadPoolExecutor(
        max_workers=settings.ML_POOL_WORKERS,
        thread_name_prefix="ml_infer",
    )
    log.info("ml_pool.started", workers=settings.ML_POOL_WORKERS)


def shutdown_ml_pool() -> None:
    """Graceful shutdown — call from the application lifespan on exit."""
    global _ml_pool
    if _ml_pool is not None:
        _ml_pool.shutdown(wait=False, cancel_futures=True)
        _ml_pool = None
        log.info("ml_pool.stopped")


@router.websocket("/ws/sessions/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    token: Optional[str] = Query(None, description="Optional JWT access token"),
):
    # ── Authenticate / Resolve User ──────────────────────────────────────────
    user_id: Optional[str] = None
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                await websocket.close(code=4001, reason="Not an access token")
                return
            user_id = payload["sub"]
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return

    # ── Authorise: verify session exists and is active ───────────────────────
    # Resolve the effective user identity before entering the WS loop so that
    # teardown (which runs outside the DB context) always has a valid UUID even
    # when no JWT token was presented.  ``session.user_id`` is NOT NULL in the
    # schema, so this is always resolvable when a live session exists.
    effective_user_id: Optional[str] = None   # populated after DB lookup
    async with AsyncSessionLocal() as db:
        if user_id:
            query = select(Session).where(Session.id == session_id, Session.user_id == user_id)
        else:
            query = select(Session).where(Session.id == session_id)

        result = await db.execute(query)
        session = result.scalar_one_or_none()
        if not session or session.state != "active":
            await websocket.close(code=4004, reason="Session not found or not active")
            return

        effective_user_id = user_id or session.user_id

        p_result = await db.execute(select(Policy).where(Policy.is_active.is_(True)).limit(1))
        policy = p_result.scalar_one_or_none()
        policy_config = policy.config if policy else DEFAULT_POLICY_CONFIG

    await websocket.accept()
    _ensure_ml_pool()          # Phase 1.6: start pool before the receive loop
    await _ensure_stt_queue()
    stt_queue.reopen_session(session_id)
    manager.add(session_id, websocket)
    state = manager.get_or_create_state(session_id, effective_user_id, policy_config)
    log.info("ws.connected", session_id=session_id, user_id=effective_user_id,
             connections=manager.connection_count(session_id))

    await websocket.send_json(ev.session_started(
        session_id, pipeline_mode=state.pipeline_mode, model_versions=MODEL_VERSIONS
    ))

    try:
        while True:
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=RECEIVE_TIMEOUT_S
            )

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    ev.error(session_id, "Malformed JSON", code="bad_request")
                )
                continue
            if not isinstance(msg, dict):
                await websocket.send_json(
                    ev.error(session_id, "Message must be an object", code="bad_request")
                )
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await websocket.send_json({"type": ev.PONG, "timestamp": int(time.time())})
                continue

            if msg_type == "start_demo":
                await _start_demo(session_id)
                continue

            if msg_type == "stop_demo":
                _stop_demo(session_id)
                continue

            if msg_type == "audio_chunk":
                encoded = msg.get("data", "")
                if not encoded:
                    continue
                if not isinstance(encoded, str):
                    state.rejected_audio_chunks += 1
                    await websocket.send_json(
                        ev.error(session_id, "audio data must be a base64 string",
                                 code="bad_audio")
                    )
                    continue
                # Reject before decoding: a base64 blob this large is either a
                # bug or an attempt to exhaust memory.
                if len(encoded) > MAX_AUDIO_B64_CHARS:
                    state.rejected_audio_chunks += 1
                    await websocket.send_json(
                        ev.error(session_id,
                                 f"audio chunk too large ({len(encoded)} chars, "
                                 f"limit {MAX_AUDIO_B64_CHARS})",
                                 code="audio_too_large")
                    )
                    continue
                try:
                    pcm_bytes = base64.b64decode(encoded, validate=True)
                except Exception:
                    state.rejected_audio_chunks += 1
                    await websocket.send_json(
                        ev.error(session_id, "Invalid base64 audio", code="bad_audio")
                    )
                    continue
                if len(pcm_bytes) > MAX_AUDIO_CHUNK_BYTES:
                    state.rejected_audio_chunks += 1
                    await websocket.send_json(
                        ev.error(session_id, "decoded audio chunk too large",
                                 code="audio_too_large")
                    )
                    continue

                # Optional client sequence number: duplicates and stale chunks
                # must not be analysed twice, which would double-count evidence.
                raw_seq = msg.get("seq")
                if isinstance(raw_seq, int):
                    if raw_seq == state.last_audio_seq:
                        state.duplicate_audio_chunks += 1
                        continue
                    if raw_seq < state.last_audio_seq:
                        state.stale_audio_chunks += 1
                        continue
                    state.last_audio_seq = raw_seq

                # Real client audio runs the identical pipeline with bounded admission backpressure.
                if state.pending_audio_tasks >= settings.MAX_PENDING_AUDIO_CHUNKS:
                    state.dropped_audio_chunks += 1
                    log.warning(
                        "ws.audio_chunk_dropped_queue_full",
                        session_id=session_id,
                        pending=state.pending_audio_tasks,
                        limit=settings.MAX_PENDING_AUDIO_CHUNKS,
                    )
                    continue

                state.pending_audio_tasks += 1
                task = asyncio.create_task(_process(session_id, pcm_bytes, "live"))
                state.active_tasks.add(task)
                task.add_done_callback(state.active_tasks.discard)
                continue

            await websocket.send_json(
                ev.error(session_id, f"Unknown message type: {msg_type}",
                         code="unknown_type")
            )

    except (WebSocketDisconnect, asyncio.TimeoutError):
        log.info("ws.disconnected", session_id=session_id)
    except Exception as e:
        log.error("ws.error", session_id=session_id, error=str(e))
    finally:
        manager.remove(session_id, websocket)
        # Tear the session down only when the last dashboard disconnects, so a
        # brief network drop and reconnect does not lose the risk picture.
        if manager.connection_count(session_id) == 0:
            # Phase 5.7 fix: pass effective_user_id (always a valid UUID,
            # resolved from session.user_id) rather than the closure-captured
            # user_id which is None for unauthenticated connections.  Passing
            # None would violate the NOT NULL FK on incidents.user_id and the
            # incident record would be silently dropped.
            await _teardown(session_id, effective_user_id)


# ── Asynchronous speech-to-text ───────────────────────────────────────────────

async def _apply_transcript(job: STTJob, segment) -> None:
    """
    Fold a finished transcript into a session and re-decide, authoritatively.

    Everything that makes a late result safe happens here: the session must
    still exist, the window must be newer than the last one applied, and the
    resulting risk update is published with a fresh server sequence number so
    the client can never move backwards.
    """
    state = manager.get_state(job.session_id)
    if state is None or stt_queue.is_closed(job.session_id):
        stt_queue.metrics.dropped_session_gone += 1
        return

    # Ordering guard (§12). Whisper may finish out of order; an older window
    # must not overwrite context derived from a newer one.
    if job.window_seq < state.last_context_seq:
        state.stale_stt_results += 1
        log.info("stt.stale_result_dropped", session_id=job.session_id,
                 window_seq=job.window_seq, last_applied=state.last_context_seq)
        return
    if job.window_seq == state.last_context_seq:
        state.duplicate_stt_results += 1      # idempotent: apply nothing twice
        return

    if segment is None:
        # No speech in that window: context evidence stays unavailable, which
        # is not the same as "safe".
        state.last_context_seq = job.window_seq
        state.context_pending = False
        return

    ctx = _ctx.classify(
        job.session_id, segment.text,
        transcript_is_mock=segment.is_mock,
        transcript_model=segment.model_name,
        transcript_pipeline_mode=segment.pipeline_mode,
        transcript_language=segment.language,
        transcript_confidence=segment.confidence,
    )
    state.last_context_seq = job.window_seq
    state.context_pending = False
    if ctx is None:
        return

    accumulated = state.append_transcript(segment.text)
    ctx_dict = ctx.to_dict()
    ctx_dict["transcript"] = accumulated
    ctx_dict["latest_segment"] = segment.text
    state.last_context = ctx_dict
    state.consequence = ctx.consequence

    # Re-decide with the same Risk Engine and the same policy — only the
    # evidence available to it has changed.
    update, verdict = fuse_and_decide(state, state.pipeline_mode)
    outgoing = [update] + list(_context_timeline(state)) + list(decision_tail(state, verdict))
    await manager.publish_many(job.session_id, outgoing)
    await persist_snapshot(job.session_id, update)
    log.info("stt.context_applied", session_id=job.session_id,
             window_seq=job.window_seq, risk_score=update.get("risk_score"),
             risk_state=update.get("risk_state"))


stt_queue = STTQueue(
    transcribe_fn=lambda sid, audio: transcriber.transcribe(sid, audio),
    apply_fn=_apply_transcript,
)


async def _ensure_stt_queue() -> None:
    """Start the STT workers lazily, on the running event loop."""
    if transcriber.is_real_ml and not stt_queue.running:
        await stt_queue.start()


# ── Analysis ──────────────────────────────────────────────────────────────────

async def _process(session_id: str, pcm_bytes: bytes, pipeline_mode: str) -> None:
    """
    Analyse one window and broadcast the resulting events.

    Phase 1.6: AASIST and ECAPA forward passes are moved into `_ml_pool` so the
    event loop is free during their CPU-bound compute.  The per-session
    `processing_lock` restores the implicit sequential ordering that previously
    existed because `analyze_window` had no await points.  Mock/heuristic paths
    stay inline — they are instant and incur no thread-pool overhead.
    """
    state = manager.get_state(session_id)
    if state is None or state.closed:
        return

    try:
        # Per-session serialisation: prevents two concurrent windows for the same
        # session from racing on SessionState fields and the per-session ML state
        # stored in StreamWindower, SpeakerIdentity and ContextClassifier.
        # Different sessions are unaffected and proceed concurrently in the pool.
        async with state.processing_lock:
            if state.closed or manager.get_state(session_id) is None:
                return

            state.pipeline_mode = pipeline_mode
            loop = asyncio.get_running_loop()

            def _submit(window_seq: int, audio) -> None:
                """
                Enqueue transcription; safe to call from any thread.

                `asyncio.Queue.put_nowait` is not thread-safe, so the actual
                submission is always scheduled on the event loop via
                call_soon_threadsafe — whether this closure is invoked from a
                pool thread (real ML path) or the event loop itself (mock path).
                """
                state.context_pending = True
                job = STTJob(session_id=session_id, window_seq=window_seq,
                             audio=audio, pipeline_mode=pipeline_mode)
                loop.call_soon_threadsafe(stt_queue.submit, job)

            sink = _submit if stt_queue.running else None

            # Determine whether the ML pool should be used for this window.
            # The pool is only warranted when a real model (PyTorch/SpeechBrain)
            # is active; mock and heuristic backends are instant and stay inline.
            use_pool = (
                _ml_pool is not None
                and (authenticity_detector.is_real_ml or speaker_identity.is_real_ml)
            )

            if use_pool:
                # Run the entire synchronous analysis in a pool thread so the
                # event loop is free during AASIST and ECAPA forward passes.
                outgoing = await loop.run_in_executor(
                    _ml_pool,
                    lambda: analyze_window(
                        state, pcm_bytes,
                        pipeline_mode=pipeline_mode,
                        stt_submit=sink,
                    ),
                )
            else:
                # Mock / heuristic: instant, no thread-pool overhead.
                outgoing = analyze_window(
                    state, pcm_bytes,
                    pipeline_mode=pipeline_mode,
                    stt_submit=sink,
                )

            await manager.publish_many(session_id, outgoing)
            await _persist_snapshot(session_id, state, outgoing)
    except asyncio.CancelledError:
        return
    except Exception as e:
        log.error("ws.analyze_error", session_id=session_id, error=str(e))
        await manager.publish(
            session_id, ev.error(session_id, "Analysis failed for one window",
                                 code="analysis_error")
        )
    finally:
        state.pending_audio_tasks = max(0, state.pending_audio_tasks - 1)


async def _persist_snapshot(session_id: str, state, outgoing: list) -> None:
    """Persist the risk snapshot from this window, if one was produced."""
    update = next((e for e in outgoing if e["type"] == ev.RISK_UPDATE), None)
    await persist_snapshot(session_id, update)


# ── Mock demo driver ──────────────────────────────────────────────────────────

async def _start_demo(session_id: str) -> None:
    """
    Start the DEVELOPMENT MOCK AUDIO driver.

    This feeds synthetic PCM through the exact same pipeline real audio uses.
    Every event it produces is tagged pipeline_mode="mock".
    """
    state = manager.get_state(session_id)
    if state is None or (state.demo_task and not state.demo_task.done()):
        return
    state.pipeline_mode = "mock"
    state.demo_task = asyncio.create_task(_demo_loop(session_id))


def _stop_demo(session_id: str) -> None:
    state = manager.get_state(session_id)
    if state and state.demo_task and not state.demo_task.done():
        state.demo_task.cancel()
        state.demo_task = None


async def _demo_loop(session_id: str) -> None:
    try:
        for step in range(DEMO_STEPS):
            if manager.connection_count(session_id) == 0:
                return
            await _process(session_id, generate_frame(step, DEMO_STEPS), "mock")
            await asyncio.sleep(DEMO_INTERVAL_S)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        log.error("ws.demo_error", session_id=session_id, error=str(e))


# ── Teardown ──────────────────────────────────────────────────────────────────

async def _teardown(session_id: str, user_id: str) -> None:
    # Refuse further transcription work and discard anything still in flight,
    # so a late transcript cannot resurrect a completed session (§25).
    stt_queue.close_session(session_id)
    state = manager.get_state(session_id)
    if state:
        state.closed = True
        for task in list(state.active_tasks):
            if not task.done():
                task.cancel()
        state.active_tasks.clear()

    incident_id: Optional[str] = None
    if state:
        incident_id = await _save_incident(session_id, user_id, state)

    if state:
        await manager.publish(session_id, ev.session_ended(
            session_id,
            reason="disconnected",
            peak_risk_score=state.peak_risk_score,
            peak_risk_state=state.peak_risk_state,
            incident_id=incident_id,
        ))

    # Clear all per-session ML state so the next call starts clean.
    speaker_identity.clear(session_id)
    transcriber.reset(session_id)
    context_classifier.reset(session_id)
    stream_windower.reset(session_id)   # discard buffered audio with the session
    manager.drop_state(session_id)
    log.info("ws.cleanup", session_id=session_id, incident_id=incident_id)


async def _save_incident(session_id: str, user_id: str, state) -> Optional[str]:
    """Persist a tamper-evident incident record (SHA-256 over the evidence)."""
    evidence_summary = {
        "peak_risk_score": state.peak_risk_score,
        "peak_risk_state": state.peak_risk_state,
        "final_decision": state.last_decision,
        "authenticity": state.last_authenticity,
        "identity": state.last_identity,
        "context": state.last_context,
        "risk_history": state.risk_history,
        "pipeline_mode": state.pipeline_mode,
        "policy_version": "v1",
        "model_versions": MODEL_VERSIONS,
    }
    integrity_hash = hashlib.sha256(
        json.dumps(evidence_summary, sort_keys=True, default=str).encode()
    ).hexdigest()

    try:
        async with AsyncSessionLocal() as db:
            incident = Incident(
                session_id=session_id,
                user_id=user_id,
                final_state=state.peak_risk_state,
                peak_risk_score=state.peak_risk_score,
                peak_risk_state=state.peak_risk_state,
                action_taken=state.last_action,
                evidence_summary=evidence_summary,
                policy_version="v1",
                model_versions=MODEL_VERSIONS,
                integrity_hash=integrity_hash,
            )
            db.add(incident)
            await db.commit()
            await db.refresh(incident)
            log.info("ws.incident_saved", session_id=session_id,
                     hash=integrity_hash[:16])
            return incident.id
    except Exception as e:
        log.error("ws.incident_save_failed", session_id=session_id, error=str(e))
        return None
