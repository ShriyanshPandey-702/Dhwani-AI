"""
Independent verification (out-of-band trust channel) endpoints.

Core principle: the voice channel must not be the only source of trust for a
consequential decision. A verification is raised on, and resolved through, a
channel independent of the call — a trusted device, an app confirmation, MFA
or a callback.

Resolutions are pushed to the live dashboard and fed back into the Risk Engine.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Session, User, Verification
from app.websocket import events as ev
from app.websocket.manager import manager
from app.websocket.pipeline import persist_snapshot, recompute_after_outcome

router = APIRouter()

OOB_TTL_SECONDS = 120  # A verification request expires after 2 minutes.

VALID_METHODS = {"trusted_device", "mfa", "callback", "app_confirmation"}


class VerificationResponse(BaseModel):
    id: str
    session_id: str
    method: str
    state: str
    expires_at: datetime
    nonce: str


class RequestVerification(BaseModel):
    method: str = "trusted_device"


class ResolveRequest(BaseModel):
    nonce: str


@router.post("/{session_id}/request", response_model=VerificationResponse)
async def request_verification(
    session_id: str,
    body: RequestVerification = RequestVerification(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.method not in VALID_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported verification method")

    await _owned_session(session_id, current_user.id, db)

    verification = Verification(
        session_id=session_id,
        method=body.method,
        state="requested",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=OOB_TTL_SECONDS),
    )
    db.add(verification)
    await db.commit()
    await db.refresh(verification)

    await manager.publish(session_id, ev.verification_requested(
        session_id=session_id,
        verification_id=verification.id,
        method=verification.method,
        expires_at=verification.expires_at.isoformat(),
    ))
    await manager.publish(session_id, ev.detected_event(
        session_id, "verification_requested",
        "Independent verification requested", "policy", "warning",
    ))

    return _to_response(verification)


@router.post("/{session_id}/approve", response_model=VerificationResponse)
async def approve_verification(
    session_id: str,
    body: ResolveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _resolve(session_id, body.nonce, "approved", current_user.id, db)


@router.post("/{session_id}/reject", response_model=VerificationResponse)
async def reject_verification(
    session_id: str,
    body: ResolveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _resolve(session_id, body.nonce, "rejected", current_user.id, db)


async def _resolve(
    session_id: str, nonce: str, new_state: str, user_id: str, db: AsyncSession
) -> VerificationResponse:
    # Ownership is checked before the nonce lookup so another user's session
    # cannot be probed for valid nonces.
    await _owned_session(session_id, user_id, db)

    result = await db.execute(
        select(Verification).where(
            Verification.session_id == session_id,
            Verification.nonce == nonce,
            Verification.state == "requested",
        )
    )
    v = result.scalar_one_or_none()
    if not v:
        # Same response for "wrong nonce" and "already resolved" — a replayed
        # nonce learns nothing new.
        raise HTTPException(
            status_code=404, detail="Verification not found or already resolved"
        )

    now = datetime.now(timezone.utc)
    expires_at = v.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        v.state = "timeout"
        await db.commit()
        await manager.publish(session_id, ev.verification_result(
            session_id, v.id, "timeout", v.method
        ))
        raise HTTPException(status_code=410, detail="Verification expired")

    v.state = new_state
    v.resolved_at = now
    await db.commit()
    await db.refresh(v)

    state = manager.get_state(session_id)
    if state is not None:
        state.verification_outcome = new_state

    await manager.publish(session_id, ev.verification_result(
        session_id=session_id,
        verification_id=v.id,
        outcome=new_state,
        method=v.method,
    ))
    await manager.publish(session_id, ev.detected_event(
        session_id,
        f"verification_{new_state}",
        f"Independent verification {new_state}",
        "policy",
        "critical" if new_state == "rejected" else "info",
    ))

    # A verification outcome is evidence. Re-fuse and re-decide now: a held
    # transaction is waiting on exactly this, and no further audio may arrive.
    if state is not None:
        events = recompute_after_outcome(state)
        await manager.publish_many(session_id, events)
        await persist_snapshot(session_id, events[0] if events else None)

    return _to_response(v)


async def _owned_session(session_id: str, user_id: str, db: AsyncSession) -> Session:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _to_response(v: Verification) -> VerificationResponse:
    return VerificationResponse(
        id=v.id,
        session_id=v.session_id,
        method=v.method,
        state=v.state,
        expires_at=v.expires_at,
        nonce=v.nonce,
    )
