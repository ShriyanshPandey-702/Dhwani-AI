"""
Incident endpoints — audit records plus the aggregates the Home screen's
Security Overview dashboard renders.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Incident, Session, User

router = APIRouter()

ELEVATED_STATES = {"high", "critical"}


class IncidentSummary(BaseModel):
    id: str
    session_id: str
    final_state: str
    peak_risk_score: Optional[int]
    peak_risk_state: Optional[str]
    action_taken: Optional[str] = None
    created_at: datetime


class IncidentDetail(IncidentSummary):
    # "model_versions" collides with pydantic's protected "model_" namespace.
    model_config = ConfigDict(protected_namespaces=())

    verification_outcome: Optional[str]
    evidence_summary: dict
    integrity_hash: str
    policy_version: str
    model_versions: dict


class OverviewStats(BaseModel):
    """Aggregates for the Home security-overview dashboard."""

    total_calls_today: int
    safe_calls: int
    suspicious_calls: int
    high_critical_calls: int
    active_alerts: int
    average_risk: int
    recent: List[IncidentSummary]
    # True when the figures come from real recorded incidents rather than an
    # empty database; the client labels an empty state rather than inventing data.
    has_data: bool


@router.get("", response_model=List[IncidentSummary])
async def list_incidents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Incident)
        .where(Incident.user_id == current_user.id)
        .order_by(Incident.created_at.desc())
        .limit(50)
    )
    return [_summary(i) for i in result.scalars().all()]


# Declared before /{incident_id} so "stats" is never parsed as an incident id.
@router.get("/stats/overview", response_model=OverviewStats)
async def overview_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Today's activity plus the most recent monitored calls."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    today_result = await db.execute(
        select(Incident).where(
            Incident.user_id == current_user.id,
            Incident.created_at >= since,
        )
    )
    today = list(today_result.scalars().all())

    recent_result = await db.execute(
        select(Incident)
        .where(Incident.user_id == current_user.id)
        .order_by(Incident.created_at.desc())
        .limit(10)
    )
    recent = [_summary(i) for i in recent_result.scalars().all()]

    # Sessions started in the window that produced no incident still count as
    # monitored calls — a quiet call is a real call.
    session_result = await db.execute(
        select(Session).where(
            Session.user_id == current_user.id,
            Session.created_at >= since,
        )
    )
    session_count = len(list(session_result.scalars().all()))

    scores = [i.peak_risk_score for i in today if i.peak_risk_score is not None]
    states = [(i.peak_risk_state or i.final_state or "").lower() for i in today]

    suspicious = sum(1 for s in states if s == "suspicious")
    elevated = sum(1 for s in states if s in ELEVATED_STATES)
    total_calls = max(session_count, len(today))
    safe = max(0, total_calls - suspicious - elevated)

    return OverviewStats(
        total_calls_today=total_calls,
        safe_calls=safe,
        suspicious_calls=suspicious,
        high_critical_calls=elevated,
        active_alerts=elevated,
        average_risk=int(round(sum(scores) / len(scores))) if scores else 0,
        recent=recent,
        has_data=bool(today or recent or session_count),
    )


@router.get("/{incident_id}", response_model=IncidentDetail)
async def get_incident(
    incident_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Incident).where(
            Incident.id == incident_id,
            Incident.user_id == current_user.id,
        )
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return IncidentDetail(
        **_summary(incident).model_dump(),
        verification_outcome=incident.verification_outcome,
        evidence_summary=incident.evidence_summary,
        integrity_hash=incident.integrity_hash,
        policy_version=incident.policy_version,
        model_versions=incident.model_versions,
    )


def _summary(i: Incident) -> IncidentSummary:
    return IncidentSummary(
        id=i.id,
        session_id=i.session_id,
        final_state=i.final_state,
        peak_risk_score=i.peak_risk_score,
        peak_risk_state=i.peak_risk_state,
        action_taken=i.action_taken,
        created_at=i.created_at,
    )
