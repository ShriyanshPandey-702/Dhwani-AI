"""Risk endpoint — GET /risk/{session_id} returns latest risk snapshot."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import RiskSnapshot, Session, User

router = APIRouter()


class RiskResponse(BaseModel):
    session_id: str
    risk_score: int
    risk_state: str
    authenticity: float | None
    identity: float | None
    context: float | None
    consequence: str | None
    reasons: list


@router.get("/{session_id}", response_model=RiskResponse)
async def get_risk(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify session ownership
    s_result = await db.execute(
        select(Session).where(Session.id == session_id, Session.user_id == current_user.id)
    )
    if not s_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.session_id == session_id)
        .order_by(RiskSnapshot.created_at.desc())
        .limit(1)
    )
    snap = result.scalar_one_or_none()
    if not snap:
        return RiskResponse(
            session_id=session_id,
            risk_score=0,
            risk_state="insufficient_evidence",
            authenticity=None, identity=None, context=None,
            consequence=None, reasons=["No evidence collected yet"],
        )

    return RiskResponse(
        session_id=session_id,
        risk_score=snap.risk_score,
        risk_state=snap.risk_state,
        authenticity=snap.authenticity,
        identity=snap.identity,
        context=snap.context,
        consequence=snap.consequence,
        reasons=snap.reasons,
    )
