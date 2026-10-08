"""SQLAlchemy ORM models — mirrors services/api/schema.sql."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, SmallInteger, String, Text
)

from app.models.types import JSONType, UUIDType
from sqlalchemy.orm import relationship

from app.core.database import Base


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id            = Column(UUIDType, primary_key=True, default=_uuid)
    email         = Column(Text, nullable=False, unique=True, index=True)
    password_hash = Column(Text, nullable=False)
    full_name     = Column(Text, nullable=False, default="")
    role          = Column(String(20), nullable=False, default="user")
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at    = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    devices  = relationship("Device",  back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="user")


class Device(Base):
    __tablename__ = "devices"

    id            = Column(UUIDType, primary_key=True, default=_uuid)
    user_id       = Column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_name   = Column(Text, nullable=False, default="")
    device_token  = Column(Text, nullable=False, unique=True)
    platform      = Column(String(20), nullable=False, default="android")
    is_active     = Column(Boolean, nullable=False, default=True)
    registered_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    last_seen_at  = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="devices")


class Session(Base):
    __tablename__ = "sessions"

    id         = Column(UUIDType, primary_key=True, default=_uuid)
    user_id    = Column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    state      = Column(String(20), nullable=False, default="created")
    started_at = Column(DateTime(timezone=True))
    ended_at   = Column(DateTime(timezone=True))
    metadata_  = Column("metadata", JSONType, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user          = relationship("User", back_populates="sessions")
    risk_snapshots = relationship("RiskSnapshot", back_populates="session", cascade="all, delete-orphan")
    challenges    = relationship("Challenge", back_populates="session", cascade="all, delete-orphan")
    verifications = relationship("Verification", back_populates="session", cascade="all, delete-orphan")
    incident      = relationship("Incident", back_populates="session", uselist=False)


class RiskSnapshot(Base):
    __tablename__ = "risk_snapshots"

    id             = Column(UUIDType, primary_key=True, default=_uuid)
    session_id     = Column(UUIDType, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    risk_score     = Column(SmallInteger, nullable=False)
    risk_state     = Column(String(30), nullable=False)
    authenticity   = Column(Float)
    identity       = Column(Float)
    context        = Column(Float)
    consequence    = Column(String(20))
    reasons        = Column(JSONType, nullable=False, default=list)
    model_versions = Column(JSONType, nullable=False, default=dict)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)

    session = relationship("Session", back_populates="risk_snapshots")


class Challenge(Base):
    __tablename__ = "challenges"

    id             = Column(UUIDType, primary_key=True, default=_uuid)
    session_id     = Column(UUIDType, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    challenge_text = Column(Text, nullable=False)
    challenge_type = Column(String(20), nullable=False, default="phrase")
    state          = Column(String(20), nullable=False, default="pending")
    response_at    = Column(DateTime(timezone=True))
    evidence       = Column(JSONType, nullable=False, default=dict)
    created_at     = Column(DateTime(timezone=True), nullable=False, default=_now)

    session = relationship("Session", back_populates="challenges")


class Verification(Base):
    __tablename__ = "verifications"

    id           = Column(UUIDType, primary_key=True, default=_uuid)
    session_id   = Column(UUIDType, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    device_id    = Column(UUIDType, ForeignKey("devices.id"), nullable=True)
    method       = Column(String(30), nullable=False, default="trusted_device")
    state        = Column(String(20), nullable=False, default="requested")
    requested_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    resolved_at  = Column(DateTime(timezone=True))
    expires_at   = Column(DateTime(timezone=True), nullable=False)
    nonce        = Column(Text, nullable=False, default=_uuid)

    session = relationship("Session", back_populates="verifications")


class Incident(Base):
    __tablename__ = "incidents"

    id                   = Column(UUIDType, primary_key=True, default=_uuid)
    session_id           = Column(UUIDType, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id              = Column(UUIDType, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    final_state          = Column(String(30), nullable=False)
    peak_risk_score      = Column(SmallInteger)
    peak_risk_state      = Column(String(30))
    action_taken         = Column(Text)
    verification_outcome = Column(Text)
    evidence_summary     = Column(JSONType, nullable=False, default=dict)
    policy_version       = Column(String(20), nullable=False, default="v1")
    model_versions       = Column(JSONType, nullable=False, default=dict)
    integrity_hash       = Column(Text, nullable=False)
    created_at           = Column(DateTime(timezone=True), nullable=False, default=_now)

    session = relationship("Session", back_populates="incident")
    user    = relationship("User", back_populates="incidents")


class Policy(Base):
    __tablename__ = "policies"

    id         = Column(UUIDType, primary_key=True, default=_uuid)
    version    = Column(Text, nullable=False, unique=True)
    config     = Column(JSONType, nullable=False)
    is_active  = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
