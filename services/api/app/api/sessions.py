"""Sessions endpoints — create, get, start, stop."""

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import Session, User

router = APIRouter()


class SessionResponse(BaseModel):
    id: str
    state: str
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class CreateSessionRequest(BaseModel):
    metadata: dict = {}


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest = CreateSessionRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = Session(user_id=current_user.id, metadata_=body.metadata)
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _to_response(session)


@router.get("", response_model=List[SessionResponse])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Session).where(Session.user_id == current_user.id).order_by(Session.created_at.desc()).limit(20)
    )
    return [_to_response(s) for s in result.scalars().all()]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    return _to_response(session)


@router.post("/{session_id}/start", response_model=SessionResponse)
async def start_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    if session.state not in ("created",):
        raise HTTPException(status_code=409, detail=f"Session is already {session.state}")
    session.state = "active"
    session.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return _to_response(session)


@router.post("/{session_id}/stop", response_model=SessionResponse)
async def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(session_id, current_user.id, db)
    if session.state not in ("active",):
        raise HTTPException(status_code=409, detail=f"Session is {session.state}, cannot stop")
    session.state = "ended"
    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)
    return _to_response(session)


async def _get_owned_session(session_id: str, user_id: str, db: AsyncSession) -> Session:
    result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _to_response(s: Session) -> SessionResponse:
    return SessionResponse(
        id=s.id, state=s.state,
        started_at=s.started_at, ended_at=s.ended_at,
        created_at=s.created_at,
    )
