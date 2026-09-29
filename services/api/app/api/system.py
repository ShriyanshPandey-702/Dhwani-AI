"""System & Integration Capabilities endpoint — exposes factual capabilities, policy, and privacy controls."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, List

from app.risk.policy import DEFAULT_POLICY_CONFIG

router = APIRouter()


class CapabilitiesResponse(BaseModel):
    telephony: Dict[str, str]
    api: Dict[str, str]
    alerts: Dict[str, str]
    language: Dict[str, str]
    enterprise: Dict[str, Any]
    privacy: Dict[str, Any]


class PrivacyResponse(BaseModel):
    raw_audio_retained: bool
    features_logged_only: bool
    embeddings_protected: bool
    session_data_retention: str
    compliance_disclaimer: str


class PolicyResponse(BaseModel):
    version: str
    thresholds: Dict[str, int]
    weights: Dict[str, float]
    consequence_multiplier: Dict[str, float]
    challenge_required_at: str
    oob_required_at: str


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities():
    """Expose factual system and external integration status."""
    return CapabilitiesResponse(
        telephony={
            "cellular_metadata": "available",
            "cellular_audio": "unsupported",
            "voip_media": "available",
        },
        api={
            "rest": "available",
            "websocket": "available",
        },
        alerts={
            "in_app": "available",
            "push": "available",
            "email": "not_connected",
            "sms": "not_connected",
        },
        language={
            "transcription": "available",
            "threat_semantics": "supported_en_hi",
        },
        enterprise={
            "api_ready": True,
            "multi_tenant": False,
            "sso": False,
        },
        privacy={
            "raw_audio_retained": False,
            "features_logged_only": True,
            "embeddings_protected": True,
            "processing_location": "local_or_on_premise",
        },
    )


@router.get("/privacy", response_model=PrivacyResponse)
async def get_privacy():
    """Expose factual privacy controls."""
    return PrivacyResponse(
        raw_audio_retained=False,
        features_logged_only=True,
        embeddings_protected=True,
        session_data_retention="ephemeral_session_scope",
        compliance_disclaimer="Factual privacy controls enforced; no external regulatory certification simulated.",
    )


@router.get("/policy", response_model=PolicyResponse)
async def get_policy():
    """Expose current frozen Security Policy configuration."""
    return PolicyResponse(
        version="v1.0-frozen",
        thresholds=DEFAULT_POLICY_CONFIG["thresholds"],
        weights=DEFAULT_POLICY_CONFIG["weights"],
        consequence_multiplier=DEFAULT_POLICY_CONFIG["consequence_multiplier"],
        challenge_required_at=DEFAULT_POLICY_CONFIG["challenge_required_at"],
        oob_required_at=DEFAULT_POLICY_CONFIG["oob_required_at"],
    )
