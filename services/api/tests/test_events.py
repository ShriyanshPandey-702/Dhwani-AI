"""WebSocket event contract — envelope shape, sequencing, builder coverage."""

import pytest

from app.websocket import events as ev

SESSION = "sess-test-events"


@pytest.fixture(autouse=True)
def _clean_sequence():
    ev.reset_seq(SESSION)
    yield
    ev.reset_seq(SESSION)


def test_every_event_carries_the_full_envelope():
    event = ev.risk_update(
        session_id=SESSION, risk_score=50, risk_state="suspicious",
        risk_trend="rising", evidence_confidence=0.5,
        authenticity=None, identity=None, context=None,
        decision="VERIFY", reasons=[], consequence="low",
        contributions={}, pipeline_mode="mock",
    )
    for field in ("type", "event_id", "seq", "session_id", "timestamp"):
        assert field in event, field
    assert event["session_id"] == SESSION
    assert event["type"] in ev.EVENT_TYPES


def test_sequence_numbers_are_monotonic_per_session():
    seqs = [ev.detected_event(SESSION, "c", "l", "risk")["seq"] for _ in range(5)]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == 5
    assert seqs[0] == 1


def test_sequences_are_independent_across_sessions():
    other = "sess-other"
    ev.reset_seq(other)
    try:
        a = ev.detected_event(SESSION, "c", "l", "risk")["seq"]
        b = ev.detected_event(other, "c", "l", "risk")["seq"]
        assert a == b == 1
    finally:
        ev.reset_seq(other)


def test_event_ids_are_unique():
    ids = {ev.alert(SESSION, "high", "m", "verify")["event_id"] for _ in range(20)}
    assert len(ids) == 20


def test_reset_seq_restarts_numbering():
    ev.detected_event(SESSION, "c", "l", "risk")
    ev.reset_seq(SESSION)
    assert ev.detected_event(SESSION, "c", "l", "risk")["seq"] == 1


def test_risk_update_keeps_evidence_streams_separate():
    event = ev.risk_update(
        session_id=SESSION, risk_score=74, risk_state="high", risk_trend="rising",
        evidence_confidence=0.8,
        authenticity={"score": 68}, identity={"match_score": 82},
        context={"score": 81},
        decision="VERIFY", reasons=["voice_authenticity_anomaly"],
        consequence="high", contributions={}, pipeline_mode="mock",
    )
    assert event["authenticity"]["score"] == 68
    assert event["identity"]["match_score"] == 82
    assert event["context"]["score"] == 81
    # The three objects are distinct — never merged into one blob.
    assert event["authenticity"] is not event["context"]


@pytest.mark.parametrize("builder,kwargs,expected_type", [
    (ev.session_started, {"pipeline_mode": "mock", "model_versions": {}}, "session_started"),
    (ev.audio_quality, {"quality": {}, "active": True}, "audio_quality"),
    (ev.detected_event, {"code": "c", "label": "l", "stream": "risk"}, "detected_event"),
    (ev.alert, {"severity": "high", "message": "m", "recommended_action": "verify"}, "alert"),
    (ev.challenge_started, {"challenge_id": "c1", "challenge_text": "t", "challenge_type": "phrase"}, "challenge_started"),
    (ev.challenge_result, {"challenge_id": "c1", "outcome": "failed"}, "challenge_result"),
    (ev.verification_requested, {"verification_id": "v1", "method": "trusted_device", "expires_at": "2026-01-01T00:00:00Z"}, "verification_requested"),
    (ev.verification_result, {"verification_id": "v1", "outcome": "approved"}, "verification_result"),
    (ev.policy_decision, {"decision": "HOLD", "action": "hold", "reasons": [], "recommended_action": "r", "risk_state": "critical", "risk_score": 90}, "policy_decision"),
    (ev.session_ended, {"reason": "done", "peak_risk_score": 90, "peak_risk_state": "critical"}, "session_ended"),
    (ev.error, {"detail": "boom"}, "error"),
])
def test_all_builders_produce_registered_types(builder, kwargs, expected_type):
    event = builder(SESSION, **kwargs)
    assert event["type"] == expected_type
    assert expected_type in ev.EVENT_TYPES
    assert event["session_id"] == SESSION


def test_the_documented_event_types_all_exist():
    """Every event type the product spec requires must be in the registry."""
    required = {
        "session_started", "audio_quality", "risk_update", "detected_event",
        "alert", "challenge_started", "challenge_result",
        "verification_requested", "verification_result", "policy_decision",
        "session_ended", "error",
    }
    assert required <= ev.EVENT_TYPES
