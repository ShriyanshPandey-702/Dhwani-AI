"""
Security Policy Engine — maps (risk state, consequence, evidence confidence)
to the action VoiceShield requires before a consequential decision proceeds.

The Risk Engine produces evidence. This module decides what should happen.
All thresholds live in the policy config (DB-backed, versioned) rather than
being hardcoded across the backend or the mobile UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal

from app.risk.engine import STATE_ORDER, INSUFFICIENT

RiskState = Literal["insufficient_evidence", "low", "suspicious", "high", "critical"]
Action = Literal["allow", "challenge", "verify", "hold", "block", "escalate"]

# Human-facing decision shown on the dashboard, per the product spec:
#   ALLOW · VERIFY · HOLD · BLOCK / ESCALATE
DECISION_FOR_ACTION = {
    "allow": "ALLOW",
    "challenge": "VERIFY",   # a challenge is an in-band verification step
    "verify": "VERIFY",
    "hold": "HOLD",
    "block": "BLOCK",
    "escalate": "ESCALATE",
}


@dataclass
class PolicyDecision:
    action: Action
    decision: str            # ALLOW | VERIFY | HOLD | BLOCK | ESCALATE
    reasons: List[str] = field(default_factory=list)
    recommended_action: str = ""


DEFAULT_POLICY_CONFIG = {
    "thresholds": {"low": 20, "suspicious": 40, "high": 65, "critical": 85},
    "weights": {"authenticity": 0.50, "identity": 0.25, "context": 0.25},
    "consequence_multiplier": {"low": 1.0, "medium": 1.15, "high": 1.30, "critical": 1.50},
    "challenge_required_at": "suspicious",
    "oob_required_at": "high",
    "hold_required_at": "critical",
    # Below this evidence confidence a high-consequence request cannot be
    # auto-allowed — the system asks for independent verification instead of
    # guessing from a thin evidence surface.
    "min_confidence_for_allow": 0.25,
    # Gated Corroboration Fusion (Model B with Multi-Window Persistence)
    "authenticity_uncorroborated_cap": 35.0,
    "uncorroborated_total_cap": 38.0,
    "identity_corroboration_threshold": 0.40,
    "context_corroboration_threshold": 0.25,
    "corroboration_threshold": 0.25,
    "corroboration_persistence": 2,
}


def _rank(state: str) -> int:
    try:
        return STATE_ORDER.index(state)
    except ValueError:
        return 0


def required_action(
    risk_state: str,
    consequence: str,
    policy_config: dict | None = None,
) -> Action:
    """Return the mandatory action for a (risk_state, consequence) pair."""
    cfg = policy_config or DEFAULT_POLICY_CONFIG
    hold_at = cfg.get("hold_required_at", "critical")
    oob_at = cfg.get("oob_required_at", "high")
    chal_at = cfg.get("challenge_required_at", "suspicious")

    # Insufficient evidence is never silently treated as "safe" when the
    # requested action carries real consequence.
    if risk_state == INSUFFICIENT:
        return "verify" if consequence in ("high", "critical") else "allow"

    rank = _rank(risk_state)
    if rank >= _rank(hold_at):
        return "hold"
    if rank >= _rank(oob_at):
        return "verify"
    if rank >= _rank(chal_at):
        return "challenge"
    return "allow"


def evaluate(
    risk_state: str,
    consequence: str,
    reasons: List[str] | None = None,
    evidence_confidence: float = 1.0,
    policy_config: dict | None = None,
) -> PolicyDecision:
    """
    Full policy evaluation used by the WebSocket gateway.

    Adds the low-confidence guard on top of `required_action`: a thin evidence
    surface plus a high-consequence request escalates to VERIFY rather than
    ALLOW.
    """
    cfg = policy_config or DEFAULT_POLICY_CONFIG
    action = required_action(risk_state, consequence, cfg)
    out_reasons = list(reasons or [])

    min_conf = cfg.get("min_confidence_for_allow", 0.25)
    if (
        action == "allow"
        and consequence in ("high", "critical")
        and evidence_confidence < min_conf
    ):
        action = "verify"
        out_reasons.append("insufficient_evidence_for_high_consequence")

    return PolicyDecision(
        action=action,
        decision=DECISION_FOR_ACTION.get(action, "ALLOW"),
        reasons=out_reasons,
        recommended_action=RECOMMENDED_ACTION_TEXT.get(action, "Continue monitoring"),
    )


RECOMMENDED_ACTION_TEXT = {
    "allow": "Continue monitoring",
    "challenge": "Challenge the caller",
    "verify": "Independent verification",
    "hold": "Hold the transaction and verify out-of-band",
    "block": "Block and escalate",
    "escalate": "Escalate to the security team",
}
