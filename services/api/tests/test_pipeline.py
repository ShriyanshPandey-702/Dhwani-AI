"""
Analysis pipeline — the full DETECT → SCORE → DECIDE path over mock audio,
without a database or a socket.
"""

import pytest

from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.simulation.mock_audio import generate_frame, generate_silence
from app.websocket import events as ev
from app.websocket.manager import MAX_HISTORY, SessionState
from app.websocket import pipeline as pl
from app.websocket.pipeline import analyze_window


@pytest.fixture(autouse=True)
def _demo_backends(monkeypatch):
    """
    This module pins the deterministic demonstration, so it must run against the
    demo backends whatever PIPELINE_MODE the environment sets. Real-model
    behaviour is covered by tests/test_ml_*.py.
    """
    from app.ml.authenticity.detector import AuthenticityDetector, HEURISTIC_DEMO
    from app.ml.context.transcriber import Transcriber
    from app.ml.identity.speaker import SpeakerIdentity

    monkeypatch.setattr(pl, "authenticity_detector",
                        AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO))
    monkeypatch.setattr(pl, "speaker_identity",
                        SpeakerIdentity(pipeline_mode=HEURISTIC_DEMO))
    monkeypatch.setattr(pl, "transcriber", Transcriber(pipeline_mode=HEURISTIC_DEMO))
    yield


def fresh_state(session_id: str) -> SessionState:
    # Per-session ML state is global by design (model singletons), so each test
    # clears it the same way the gateway does on disconnect.
    pl.speaker_identity.clear(session_id)
    pl.transcriber.reset(session_id)
    pl.context_classifier.reset(session_id)
    pl.stream_windower.reset(session_id)
    return SessionState(
        session_id=session_id, user_id="user-1",
        policy_config=dict(DEFAULT_POLICY_CONFIG),
    )


def run_scenario(session_id: str, steps: int = 12):
    state = fresh_state(session_id)
    all_events = []
    for step in range(steps):
        all_events.extend(analyze_window(state, generate_frame(step, steps), "mock"))
    return state, all_events


def risk_updates(events):
    return [e for e in events if e["type"] == ev.RISK_UPDATE]


# ── The headline scenario ─────────────────────────────────────────────────────

def test_scenario_escalates_from_insufficient_evidence_to_critical():
    state, events = run_scenario("pipe-escalate")
    updates = risk_updates(events)

    assert len(updates) >= 10
    scores = [u["risk_score"] for u in updates]
    states = [u["risk_state"] for u in updates]

    assert scores[0] < scores[-1], scores
    assert states[0] in {"insufficient_evidence", "low"}
    assert states[-1] == "critical"
    assert {"suspicious", "high", "critical"} <= set(states)


def test_decision_walks_allow_to_verify_to_hold():
    _, events = run_scenario("pipe-decision")
    decisions = [u["decision"] for u in risk_updates(events)]
    assert decisions[0] == "ALLOW"
    assert "VERIFY" in decisions
    assert decisions[-1] == "HOLD"


def test_all_three_evidence_streams_are_populated_and_separate():
    _, events = run_scenario("pipe-streams")
    final = risk_updates(events)[-1]

    assert final["authenticity"] is not None
    assert final["identity"] is not None
    assert final["context"] is not None

    # Authenticity carries no context fields and vice versa.
    assert "otp_request" not in final["authenticity"]
    assert "spoof_probability" not in final["context"]
    assert "spoof_probability" not in final["identity"]


def test_timeline_reports_each_finding_exactly_once():
    _, events = run_scenario("pipe-timeline")
    labels = [e["label"] for e in events if e["type"] == ev.DETECTED_EVENT]
    assert len(labels) == len(set(labels)), labels
    assert any("OTP" in label for label in labels)
    assert any("threshold" in label.lower() for label in labels)


def test_alerts_fire_once_per_severity():
    _, events = run_scenario("pipe-alerts")
    severities = [e["severity"] for e in events if e["type"] == ev.ALERT]
    assert sorted(severities) == sorted(set(severities))
    assert "high" in severities
    assert "critical" in severities


def test_policy_decision_events_are_emitted_on_change_only():
    _, events = run_scenario("pipe-policy")
    decisions = [e["decision"] for e in events if e["type"] == ev.POLICY_DECISION]
    assert decisions == ["VERIFY", "HOLD"]


def test_every_window_reports_audio_quality():
    _, events = run_scenario("pipe-quality", steps=5)
    quality_events = [e for e in events if e["type"] == ev.AUDIO_QUALITY]
    assert len(quality_events) == 5
    assert all(e["audio"]["quality"] in {"GOOD", "FAIR", "POOR"} for e in quality_events)


def test_mock_audio_is_labelled_as_mock_on_the_wire():
    _, events = run_scenario("pipe-label", steps=3)
    for update in risk_updates(events):
        assert update["pipeline_mode"] == "mock"
        assert update["authenticity"]["is_mock"] is True


# ── Robustness ────────────────────────────────────────────────────────────────

def test_silence_produces_no_risk_update():
    """Silence is not evidence — it may flag poor quality, but never scores."""
    state = fresh_state("pipe-silence")
    events = analyze_window(state, generate_silence(), "mock")
    assert risk_updates(events) == []
    assert state.risk_history == []
    assert {e["type"] for e in events} <= {ev.AUDIO_QUALITY, ev.DETECTED_EVENT}


def test_malformed_audio_does_not_raise_or_score():
    state = fresh_state("pipe-malformed")
    for payload in (b"", b"\x00", b"not-really-pcm"):
        events = analyze_window(state, payload, "mock")
        assert risk_updates(events) == []
        assert {e["type"] for e in events} <= {ev.AUDIO_QUALITY, ev.DETECTED_EVENT}
    assert state.risk_history == []


def test_silence_mid_call_preserves_the_existing_risk_picture():
    state = fresh_state("pipe-gap")
    for step in range(6):
        analyze_window(state, generate_frame(step, 12), "mock")
    before = state.risk_history[-1]

    analyze_window(state, generate_silence(), "mock")
    assert state.risk_history[-1] == before
    assert state.last_context is not None


def test_risk_history_is_bounded():
    state = fresh_state("pipe-bounded")
    for step in range(MAX_HISTORY + 30):
        analyze_window(state, generate_frame(step % 12, 12), "mock")
    assert len(state.risk_history) == MAX_HISTORY


def test_peak_risk_is_tracked_for_the_incident_record():
    state, _ = run_scenario("pipe-peak")
    assert state.peak_risk_score == max(state.risk_history)
    assert state.peak_risk_state == "critical"


def test_a_new_session_starts_from_a_clean_slate():
    state_a, _ = run_scenario("pipe-reset")
    assert state_a.peak_risk_score > 50

    state_b = fresh_state("pipe-reset")
    events = analyze_window(state_b, generate_frame(0, 12), "mock")
    first = risk_updates(events)[0]
    assert first["risk_score"] < state_a.peak_risk_score
    assert first["context"]["otp_request"] is False
    assert state_b.risk_history == [first["risk_score"]]


# ── Interactive outcomes must move the authoritative decision ─────────────────
#
# A challenge or verification result is evidence in its own right. It must be
# fused immediately, not lazily on the next audio window — once the audio stops
# (exactly when a held transaction awaits verification) no window ever arrives.

from app.websocket.pipeline import recompute_after_outcome  # noqa: E402


def _run_to(session_id: str, updates: int):
    """Run the scenario until `updates` risk updates have been produced."""
    state = fresh_state(session_id)
    seen = 0
    for step in range(12):
        events = analyze_window(state, generate_frame(step, 12), "mock")
        seen += len(risk_updates(events))
        if seen >= updates:
            break
    return state


def test_recompute_without_prior_evidence_is_a_no_op():
    """Nothing to revise yet — the first audio window will fuse the outcome."""
    state = fresh_state("outcome-empty")
    state.challenge_outcome = "failed"
    assert recompute_after_outcome(state) == []
    assert state.risk_history == []


def test_failed_challenge_raises_the_authoritative_score_immediately():
    state = _run_to("outcome-chal-fail", 5)
    before_score = state.risk_history[-1]
    before_decision = state.last_decision

    state.challenge_outcome = "failed"
    events = recompute_after_outcome(state)
    update = risk_updates(events)[0]

    assert update["risk_score"] > before_score
    assert update["risk_score"] - before_score == 20  # _CHALLENGE_DELTA["failed"]
    assert "challenge_failed" in update["reasons"]
    assert state.risk_history[-1] == update["risk_score"]
    # The decision is re-derived by the policy engine, not merely relabelled.
    assert update["decision"] in {"ALLOW", "VERIFY", "HOLD", "BLOCK", "ESCALATE"}
    assert state.last_decision == update["decision"]
    if update["decision"] != before_decision:
        assert any(e["type"] == ev.POLICY_DECISION for e in events)


def test_passed_challenge_lowers_the_authoritative_score():
    state = _run_to("outcome-chal-pass", 6)
    before = state.risk_history[-1]

    state.challenge_outcome = "passed"
    update = risk_updates(recompute_after_outcome(state))[0]

    assert before - update["risk_score"] == 12  # _CHALLENGE_DELTA["passed"]
    assert "challenge_passed" in update["reasons"]


def test_approved_verification_releases_a_held_transaction():
    """The decisive case: HOLD must become VERIFY once approval lands."""
    state = _run_to("outcome-verify-approve", 12)
    assert state.last_decision == "HOLD", state.last_decision
    before = state.risk_history[-1]

    state.verification_outcome = "approved"
    events = recompute_after_outcome(state)
    update = risk_updates(events)[0]

    assert before - update["risk_score"] == 20  # _VERIFICATION_DELTA["approved"]
    assert "verification_approved" in update["reasons"]
    assert update["decision"] == "VERIFY"
    assert state.last_decision == "VERIFY"

    decisions = [e for e in events if e["type"] == ev.POLICY_DECISION]
    assert decisions, "a decision change must emit policy_decision"
    assert decisions[0]["decision"] == "VERIFY"
    assert decisions[0]["action"] == "verify"


def test_rejected_verification_raises_risk_rather_than_lowering_it():
    state = _run_to("outcome-verify-reject", 5)
    before = state.risk_history[-1]

    state.verification_outcome = "rejected"
    update = risk_updates(recompute_after_outcome(state))[0]

    assert update["risk_score"] - before == 25  # _VERIFICATION_DELTA["rejected"]
    assert "verification_rejected" in update["reasons"]


def test_recompute_reuses_evidence_without_inventing_new_stream_data():
    """Re-fusing must not fabricate or drop per-stream evidence."""
    state = _run_to("outcome-streams", 8)
    auth_before = dict(state.last_authenticity)
    ctx_before = dict(state.last_context)

    state.challenge_outcome = "failed"
    update = risk_updates(recompute_after_outcome(state))[0]

    assert update["authenticity"] == auth_before
    assert update["context"] == ctx_before
    assert state.last_authenticity == auth_before
    assert state.last_context == ctx_before


def test_outcome_is_also_fused_by_the_next_audio_window():
    """The lazy path still works — the fix adds immediacy, it does not replace it."""
    state = _run_to("outcome-next-window", 5)
    state.challenge_outcome = "failed"
    events = analyze_window(state, generate_frame(5, 12), "mock")
    update = risk_updates(events)[0]
    assert "challenge_failed" in update["reasons"]


# ── Real ML integration must not disturb the deterministic demonstration ──────

def test_mock_mode_produces_the_exact_sih_demo_trajectory():
    """
    The demonstration is a contract: LOW → SUSPICIOUS → HIGH → CRITICAL with
    ALLOW → VERIFY → HOLD, at these exact scores. Real ML integration must not
    move it by a single point.
    """
    state = fresh_state("mock-contract")
    observed = []
    for step in range(12):
        for event in analyze_window(state, generate_frame(step, 12), "mock"):
            if event["type"] == ev.RISK_UPDATE:
                observed.append((event["risk_score"], event["risk_state"], event["decision"]))

    assert [s for s, _, _ in observed] == [6, 14, 21, 35, 40, 47, 68, 79, 85, 87, 91, 93]
    assert {st for _, st, _ in observed} >= {"low", "suspicious", "high", "critical"}
    assert [d for _, _, d in observed][0] == "ALLOW"
    assert [d for _, _, d in observed][-1] == "HOLD"
    assert "VERIFY" in {d for _, _, d in observed}


def test_mock_mode_labels_every_stream_as_not_real_ml():
    """Nothing in demo mode may claim to be a trained model."""
    state = fresh_state("mock-labels")
    for step in range(3):
        events = analyze_window(state, generate_frame(step, 12), "mock")
    update = risk_updates(events)[-1]

    assert update["authenticity"]["is_mock"] is True
    assert update["authenticity"]["pipeline_mode"] != "real_ml"
    assert update["identity"]["is_mock"] is True
    assert update["context"]["transcript_is_mock"] is True
    # The context RULES are real even in demo mode; only the transcript is not.
    assert update["context"]["is_mock"] is False


def test_evidence_streams_stay_structurally_separate():
    """
    Fusion happens only in the Risk Engine. No stream may carry another's
    fields — an OTP request must never appear inside authenticity evidence.
    """
    state = fresh_state("separation")
    for step in range(4):
        events = analyze_window(state, generate_frame(step, 12), "mock")
    update = risk_updates(events)[-1]

    auth, ident, ctx = update["authenticity"], update["identity"], update["context"]
    assert not ({"otp_request", "financial_request", "transcript", "match_score"} & set(auth))
    assert not ({"spoof_probability", "acoustic_anomaly", "otp_request"} & set(ident))
    assert not ({"spoof_probability", "match_score", "similarity"} & set(ctx))


def test_backend_provenance_is_recorded_for_the_audit_trail():
    MODEL_VERSIONS = pl.MODEL_VERSIONS

    for key in ("authenticity", "identity", "stt", "context",
                "authenticity_backend", "identity_backend", "stt_backend",
                "pipeline_mode"):
        assert key in MODEL_VERSIONS, f"incident records must carry {key}"
