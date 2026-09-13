"""
Consequence-aware policy validation (Phase 11).

These assert the property that makes VoiceShield a security system rather than
a classifier: **spoof probability alone does not determine the decision.**
Identity and context are fused with it, and evidence confidence gates how much
any of it is trusted.

Each scenario is a plain Risk Engine + Policy Engine evaluation, so it tests the
authoritative path the WebSocket gateway uses.
"""

import pytest

from app.risk.engine import EvidenceBundle, compute_risk
from app.risk.policy import DEFAULT_POLICY_CONFIG, evaluate

CFG = DEFAULT_POLICY_CONFIG


def decide(**kwargs):
    """Fuse evidence and apply policy, returning (risk, decision)."""
    bundle = EvidenceBundle(**kwargs)
    result = compute_risk(bundle, CFG)
    decision = evaluate(
        risk_state=result.state,
        consequence=bundle.consequence,
        reasons=result.reasons,
        evidence_confidence=result.evidence_confidence,
        policy_config=CFG,
    )
    return result, decision


# ── A. Normal call ───────────────────────────────────────────────────────────

def test_a_bonafide_known_speaker_normal_conversation_is_allowed():
    result, decision = decide(
        authenticity=0.05, authenticity_confidence=0.7,
        identity_similarity=0.95, identity_confidence=0.8,
        context_risk=0.0, context_confidence=0.8, consequence="low",
    )
    assert result.state in ("insufficient_evidence", "low")
    assert decision.decision == "ALLOW"


# ── B. Unknown speaker is an identity signal, not a spoof signal ─────────────

def test_b_unknown_speaker_does_not_imply_synthetic_speech():
    """
    A genuine but unfamiliar human. Identity contributes risk; the authenticity
    stream must stay clean and must not be inflated by the mismatch.
    """
    result, _ = decide(
        authenticity=0.05, authenticity_confidence=0.7,
        identity_similarity=0.10, identity_confidence=0.8,
        context_risk=0.0, context_confidence=0.8, consequence="low",
    )
    assert result.contributions["authenticity"] < 5.0, \
        "identity mismatch must not raise the authenticity contribution"
    assert "speaker_identity_mismatch" in result.reasons
    assert "voice_authenticity_anomaly" not in result.reasons


def test_b2_unknown_speaker_alone_does_not_reach_critical():
    result, decision = decide(
        authenticity=0.05, authenticity_confidence=0.7,
        identity_similarity=0.0, identity_confidence=0.8,
        context_risk=0.0, context_confidence=0.8, consequence="low",
    )
    assert result.state != "critical"
    assert decision.decision != "HOLD"


# ── C–E. Spoof probability interacts with consequence ───────────────────────

def test_c_high_spoof_with_low_consequence_is_not_automatically_critical():
    result, decision = decide(
        authenticity=0.85, authenticity_confidence=0.7,
        identity_similarity=0.9, identity_confidence=0.8,
        context_risk=0.0, context_confidence=0.8, consequence="low",
    )
    assert result.state != "critical"
    assert decision.decision in ("ALLOW", "VERIFY")


def test_d_high_spoof_with_otp_request_elevates_risk():
    low_ctx, _ = decide(
        authenticity=0.85, authenticity_confidence=0.7,
        identity_similarity=0.9, identity_confidence=0.8,
        context_risk=0.0, context_confidence=0.8, consequence="low",
    )
    otp, decision = decide(
        authenticity=0.85, authenticity_confidence=0.7,
        identity_similarity=0.9, identity_confidence=0.8,
        context_risk=0.95, context_confidence=0.85, consequence="critical",
    )
    assert otp.score > low_ctx.score
    assert decision.decision in ("VERIFY", "HOLD")


def test_e_high_spoof_with_financial_transfer_reaches_high_or_critical():
    result, decision = decide(
        authenticity=0.9, authenticity_confidence=0.75,
        identity_similarity=0.6, identity_confidence=0.8,
        context_risk=0.9, context_confidence=0.85, consequence="high",
    )
    assert result.state in ("high", "critical")
    assert decision.decision in ("VERIFY", "HOLD")


# ── F. Identity mismatch plus a sensitive request ───────────────────────────

def test_f_identity_mismatch_with_sensitive_request_requires_verification():
    result, decision = decide(
        authenticity=0.2, authenticity_confidence=0.7,
        identity_similarity=0.1, identity_confidence=0.8,
        context_risk=0.8, context_confidence=0.85, consequence="high",
    )
    assert decision.decision in ("VERIFY", "HOLD")
    assert result.state in ("suspicious", "high", "critical")


# ── G. Insufficient evidence ────────────────────────────────────────────────

def test_g_no_evidence_is_insufficient_not_genuine():
    result, decision = decide()
    assert result.state == "insufficient_evidence"
    assert result.score == 0
    assert decision.decision == "ALLOW"      # low consequence, nothing asked for


def test_g2_insufficient_evidence_with_high_consequence_demands_verification():
    """The safety property: thin evidence must never auto-allow a big ask."""
    _, decision = decide(consequence="critical")
    assert decision.decision == "VERIFY"


def test_g3_stale_evidence_is_never_converted_into_a_verdict():
    result, _ = decide(authenticity=0.99, authenticity_confidence=0.8, stale=True)
    assert result.state == "insufficient_evidence"
    assert result.score == 0


def test_g4_low_confidence_blocks_auto_allow_for_high_consequence():
    """
    Isolates the confidence guard specifically.

    Inputs are chosen so the risk state is LOW — which on its own maps to ALLOW —
    while evidence confidence sits far below `min_confidence_for_allow`. The
    upgrade to VERIFY must therefore come from the guard, not from the
    insufficient-evidence rule that also returns VERIFY.
    """
    result, decision = decide(
        authenticity=0.25, authenticity_confidence=0.05,
        context_risk=0.10, context_confidence=0.05, consequence="critical",
    )
    assert result.state == "low", "the guard, not the insufficient-evidence rule, is under test"
    assert result.evidence_confidence < CFG["min_confidence_for_allow"]
    assert decision.action == "verify"
    assert "insufficient_evidence_for_high_consequence" in decision.reasons


# ── H–I. Interactive outcomes remain authoritative ──────────────────────────

def test_h_verification_approved_reduces_risk_authoritatively():
    base, _ = decide(
        authenticity=0.8, authenticity_confidence=0.75,
        identity_similarity=0.5, identity_confidence=0.8,
        context_risk=0.9, context_confidence=0.85, consequence="critical",
    )
    approved, _ = decide(
        authenticity=0.8, authenticity_confidence=0.75,
        identity_similarity=0.5, identity_confidence=0.8,
        context_risk=0.9, context_confidence=0.85, consequence="critical",
        verification_outcome="approved",
    )
    assert approved.score < base.score
    assert "verification_approved" in approved.reasons


def test_i_challenge_failed_escalates_risk_authoritatively():
    base, _ = decide(
        authenticity=0.4, authenticity_confidence=0.7,
        identity_similarity=0.7, identity_confidence=0.8,
        context_risk=0.5, context_confidence=0.8, consequence="medium",
    )
    failed, _ = decide(
        authenticity=0.4, authenticity_confidence=0.7,
        identity_similarity=0.7, identity_confidence=0.8,
        context_risk=0.5, context_confidence=0.8, consequence="medium",
        challenge_outcome="failed",
    )
    assert failed.score > base.score
    assert "challenge_failed" in failed.reasons


# ── Stream independence, asserted structurally ──────────────────────────────

def test_context_never_changes_the_authenticity_contribution():
    """The invariant: an OTP request is not evidence of synthesis."""
    for ctx in (0.0, 0.5, 1.0):
        result, _ = decide(
            authenticity=0.6, authenticity_confidence=0.7,
            identity_similarity=0.8, identity_confidence=0.8,
            context_risk=ctx, context_confidence=0.8,
        )
        if ctx == 0.0:
            reference = result.contributions["authenticity"]
        assert result.contributions["authenticity"] == pytest.approx(reference)


def test_identity_never_changes_the_authenticity_contribution():
    for sim in (0.0, 0.5, 1.0):
        result, _ = decide(
            authenticity=0.6, authenticity_confidence=0.7,
            identity_similarity=sim, identity_confidence=0.8,
            context_risk=0.3, context_confidence=0.8,
        )
        if sim == 0.0:
            reference = result.contributions["authenticity"]
        assert result.contributions["authenticity"] == pytest.approx(reference)
