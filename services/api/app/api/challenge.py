"""
Challenge endpoints.

A challenge is an in-band verification step: ask the caller something an
impersonator is unlikely to answer correctly. The outcome is fed back into the
Risk Engine as interactive evidence and pushed to the live dashboard, so the
Challenge screen and the Live Security Dashboard stay in sync without a refresh.
"""

import random
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Challenge, Session, User
from app.websocket import events as ev
from app.websocket.manager import manager
from app.websocket.pipeline import persist_snapshot, recompute_after_outcome

router = APIRouter()

# Randomised pool — a challenge that is always identical is trivially replayed.
CHALLENGE_POOL = [
    ("phrase", "Please say: 'The security of this call matters.'"),
    ("phrase", "Please say your full name clearly."),
    ("question", "What are the last 4 digits of your registered mobile number?"),
    ("question", "Which city did you register from?"),
    ("sequence", "Count from 1 to 5 slowly."),
    ("phrase", "Please say: 'I authorize this transaction.'"),
    ("phrase", "Repeat after me: 'VoiceShield verification active.'"),
    ("question", "What is today's date?"),
]

VALID_OUTCOMES = {"passed", "failed", "timeout"}


class ChallengeResponse(BaseModel):
    id: str
    session_id: str
    challenge_text: str
    challenge_type: str
    state: str
    created_at: datetime


class ChallengeResultRequest(BaseModel):
    outcome: str          # passed | failed | timeout
    detail: str = ""


@router.post("/{session_id}", response_model=ChallengeResponse)
async def issue_challenge(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_active_session(session_id, current_user.id, db)

    ctype, ctext = random.choice(CHALLENGE_POOL)
    challenge = Challenge(
        session_id=session.id,
        challenge_text=ctext,
        challenge_type=ctype,
        state="pending",
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    await manager.publish(session_id, ev.challenge_started(
        session_id=session_id,
        challenge_id=challenge.id,
        challenge_text=challenge.challenge_text,
        challenge_type=challenge.challenge_type,
    ))
    await manager.publish(session_id, ev.detected_event(
        session_id, "challenge_started", "Challenge issued to caller",
        "policy", "info",
    ))

    return _to_response(challenge)


@router.post("/{session_id}/{challenge_id}/result", response_model=ChallengeResponse)
async def submit_challenge_result(
    session_id: str,
    challenge_id: str,
    body: ChallengeResultRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.outcome not in VALID_OUTCOMES:
        raise HTTPException(status_code=422, detail="Invalid challenge outcome")

    await _owned_active_session(session_id, current_user.id, db)

    result = await db.execute(
        select(Challenge).where(
            Challenge.id == challenge_id,
            Challenge.session_id == session_id,
        )
    )
    challenge = result.scalar_one_or_none()
    if not challenge:
        raise HTTPException(status_code=404, detail="Challenge not found")
    if challenge.state != "pending":
        raise HTTPException(status_code=409, detail="Challenge already resolved")

    challenge.state = body.outcome
    challenge.response_at = datetime.now(timezone.utc)
    challenge.evidence = {"detail": body.detail}
    await db.commit()
    await db.refresh(challenge)

    # Feed the outcome back into the authoritative risk picture.
    state = manager.get_state(session_id)
    if state is not None:
        state.challenge_outcome = body.outcome

    await manager.publish(session_id, ev.challenge_result(
        session_id=session_id,
        challenge_id=challenge.id,
        outcome=body.outcome,
        detail=body.detail,
    ))
    await manager.publish(session_id, ev.detected_event(
        session_id,
        f"challenge_{body.outcome}",
        f"Challenge {body.outcome}",
        "policy",
        "critical" if body.outcome == "failed" else "info",
    ))

    # A challenge outcome is evidence, so re-fuse and re-decide immediately
    # rather than waiting for the next audio window (which may never come).
    if state is not None:
        events = recompute_after_outcome(state)
        await manager.publish_many(session_id, events)
        await persist_snapshot(session_id, events[0] if events else None)

    return _to_response(challenge)


async def _owned_active_session(session_id: str, user_id: str, db: AsyncSession) -> Session:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.state != "active":
        raise HTTPException(status_code=409, detail="Session is not active")
    return session


def _to_response(c: Challenge) -> ChallengeResponse:
    return ChallengeResponse(
        id=c.id,
        session_id=c.session_id,
        challenge_text=c.challenge_text,
        challenge_type=c.challenge_type,
        state=c.state,
        created_at=c.created_at,
    )
