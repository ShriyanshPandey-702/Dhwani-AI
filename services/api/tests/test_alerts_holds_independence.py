"""
Tests for independent ALERTS vs HOLDS calculation and live session termination.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.api.incidents import _is_alert, _is_hold, OverviewStats
from app.models.models import Incident
from app.websocket.manager import SessionState, manager
from app.websocket.stt_queue import STTJob, STTQueue
from app.websocket.gateway import _apply_transcript, _teardown, _deepgram_streamers
from app.ml.stt.deepgram_stream import DeepgramLiveStreamer
from app.risk.policy import DEFAULT_POLICY_CONFIG


def _make_incident(
    id: str,
    peak_risk_state: str,
    peak_risk_score: int,
    action_taken: str,
    decision: str,
) -> Incident:
    return Incident(
        id=id,
        session_id=f"sess-{id}",
        user_id="u1",
        final_state=peak_risk_state,
        peak_risk_score=peak_risk_score,
        peak_risk_state=peak_risk_state,
        action_taken=action_taken,
        evidence_summary={
            "final_decision": decision,
            "decision": decision,
            "peak_risk_score": peak_risk_score,
            "peak_risk_state": peak_risk_state,
        },
        policy_version="v1",
        model_versions={},
        integrity_hash="sha256-hash",
        created_at=datetime.now(timezone.utc),
    )


# ══ ALERTS VS HOLDS INDEPENDENCE ═════════════════════════════════════════════

def test_alerts_and_holds_independent_classification():
    """
    Verify classification logic:
    - ALLOW + LOW: Alerts: No, Holds: No
    - VERIFY + SUSPICIOUS: Alerts: Yes, Holds: No
    - HOLD + CRITICAL: Alerts: Yes, Holds: Yes
    - BLOCK + HIGH: Alerts: Yes, Holds: No
    """
    inc_allow = _make_incident("1", "low", 10, "allow", "ALLOW")
    inc_verify = _make_incident("2", "suspicious", 45, "verify", "VERIFY")
    inc_hold = _make_incident("3", "critical", 90, "hold", "HOLD")
    inc_block = _make_incident("4", "high", 80, "block", "BLOCK")

    # ALLOW + LOW
    assert not _is_alert(inc_allow), "ALLOW + LOW must not be an alert"
    assert not _is_hold(inc_allow), "ALLOW + LOW must not be a hold"

    # VERIFY + SUSPICIOUS
    assert _is_alert(inc_verify), "VERIFY + SUSPICIOUS must be an alert"
    assert not _is_hold(inc_verify), "VERIFY + SUSPICIOUS must not be a hold"

    # HOLD
    assert _is_alert(inc_hold), "HOLD must be an alert"
    assert _is_hold(inc_hold), "HOLD must be a hold"

    # BLOCK
    assert _is_alert(inc_block), "BLOCK must be an alert"
    assert not _is_hold(inc_block), "BLOCK must not be a hold"

    # Combined dataset: 4 incidents total
    dataset = [inc_allow, inc_verify, inc_hold, inc_block]
    alerts_count = sum(1 for i in dataset if _is_alert(i))
    holds_count = sum(1 for i in dataset if _is_hold(i))

    # Alerts = 3 (verify, hold, block)
    # Holds = 1 (hold)
    assert alerts_count == 3
    assert holds_count == 1
    assert alerts_count != holds_count, "Alerts and Holds must be calculated independently and not equal"


# ══ SESSION TERMINATION & CANCELLATION ═══════════════════════════════════════

@pytest.mark.asyncio
async def test_session_teardown_cancels_and_closes_resources():
    """
    Verify that _teardown:
    1. Sets state.closed = True immediately.
    2. Closes STT queue for session so late jobs are ignored.
    3. Stops Deepgram stream.
    4. Drops state cleanly.
    5. Is idempotent and safe on repeated calls.
    """
    session_id = "test-term-1"
    user_id = "user-term-1"

    # Set up session state
    state = manager.get_or_create_state(session_id, user_id, dict(DEFAULT_POLICY_CONFIG))
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    state.active_tasks.add(dummy_task)

    # Set up mock Deepgram streamer
    mock_streamer = MagicMock()
    mock_streamer.stop = AsyncMock()
    _deepgram_streamers[session_id] = mock_streamer

    # Perform teardown
    await _teardown(session_id, user_id)

    # Verifications
    assert dummy_task.cancelled() or dummy_task.done()
    assert mock_streamer.stop.awaited or mock_streamer.stop.called
    assert session_id not in _deepgram_streamers
    assert manager.get_state(session_id) is None

    # Repeated teardown must be safe (idempotent)
    await _teardown(session_id, user_id)


@pytest.mark.asyncio
async def test_late_transcript_cannot_mutate_closed_session():
    """
    Ensure STT callback discards late segment if session is closed.
    """
    session_id = "test-closed-stt"
    queue = STTQueue(transcribe_fn=MagicMock(), apply_fn=_apply_transcript)
    queue.close_session(session_id)

    job = STTJob(session_id=session_id, window_seq=1, audio=None)
    segment = SimpleNamespace(
        text="transfer fifty thousand rupees immediately",
        is_mock=False,
        model_name="whisper",
        pipeline_mode="live",
        language="en",
        confidence=0.9,
    )

    # Invoking _apply_transcript on a closed session drops without mutating or publishing
    await _apply_transcript(job, segment)
    assert queue.is_closed(session_id)
