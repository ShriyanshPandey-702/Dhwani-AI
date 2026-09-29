"""
WebSocket event contract.

Every server → client message is built here so the wire format has exactly one
definition. Each event carries:

  type        one of EVENT_TYPES
  event_id    unique — lets the client drop duplicates after a reconnect
  seq         monotonic per session — lets the client drop out-of-order/stale
              events without dropping legitimate late-arriving ones
  session_id  the session the event belongs to
  timestamp   ISO-8601 UTC

Adding a field is backwards compatible; the mobile client ignores unknown
fields and unknown event types.
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

# ── Event type registry ───────────────────────────────────────────────────────
SESSION_STARTED = "session_started"
AUDIO_QUALITY = "audio_quality"
RISK_UPDATE = "risk_update"
DETECTED_EVENT = "detected_event"
ALERT = "alert"
CHALLENGE_STARTED = "challenge_started"
CHALLENGE_RESULT = "challenge_result"
VERIFICATION_REQUESTED = "verification_requested"
VERIFICATION_RESULT = "verification_result"
POLICY_DECISION = "policy_decision"
SESSION_ENDED = "session_ended"
ERROR = "error"
PONG = "pong"

EVENT_TYPES = {
    SESSION_STARTED, AUDIO_QUALITY, RISK_UPDATE, DETECTED_EVENT, ALERT,
    CHALLENGE_STARTED, CHALLENGE_RESULT, VERIFICATION_REQUESTED,
    VERIFICATION_RESULT, POLICY_DECISION, SESSION_ENDED, ERROR, PONG,
}

# ── Sequence numbering ────────────────────────────────────────────────────────
_seq_counters: Dict[str, itertools.count] = {}
_seq_lock = Lock()


def next_seq(session_id: str) -> int:
    with _seq_lock:
        counter = _seq_counters.get(session_id)
        if counter is None:
            counter = itertools.count(1)
            _seq_counters[session_id] = counter
        return next(counter)


def reset_seq(session_id: str) -> None:
    with _seq_lock:
        _seq_counters.pop(session_id, None)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _envelope(event_type: str, session_id: str, **payload: Any) -> Dict[str, Any]:
    return {
        "type": event_type,
        "event_id": str(uuid.uuid4()),
        "seq": next_seq(session_id),
        "session_id": session_id,
        "timestamp": _now_iso(),
        **payload,
    }


# ── Builders ──────────────────────────────────────────────────────────────────

def session_started(session_id: str, pipeline_mode: str, model_versions: dict) -> dict:
    """`pipeline_mode` is "mock" or "live" — the UI labels the dashboard with it."""
    return _envelope(
        SESSION_STARTED,
        session_id,
        pipeline_mode=pipeline_mode,
        model_versions=model_versions,
    )


def audio_quality(session_id: str, quality: dict, active: bool) -> dict:
    return _envelope(AUDIO_QUALITY, session_id, active=active, audio=quality)


def risk_update(
    session_id: str,
    risk_score: int,
    risk_state: str,
    risk_trend: str,
    evidence_confidence: float,
    authenticity: Optional[dict],
    identity: Optional[dict],
    context: Optional[dict],
    decision: str,
    reasons: List[str],
    consequence: str,
    contributions: dict,
    pipeline_mode: str,
    evidence: Optional[dict] = None,
    pre_transaction_warning: bool = False,
    recommended_actions: Optional[List[str]] = None,
    call_source: str = "DEVICE_MICROPHONE",
) -> dict:
    """The primary dashboard event. Evidence streams stay in separate objects."""
    return _envelope(
        RISK_UPDATE,
        session_id,
        risk_score=risk_score,
        risk_state=risk_state,
        risk_trend=risk_trend,
        evidence_confidence=evidence_confidence,
        authenticity=authenticity,
        identity=identity,
        context=context,
        decision=decision,
        reasons=reasons,
        consequence=consequence,
        contributions=contributions,
        pipeline_mode=pipeline_mode,
        evidence=evidence,
        pre_transaction_warning=pre_transaction_warning,
        recommended_actions=recommended_actions or [],
        call_source=call_source,
    )


def detected_event(
    session_id: str,
    code: str,
    label: str,
    stream: str,
    severity: str = "info",
) -> dict:
    """
    One entry on the live event timeline.
    `stream` is authenticity | identity | context | risk | policy | session.
    """
    return _envelope(
        DETECTED_EVENT,
        session_id,
        code=code,
        label=label,
        stream=stream,
        severity=severity,
    )


def alert(session_id: str, severity: str, message: str, recommended_action: str) -> dict:
    return _envelope(
        ALERT,
        session_id,
        severity=severity,
        message=message,
        recommended_action=recommended_action,
    )


def challenge_started(session_id: str, challenge_id: str, challenge_text: str,
                      challenge_type: str) -> dict:
    return _envelope(
        CHALLENGE_STARTED,
        session_id,
        challenge_id=challenge_id,
        challenge_text=challenge_text,
        challenge_type=challenge_type,
    )


def challenge_result(session_id: str, challenge_id: str, outcome: str,
                     detail: str = "") -> dict:
    """`outcome` is "passed" | "failed" | "timeout"."""
    return _envelope(
        CHALLENGE_RESULT,
        session_id,
        challenge_id=challenge_id,
        outcome=outcome,
        detail=detail,
    )


def verification_requested(session_id: str, verification_id: str, method: str,
                           expires_at: str) -> dict:
    return _envelope(
        VERIFICATION_REQUESTED,
        session_id,
        verification_id=verification_id,
        method=method,
        expires_at=expires_at,
    )


def verification_result(session_id: str, verification_id: str, outcome: str,
                        method: str = "trusted_device") -> dict:
    """`outcome` is "approved" | "rejected" | "timeout"."""
    return _envelope(
        VERIFICATION_RESULT,
        session_id,
        verification_id=verification_id,
        outcome=outcome,
        method=method,
    )


def policy_decision(session_id: str, decision: str, action: str,
                    reasons: List[str], recommended_action: str,
                    risk_state: str, risk_score: int) -> dict:
    return _envelope(
        POLICY_DECISION,
        session_id,
        decision=decision,
        action=action,
        reasons=reasons,
        recommended_action=recommended_action,
        risk_state=risk_state,
        risk_score=risk_score,
    )


def session_ended(session_id: str, reason: str, peak_risk_score: int,
                  peak_risk_state: str, incident_id: Optional[str] = None) -> dict:
    return _envelope(
        SESSION_ENDED,
        session_id,
        reason=reason,
        peak_risk_score=peak_risk_score,
        peak_risk_state=peak_risk_state,
        incident_id=incident_id,
    )


def error(session_id: str, detail: str, code: str = "internal_error") -> dict:
    return _envelope(ERROR, session_id, detail=detail, code=code)
