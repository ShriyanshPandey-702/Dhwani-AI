"""Policy Engine — risk state to required action mapping."""

import pytest

from app.risk.policy import (
    DEFAULT_POLICY_CONFIG, evaluate, required_action,
)

CFG = DEFAULT_POLICY_CONFIG


# ── The mapping the product specifies ─────────────────────────────────────────

@pytest.mark.parametrize("state,expected_action,expected_decision", [
    ("low",         "allow",     "ALLOW"),
    ("suspicious",  "challenge", "VERIFY"),
    ("high",        "verify",    "VERIFY"),
    ("critical",    "hold",      "HOLD"),
])
def test_state_to_action_mapping(state, expected_action, expected_decision):
    assert required_action(state, "low", CFG) == expected_action
    assert evaluate(state, "low", policy_config=CFG).decision == expected_decision


def test_insufficient_evidence_with_low_consequence_allows():
    assert required_action("insufficient_evidence", "low", CFG) == "allow"


def test_insufficient_evidence_with_high_consequence_requires_verification():
    """Missing evidence must never silently permit a consequential action."""
    assert required_action("insufficient_evidence", "high", CFG) == "verify"
    assert required_action("insufficient_evidence", "critical", CFG) == "verify"


# ── The low-confidence guard ──────────────────────────────────────────────────

def test_thin_evidence_blocks_auto_allow_for_high_consequence():
    decision = evaluate(
        risk_state="low", consequence="critical",
        evidence_confidence=0.05, policy_config=CFG,
    )
    assert decision.action == "verify"
    assert "insufficient_evidence_for_high_consequence" in decision.reasons


def test_strong_evidence_allows_low_risk_high_consequence():
    decision = evaluate(
        risk_state="low", consequence="critical",
        evidence_confidence=0.9, policy_config=CFG,
    )
    assert decision.action == "allow"


def test_low_confidence_does_not_downgrade_a_hold():
    decision = evaluate(
        risk_state="critical", consequence="critical",
        evidence_confidence=0.01, policy_config=CFG,
    )
    assert decision.action == "hold"


# ── Configurability ───────────────────────────────────────────────────────────

def test_policy_thresholds_are_configurable_not_hardcoded():
    strict = {**CFG, "oob_required_at": "suspicious", "hold_required_at": "high"}
    assert required_action("suspicious", "low", strict) == "verify"
    assert required_action("high", "low", strict) == "hold"


def test_unknown_state_is_handled_without_raising():
    assert required_action("banana", "low", CFG) in {
        "allow", "challenge", "verify", "hold", "block", "escalate"
    }


def test_decision_carries_reasons_and_recommendation():
    decision = evaluate(
        risk_state="high", consequence="high",
        reasons=["voice_authenticity_anomaly"],
        evidence_confidence=0.7, policy_config=CFG,
    )
    assert decision.decision == "VERIFY"
    assert "voice_authenticity_anomaly" in decision.reasons
    assert decision.recommended_action
