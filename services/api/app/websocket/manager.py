"""
Connection registry and per-session live state.

Other modules (the challenge and verification REST routes) publish events into
an active dashboard through `manager.publish(...)`, so a REST action taken on
one screen is reflected on the live dashboard without a refresh.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import structlog
from fastapi import WebSocket

from app.risk.engine import EvidenceBundle
from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.websocket import events as ev

log = structlog.get_logger()

# Bounded history kept server-side; the client keeps its own bounded copy.
MAX_HISTORY = 120


@dataclass
class SessionState:
    session_id: str
    user_id: str
    policy_config: dict = field(default_factory=lambda: dict(DEFAULT_POLICY_CONFIG))
    pipeline_mode: str = "mock"          # "mock" | "live"

    risk_history: List[int] = field(default_factory=list)
    peak_risk_score: int = 0
    peak_risk_state: str = "insufficient_evidence"

    last_authenticity: Optional[dict] = None
    last_identity: Optional[dict] = None
    last_context: Optional[dict] = None
    last_decision: str = "ALLOW"
    last_action: str = "allow"

    consequence: str = "low"
    challenge_outcome: Optional[str] = None
    verification_outcome: Optional[str] = None

    # Codes already announced on the timeline, so the same finding is not
    # repeated on every analysis window.
    announced: Set[str] = field(default_factory=set)

    demo_task: Optional[asyncio.Task] = None

    # Ingest-side ordering guard (§5). Clients may number their audio chunks;
    # when they do, a repeated or older number is dropped rather than fed to
    # the models a second time. Absent numbering, every chunk is accepted.
    last_audio_seq: int = -1
    duplicate_audio_chunks: int = 0
    stale_audio_chunks: int = 0
    rejected_audio_chunks: int = 0

    # Last per-stage timings, for the latency benchmark and /metrics-style reads.
    last_stage_ms: dict = field(default_factory=dict)

    # Async STT bookkeeping (Phase 1.5). `window_seq` numbers analysis windows
    # so a transcript can be matched back to the audio it came from;
    # `last_context_seq` is the newest window whose transcript has been applied,
    # which is what makes a late-arriving result detectably stale.
    window_seq: int = 0
    last_context_seq: int = -1
    stale_stt_results: int = 0
    duplicate_stt_results: int = 0
    context_pending: bool = False

    # Phase 1.6: per-session serialisation lock for the ML inference thread pool.
    # analyze_window mutates this state and per-session dicts inside the ML
    # singletons (StreamWindower, SpeakerIdentity, ContextClassifier).  Moving
    # inference into a ThreadPoolExecutor removes the implicit single-threaded
    # serialisation the event loop previously provided, so we restore it here
    # explicitly.  The lock is acquired in gateway._process; different sessions
    # proceed concurrently while the same session is processed sequentially.
    processing_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # Phase 1.6 Bounded Ingress Backpressure:
    # Track pending tasks per session to strictly bound coroutine accumulation.
    pending_audio_tasks: int = 0
    dropped_audio_chunks: int = 0
    closed: bool = False
    active_tasks: Set[asyncio.Task] = field(default_factory=set)

    # Phase 1 Step 5.4 Gated Corroboration Persistence (P=2 consecutive ML analysis windows)
    consecutive_identity_mismatches: int = 0
    consecutive_authenticity_anomalies: int = 0
    temporal_risk_score: Optional[float] = None
    transcript_segments: List[str] = field(default_factory=list)

    def record_risk(self, score: int, state: str, alpha: float = 0.40) -> int:
        if self.pipeline_mode == "mock":
            self.risk_history.append(score)
            del self.risk_history[:-MAX_HISTORY]
            if score > self.peak_risk_score:
                self.peak_risk_score = score
                self.peak_risk_state = state
            return score

        if self.temporal_risk_score is None:
            self.temporal_risk_score = float(score)
        else:
            self.temporal_risk_score = alpha * score + (1.0 - alpha) * self.temporal_risk_score

        smooth_score = int(round(self.temporal_risk_score))
        self.risk_history.append(smooth_score)
        del self.risk_history[:-MAX_HISTORY]
        if smooth_score > self.peak_risk_score:
            self.peak_risk_score = smooth_score
            self.peak_risk_state = state
        return smooth_score

    def append_transcript(self, text: str) -> str:
        text = text.strip()
        if not text:
            return " ".join(self.transcript_segments)
        if self.transcript_segments:
            last = self.transcript_segments[-1]
            if text.lower() == last.lower():
                return " ".join(self.transcript_segments)
            words_last = last.split()
            words_new = text.split()
            overlap = 0
            for i in range(1, min(len(words_last), len(words_new)) + 1):
                if [w.lower() for w in words_last[-i:]] == [w.lower() for w in words_new[:i]]:
                    overlap = i
            if overlap > 0:
                text = " ".join(words_new[overlap:])
        if text:
            self.transcript_segments.append(text)
        return " ".join(self.transcript_segments)

    def get_accumulated_transcript(self) -> str:
        return " ".join(self.transcript_segments)

    def evidence(self) -> EvidenceBundle:
        """Build the fusion input from the latest per-stream observations."""
        auth = self.last_authenticity
        ident = self.last_identity
        ctx = self.last_context

        P = self.policy_config.get("corroboration_persistence", 2)
        is_confirmed = (self.consecutive_identity_mismatches >= P)
        is_pending = (self.consecutive_identity_mismatches == 1)

        is_auth_confirmed = (self.consecutive_authenticity_anomalies >= P)
        is_auth_pending = (self.consecutive_authenticity_anomalies == 1)

        return EvidenceBundle(
            authenticity=(auth or {}).get("spoof_probability"),
            authenticity_confidence=(auth or {}).get("confidence", 0.0),
            identity_similarity=(
                (ident or {}).get("match_score", 0) / 100.0
                if ident and ident.get("enrollment_status") != "NOT_ENROLLED"
                else None
            ),
            identity_confidence=(ident or {}).get("confidence", 0.0),
            context_risk=((ctx or {}).get("score") / 100.0) if ctx else None,
            context_confidence=(ctx or {}).get("confidence", 0.0),
            consequence=self.consequence,
            challenge_outcome=self.challenge_outcome,
            verification_outcome=self.verification_outcome,
            identity_corroborated=is_confirmed,
            identity_corroboration_pending=is_pending,
            authenticity_corroborated=is_auth_confirmed,
            authenticity_corroboration_pending=is_auth_pending,
            authenticity_streak=self.consecutive_authenticity_anomalies,
        )


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._states: Dict[str, SessionState] = {}

    # ── Connections ──────────────────────────────────────────────────────────

    def add(self, session_id: str, ws: WebSocket) -> None:
        self._connections.setdefault(session_id, set()).add(ws)

    def remove(self, session_id: str, ws: WebSocket) -> None:
        conns = self._connections.get(session_id)
        if conns:
            conns.discard(ws)
            if not conns:
                self._connections.pop(session_id, None)

    def connection_count(self, session_id: str) -> int:
        return len(self._connections.get(session_id, ()))

    # ── State ────────────────────────────────────────────────────────────────

    def get_or_create_state(self, session_id: str, user_id: str,
                            policy_config: dict) -> SessionState:
        state = self._states.get(session_id)
        if state is None:
            state = SessionState(
                session_id=session_id,
                user_id=user_id,
                policy_config=policy_config,
            )
            self._states[session_id] = state
        return state

    def get_state(self, session_id: str) -> Optional[SessionState]:
        return self._states.get(session_id)

    def drop_state(self, session_id: str) -> None:
        state = self._states.pop(session_id, None)
        if state:
            state.closed = True
            if state.demo_task and not state.demo_task.done():
                state.demo_task.cancel()
            for task in list(state.active_tasks):
                if not task.done():
                    task.cancel()
            state.active_tasks.clear()
        ev.reset_seq(session_id)

    # ── Publishing ───────────────────────────────────────────────────────────

    async def publish(self, session_id: str, message: dict) -> int:
        """
        Send an event to every live connection for a session.

        Returns the number of connections it reached. A dead socket is dropped
        rather than failing the broadcast for everyone else.
        """
        conns = list(self._connections.get(session_id, ()))
        delivered = 0
        dead: List[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.remove(session_id, ws)
        return delivered

    async def publish_many(self, session_id: str, messages: List[dict]) -> None:
        for message in messages:
            await self.publish(session_id, message)


manager = ConnectionManager()
