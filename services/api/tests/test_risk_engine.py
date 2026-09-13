"""Risk Engine — fusion, state transitions and evidence handling."""

import pytest

from app.risk.engine import (
    CRITICAL, HIGH, INSUFFICIENT, LOW, SUSPICIOUS,
    EvidenceBundle, classify_state, compute_risk, risk_trend,
)
from app.risk.policy import DEFAULT_POLICY_CONFIG

CFG = DEFAULT_POLICY_CONFIG


def bundle(**kwargs) -> EvidenceBundle:
    base = dict(
        authenticity=0.0, authenticity_confidence=0.8,
        identity_similarity=1.0, identity_confidence=0.8,
        context_risk=0.0, context_confidence=0.8,
    )
    base.update(kwargs)
    return EvidenceBundle(**base)


# ── State transitions ─────────────────────────────────────────────────────────

def test_state_progression_low_to_critical():
    """Rising authenticity + context must walk the full state ladder."""
    observed = []
    for auth, ctx, consequence in [
        (0.05, 0.00, "low"),
        (0.35, 0.20, "low"),
        (0.55, 0.55, "medium"),
        (0.80, 0.85, "high"),
        (0.95, 1.00, "critical"),
    ]:
        result = compute_risk(
            bundle(authenticity=auth, identity_similarity=0.9,
                   context_risk=ctx, consequence=consequence),
            CFG,
        )
        observed.append(result.state)

    # Monotonically non-decreasing, ending at critical.
    order = [INSUFFICIENT, LOW, SUSPICIOUS, HIGH, CRITICAL]
    ranks = [order.index(s) for s in observed]
    assert ranks == sorted(ranks), observed
    assert observed[-1] == CRITICAL
    assert SUSPICIOUS in observed
    assert HIGH in observed


@pytest.mark.parametrize("score,expected", [
    (0, INSUFFICIENT), (19, INSUFFICIENT),
    (20, LOW), (39, LOW),
    (40, SUSPICIOUS), (64, SUSPICIOUS),
    (65, HIGH), (84, HIGH),
    (85, CRITICAL), (100, CRITICAL),
])
def test_classify_state_boundaries(score, expected):
    assert classify_state(score, CFG["thresholds"]) == expected


# ── Insufficient / missing evidence ───────────────────────────────────────────

def test_no_evidence_is_insufficient_not_safe():
    result = compute_risk(EvidenceBundle(), CFG)
    assert result.state == INSUFFICIENT
    assert result.score == 0
    assert result.evidence_confidence == 0.0


def test_stale_evidence_never_becomes_a_verdict():
    result = compute_risk(bundle(authenticity=0.99, stale=True), CFG)
    assert result.state == INSUFFICIENT
    assert result.score == 0
    assert "evidence_stale" in result.reasons


def test_missing_stream_lowers_confidence_but_still_scores():
    full = compute_risk(bundle(authenticity=0.8, context_risk=0.8), CFG)
    partial = compute_risk(
        EvidenceBundle(authenticity=0.8, authenticity_confidence=0.8), CFG
    )
    assert partial.score > 0
    assert partial.evidence_confidence < full.evidence_confidence
    assert "no_enrolled_speaker_reference" in partial.reasons


def test_unenrolled_identity_contributes_nothing():
    result = compute_risk(
        EvidenceBundle(authenticity=0.5, authenticity_confidence=0.8), CFG
    )
    assert result.contributions["identity"] == 0.0


# ── Stream independence ───────────────────────────────────────────────────────

def test_context_does_not_alter_authenticity_contribution():
    """An OTP request must not make the voice look more synthetic."""
    low_ctx = compute_risk(bundle(authenticity=0.6, context_risk=0.0), CFG)
    high_ctx = compute_risk(bundle(authenticity=0.6, context_risk=1.0), CFG)
    assert low_ctx.contributions["authenticity"] == high_ctx.contributions["authenticity"]


def test_identity_mismatch_is_not_reported_as_synthesis():
    result = compute_risk(bundle(authenticity=0.0, identity_similarity=0.1), CFG)
    assert "speaker_identity_mismatch" in result.reasons
    assert "voice_authenticity_anomaly" not in result.reasons


# ── Consequence and interactive evidence ──────────────────────────────────────

def test_consequence_multiplier_raises_score():
    low = compute_risk(bundle(authenticity=0.5, context_risk=0.5, consequence="low"), CFG)
    crit = compute_risk(bundle(authenticity=0.5, context_risk=0.5, consequence="critical"), CFG)
    assert crit.score > low.score


def test_failed_challenge_raises_risk_and_passed_lowers_it():
    base = compute_risk(bundle(authenticity=0.5, context_risk=0.5), CFG)
    failed = compute_risk(
        bundle(authenticity=0.5, context_risk=0.5, challenge_outcome="failed"), CFG)
    passed = compute_risk(
        bundle(authenticity=0.5, context_risk=0.5, challenge_outcome="passed"), CFG)
    assert failed.score > base.score > passed.score
    assert "challenge_failed" in failed.reasons


def test_verification_outcomes_move_risk():
    base = compute_risk(bundle(authenticity=0.6, context_risk=0.6), CFG)
    rejected = compute_risk(
        bundle(authenticity=0.6, context_risk=0.6, verification_outcome="rejected"), CFG)
    approved = compute_risk(
        bundle(authenticity=0.6, context_risk=0.6, verification_outcome="approved"), CFG)
    assert rejected.score > base.score > approved.score


# ── Bounds and robustness ─────────────────────────────────────────────────────

def test_score_is_always_within_bounds():
    extreme = compute_risk(
        bundle(authenticity=5.0, identity_similarity=-3.0, context_risk=9.0,
               consequence="critical", challenge_outcome="failed",
               verification_outcome="rejected"),
        CFG,
    )
    assert 0 <= extreme.score <= 100

    floor = compute_risk(
        bundle(authenticity=0.0, identity_similarity=1.0, context_risk=0.0,
               challenge_outcome="passed", verification_outcome="approved"),
        CFG,
    )
    assert floor.score >= 0


def test_custom_policy_weights_are_respected():
    heavy_context = {
        **CFG,
        "weights": {"authenticity": 0.1, "identity": 0.1, "context": 0.8},
    }
    default = compute_risk(bundle(authenticity=0.0, context_risk=1.0), CFG)
    weighted = compute_risk(bundle(authenticity=0.0, context_risk=1.0), heavy_context)
    assert weighted.score > default.score


# ── Trend ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("history,expected", [
    ([], "stable"),
    ([40], "stable"),
    ([20, 30, 45, 60, 75], "rising"),
    ([80, 70, 55, 40, 25], "falling"),
    ([50, 51, 50, 49, 50], "stable"),
])
def test_risk_trend(history, expected):
    assert risk_trend(history) == expected
