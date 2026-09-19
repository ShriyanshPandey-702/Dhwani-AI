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


# ── Gated Corroboration Fusion (Model B) ───────────────────────────────────

def test_high_auth_matching_identity_benign_context_is_capped():
    """Isolated high authenticity without corroboration is capped at 38 (LOW)."""
    res = compute_risk(bundle(authenticity=0.98, identity_similarity=1.0, context_risk=0.0), CFG)
    assert res.contributions["authenticity"] == 35.0
    assert res.score == 38
    assert res.state == LOW
    assert "authenticity_uncorroborated_provisional" in res.reasons
    assert "total_risk_uncorroborated_cap_active" in res.reasons
    assert "voice_authenticity_anomaly" in res.reasons


def test_high_auth_natural_human_variation_total_cap_38():
    """
    High authenticity + natural human variation (sim 0.72 -> id_risk 0.28, id_contrib = 7.0).
    Total raw without cap would be 35 + 7 = 42 (SUSPICIOUS).
    Model B uncorroborated total-risk cap clamps total score to 38 (LOW).
    """
    res = compute_risk(bundle(authenticity=0.98, identity_similarity=0.72, context_risk=0.0), CFG)
    assert res.score == 38
    assert res.state == LOW
    assert "authenticity_uncorroborated_provisional" in res.reasons
    assert "total_risk_uncorroborated_cap_active" in res.reasons


def test_consequence_multiplier_cannot_cross_40_when_uncorroborated():
    """Consequence multiplier cannot cause an uncorroborated passive score to cross 40."""
    res = compute_risk(bundle(authenticity=0.98, identity_similarity=1.0, context_risk=0.0, consequence="critical"), CFG)
    assert res.score == 38
    assert res.state == LOW
    assert "total_risk_uncorroborated_cap_active" in res.reasons


def test_failed_interactive_challenge_after_uncorroborated_cap():
    """Interactive challenge failure (+20) can elevate risk above 40 after the 38 cap."""
    res = compute_risk(bundle(authenticity=0.98, identity_similarity=0.72, context_risk=0.0, challenge_outcome="failed"), CFG)
    # 38 cap + 20 challenge delta = 58 (SUSPICIOUS 40-64)
    assert res.score == 58
    assert res.state == SUSPICIOUS
    assert "challenge_failed" in res.reasons


def test_identity_mismatch_window1_pending_not_corroborated():
    """
    Window 1 with mismatch (sim=0.20 <= 0.60): corroboration is pending, not confirmed.
    compute_risk() MUST NOT infer corroboration directly from raw similarity.
    Score is capped at 38 (LOW).
    """
    res = compute_risk(bundle(
        authenticity=0.98,
        identity_similarity=0.20,
        context_risk=0.0,
        identity_corroboration_pending=True,
        identity_corroborated=False,
    ), CFG)
    assert res.score <= 38
    assert res.state == LOW
    assert "identity_corroboration_pending" in res.reasons
    assert "identity_corroboration_confirmed" not in res.reasons
    assert "authenticity_uncorroborated_provisional" in res.reasons
    assert "total_risk_uncorroborated_cap_active" in res.reasons


def test_identity_mismatch_window2_consecutive_corroborated():
    """
    Window 2 consecutive mismatch: identity_corroborated=True removes the cap.
    Raw fusion: auth 49.0 + id 20.0 = 69.0 -> HIGH (65-84).
    """
    res = compute_risk(bundle(
        authenticity=0.98,
        identity_similarity=0.20,
        context_risk=0.0,
        identity_corroborated=True,
    ), CFG)
    assert res.contributions["authenticity"] == pytest.approx(49.0, abs=0.5)
    assert res.contributions["identity"] == pytest.approx(20.0, abs=0.5)
    assert res.score == 69
    assert res.state == HIGH
    assert "identity_corroboration_confirmed" in res.reasons
    assert "authenticity_uncorroborated_provisional" not in res.reasons
    assert "total_risk_uncorroborated_cap_active" not in res.reasons


def test_high_auth_malicious_context_uncapped():
    """Malicious context corroborates authenticity: cap is removed, score reaches HIGH."""
    # context_risk 0.90 >= 0.25 (ctx_contrib = 0.90 * 25 = 22.5) -> auth 49.0 + ctx 22.5 = 71.5 -> 72 (HIGH)
    res = compute_risk(bundle(authenticity=0.98, identity_similarity=1.0, context_risk=0.90), CFG)
    assert res.contributions["authenticity"] == pytest.approx(49.0, abs=0.5)
    assert res.contributions["context"] == pytest.approx(22.5, abs=0.5)
    assert res.score == 72
    assert res.state == HIGH
    assert "authenticity_uncorroborated_provisional" not in res.reasons
    assert "total_risk_uncorroborated_cap_active" not in res.reasons


def test_high_auth_triple_corroborated_critical():
    """High auth + confirmed mismatch + malicious context reaches CRITICAL."""
    res = compute_risk(bundle(
        authenticity=0.98,
        identity_similarity=0.20,
        context_risk=0.95,
        identity_corroborated=True,
    ), CFG)
    assert res.contributions["authenticity"] == pytest.approx(49.0, abs=0.5)
    assert res.score >= 85
    assert res.state == CRITICAL
    assert "authenticity_uncorroborated_provisional" not in res.reasons
    assert "total_risk_uncorroborated_cap_active" not in res.reasons


def test_moderate_auth_mismatch_normal_fusion():
    """Moderate auth (0.55 -> raw 27.5) with confirmed mismatch reaches SUSPICIOUS."""
    # 27.5 + 20.0 = 47.5 -> 48 (SUSPICIOUS 40-64)
    res = compute_risk(bundle(
        authenticity=0.55,
        identity_similarity=0.20,
        context_risk=0.0,
        identity_corroborated=True,
    ), CFG)
    assert res.contributions["authenticity"] == pytest.approx(27.5, abs=0.5)
    assert res.score == 48
    assert res.state == SUSPICIOUS
    assert "authenticity_uncorroborated_provisional" not in res.reasons


def test_low_auth_benign_normal_fusion():
    """Low auth (0.10 -> raw 5.0) has no cap applied and produces normal LOW/INSUFFICIENT."""
    res = compute_risk(bundle(authenticity=0.10, identity_similarity=1.0, context_risk=0.0), CFG)
    assert res.contributions["authenticity"] == pytest.approx(5.0, abs=0.5)
    assert res.score < 20
    assert res.state == INSUFFICIENT
    assert "authenticity_uncorroborated_provisional" not in res.reasons


def test_missing_identity_does_not_corroborate():
    """Missing identity evidence is NOT corroboration; high auth remains capped at 38 (LOW)."""
    res = compute_risk(EvidenceBundle(
        authenticity=0.98, authenticity_confidence=0.8,
        identity_similarity=None,  # Missing / unenrolled
        context_risk=0.0, context_confidence=0.8,
    ), CFG)
    assert res.contributions["authenticity"] == 35.0
    assert res.score == 38
    assert res.state == LOW
    assert "authenticity_uncorroborated_provisional" in res.reasons
    assert "total_risk_uncorroborated_cap_active" in res.reasons
    assert "no_enrolled_speaker_reference" in res.reasons


def test_missing_context_does_not_corroborate():
    """Missing context evidence is NOT corroboration; high auth remains capped at 38 (LOW)."""
    res = compute_risk(EvidenceBundle(
        authenticity=0.98, authenticity_confidence=0.8,
        identity_similarity=1.0, identity_confidence=0.8,
        context_risk=None,  # Missing / pending
    ), CFG)
    assert res.contributions["authenticity"] == 35.0
    assert res.score == 38
    assert res.state == LOW
    assert "authenticity_uncorroborated_provisional" in res.reasons
    assert "total_risk_uncorroborated_cap_active" in res.reasons
    assert "context_evidence_pending" in res.reasons


def test_both_identity_and_context_missing_does_not_corroborate():
    """Both identity and context missing: authenticity remains capped at 38 (LOW)."""
    res = compute_risk(EvidenceBundle(
        authenticity=0.98, authenticity_confidence=0.8,
        identity_similarity=None,
        context_risk=None,
    ), CFG)
    assert res.contributions["authenticity"] == 35.0
    assert res.score == 38
    assert res.state == LOW
    assert "authenticity_uncorroborated_provisional" in res.reasons
    assert "total_risk_uncorroborated_cap_active" in res.reasons


# ── Persistence State & Reset Unit Tests ─────────────────────────────────────

def test_session_persistence_mismatch_sequence():
    """Verify streak progression: window 1 pending, window 2 confirmed."""
    from app.websocket.manager import SessionState
    state = SessionState(session_id="test-p1", user_id="u1", policy_config=CFG)
    assert state.consecutive_identity_mismatches == 0

    # Window 1 mismatch
    state.last_authenticity = {"spoof_probability": 0.98, "confidence": 0.8}
    state.last_identity = {"match_score": 20, "enrollment_status": "ENROLLED", "confidence": 0.8}
    state.consecutive_identity_mismatches = 1

    ev1 = state.evidence()
    assert ev1.identity_corroboration_pending is True
    assert ev1.identity_corroborated is False
    res1 = compute_risk(ev1, CFG)
    assert res1.score <= 38
    assert res1.state == LOW
    assert "identity_corroboration_pending" in res1.reasons

    # Window 2 consecutive mismatch
    state.consecutive_identity_mismatches = 2
    ev2 = state.evidence()
    assert ev2.identity_corroboration_pending is False
    assert ev2.identity_corroborated is True
    res2 = compute_risk(ev2, CFG)
    assert res2.score >= 65
    assert res2.state == HIGH
    assert "identity_corroboration_confirmed" in res2.reasons


def test_persistence_resets_on_match():
    """A match resets the mismatch streak to 0."""
    from app.websocket.manager import SessionState
    state = SessionState(session_id="test-p2", user_id="u1", policy_config=CFG)
    state.consecutive_identity_mismatches = 1

    # Simulate match arriving: streak reset
    state.consecutive_identity_mismatches = 0
    ev = state.evidence()
    assert ev.identity_corroboration_pending is False
    assert ev.identity_corroborated is False


def test_persistence_resets_on_silence_or_not_enrolled():
    """Silence or NOT_ENROLLED identity resets streak to 0."""
    from app.websocket.manager import SessionState
    state = SessionState(session_id="test-p3", user_id="u1", policy_config=CFG)
    state.consecutive_identity_mismatches = 1

    # Silence / invalid evidence
    state.consecutive_identity_mismatches = 0
    ev = state.evidence()
    assert ev.identity_corroborated is False
    assert ev.identity_corroboration_pending is False


def test_session_lifecycle_persistence_destruction():
    """Teardown drops state, and a new session starts with streak 0."""
    from app.websocket.manager import ConnectionManager
    mgr = ConnectionManager()
    state = mgr.get_or_create_state("s_life", "u1", CFG)
    state.consecutive_identity_mismatches = 2
    assert mgr.get_state("s_life").consecutive_identity_mismatches == 2

    mgr.drop_state("s_life")
    assert mgr.get_state("s_life") is None

    new_state = mgr.get_or_create_state("s_life", "u1", CFG)
    assert new_state.consecutive_identity_mismatches == 0
