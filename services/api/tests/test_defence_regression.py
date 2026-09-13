"""
Interactive-defence regression (§18 cases A-E).

These guard the property that matters after a challenge or an out-of-band
verification: the *backend* recomputes the authoritative decision. A pending,
expired, or foreign response must never be mistaken for an approval.
"""

from __future__ import annotations

import pytest

from app.risk.engine import EvidenceBundle, compute_risk
from app.risk import policy
from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.websocket.manager import SessionState
from app.websocket.pipeline import fuse_and_decide


def _state(session_id="def-test", **kw) -> SessionState:
    s = SessionState(session_id=session_id, user_id="u",
                     policy_config=dict(DEFAULT_POLICY_CONFIG))
    # A risky call: synthetic-looking voice, identity mismatch, sensitive ask.
    # Field names follow SessionState.evidence() exactly — match_score and
    # context score are 0-100 there, not 0-1.
    # Deliberately mid-range: a saturated 100/100 call would clamp and hide the
    # very deltas these tests exist to observe.
    s.last_authenticity = {"spoof_probability": 0.60, "confidence": 0.7}
    s.last_identity = {"match_score": 60, "confidence": 0.7,
                       "enrollment_status": "ENROLLED"}
    s.last_context = {"score": 40, "confidence": 0.7}
    s.consequence = "low"
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def _decide(state):
    update, verdict = fuse_and_decide(state, "live")
    return update, verdict


# ── CASE A: challenge failed escalates ───────────────────────────────────────

def test_case_a_failed_challenge_changes_the_authoritative_state():
    before, _ = _decide(_state())
    after, _ = _decide(_state(challenge_outcome="failed"))
    assert after["risk_score"] > before["risk_score"]


# ── CASE B: verification approved is recomputed by the backend ───────────────

def test_case_b_approved_verification_changes_the_authoritative_state():
    before, _ = _decide(_state())
    after, _ = _decide(_state(verification_outcome="approved"))
    assert after["risk_score"] < before["risk_score"]


# ── CASE C: pending is not approval ──────────────────────────────────────────

def test_case_c_pending_verification_is_not_treated_as_approval():
    baseline, _ = _decide(_state())
    pending, _ = _decide(_state(verification_outcome=None))
    approved, _ = _decide(_state(verification_outcome="approved"))
    assert pending["risk_score"] == baseline["risk_score"]
    assert pending["risk_score"] > approved["risk_score"], \
        "a pending verification lowered risk as if approved"


@pytest.mark.parametrize("bogus", ["", "pending", "requested", "unknown", "APPROVED "])
def test_case_c_only_the_exact_approved_token_reduces_risk(bogus):
    """A near-miss string must not be silently read as an approval."""
    baseline, _ = _decide(_state())
    other, _ = _decide(_state(verification_outcome=bogus))
    assert other["risk_score"] == baseline["risk_score"], bogus


# ── CASE D: expired verification is not approval ─────────────────────────────

def test_case_d_expired_verification_does_not_count_as_approval():
    baseline, _ = _decide(_state())
    timed_out, _ = _decide(_state(verification_outcome="timeout"))
    approved, _ = _decide(_state(verification_outcome="approved"))
    assert timed_out["risk_score"] == baseline["risk_score"]
    assert timed_out["risk_score"] > approved["risk_score"]


def test_case_d_expiry_path_never_writes_an_outcome_onto_the_session():
    """
    The API marks an expired request `timeout` and raises 410; it must not set
    `verification_outcome`, which is what the Risk Engine reads.
    """
    import inspect
    from app.api import verification as vapi
    src = inspect.getsource(vapi._resolve)
    expiry = src[src.index("if expires_at < now:"):src.index("raise HTTPException(status_code=410")]
    assert "verification_outcome" not in expiry


# ── CASE E: a response from another session is rejected ──────────────────────

def test_case_e_outcome_from_another_session_does_not_reach_this_session():
    victim = _state("victim")
    attacker = _state("attacker", verification_outcome="approved")
    v_update, _ = _decide(victim)
    a_update, _ = _decide(attacker)
    assert victim.verification_outcome is None
    assert v_update["risk_score"] > a_update["risk_score"]
    assert v_update["session_id"] != a_update["session_id"]


def test_case_e_verification_lookup_is_scoped_to_the_session_and_owner():
    import inspect
    from app.api import verification as vapi
    src = inspect.getsource(vapi._resolve)
    assert "Verification.session_id == session_id" in src, "nonce lookup not session-scoped"
    assert "_owned_session(session_id, user_id" in src, "ownership not enforced"
    assert 'Verification.state == "requested"' in src, "resolved nonces are replayable"


# ── The engine remains the only authority ────────────────────────────────────

def test_interactive_outcomes_only_move_risk_through_the_risk_engine():
    """Deltas come from the engine's own table, not from the transport layer."""
    common = dict(authenticity=0.60, authenticity_confidence=0.7,
                  identity_similarity=0.60, identity_confidence=0.7,
                  context_risk=0.40, context_confidence=0.7, consequence="low")
    base = compute_risk(EvidenceBundle(**common))
    failed = compute_risk(EvidenceBundle(**common, challenge_outcome="failed"))
    assert failed.score > base.score
    assert "challenge_failed" in failed.reasons
