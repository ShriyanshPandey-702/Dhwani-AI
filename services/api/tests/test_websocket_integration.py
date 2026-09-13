"""
WebSocket integration — a real socket, the real gateway, the real pipeline and
the real event contract.

The database layer is faked (no PostgreSQL in CI), but everything the dashboard
depends on runs for real: authentication, session authorisation, the mock audio
driver, the ML stubs, the Risk Engine, the Policy Engine and event emission.

This is the backend half of the "done" criterion:

    backend → WebSocket → structured events → (Zustand → dashboard)

The client half is covered by apps/mobile/VoiceShieldApp/__tests__/riskStore.test.ts,
which drives the same event shapes.
"""

import contextlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.websocket import events as ev
from app.websocket import gateway as gw

SESSION_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    """Answers the two queries the gateway makes, and swallows writes."""

    def __init__(self):
        self._call = 0

    async def execute(self, _statement):
        self._call += 1
        if self._call == 1:
            # Session lookup: an active session owned by this user.
            return _FakeResult(
                SimpleNamespace(id=SESSION_ID, user_id=USER_ID, state="active")
            )
        # Policy lookup: none configured, so the default policy applies.
        return _FakeResult(None)

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


@contextlib.asynccontextmanager
async def _fake_session_local():
    yield _FakeDB()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(gw, "AsyncSessionLocal", _fake_session_local)
    # Keep the demo brisk so the test does not sleep for half a minute.
    monkeypatch.setattr(gw, "DEMO_INTERVAL_S", 0.0)

    app = FastAPI()
    app.include_router(gw.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def _demo_backends(monkeypatch):
    """
    These tests pin the *demo* event contract and narrative, so they must run
    against the deterministic backends regardless of the ambient PIPELINE_MODE.
    Real-model behaviour is covered by tests/test_ml_*.py.
    """
    from app.ml.authenticity.detector import AuthenticityDetector, HEURISTIC_DEMO
    from app.ml.context.transcriber import Transcriber
    from app.ml.identity.speaker import SpeakerIdentity

    monkeypatch.setattr(gw, "authenticity_detector",
                        AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO), raising=False)
    from app.websocket import pipeline as pl

    monkeypatch.setattr(pl, "authenticity_detector",
                        AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO))
    monkeypatch.setattr(pl, "speaker_identity",
                        SpeakerIdentity(pipeline_mode=HEURISTIC_DEMO))
    monkeypatch.setattr(pl, "transcriber",
                        Transcriber(pipeline_mode=HEURISTIC_DEMO))
    yield


@pytest.fixture(autouse=True)
def _clean_session_state():
    yield
    gw.speaker_identity.clear(SESSION_ID)
    gw.transcriber.reset(SESSION_ID)
    gw.context_classifier.reset(SESSION_ID)
    gw.manager.drop_state(SESSION_ID)


def _token() -> str:
    return create_access_token(USER_ID)


def _drain_demo(ws, expected_updates: int = gw.DEMO_STEPS, limit: int = 400):
    """
    Collect events until the demo has emitted all of its risk updates.

    `receive_json` blocks, so the loop needs a deterministic stop condition: the
    demo runs a known number of windows, each producing one risk update.
    """
    collected = []
    updates = 0
    for _ in range(limit):
        event = ws.receive_json()
        collected.append(event)
        if event["type"] == ev.RISK_UPDATE:
            updates += 1
            if updates >= expected_updates:
                break
        if event["type"] == ev.SESSION_ENDED:
            break
    return collected


# ── Connection ────────────────────────────────────────────────────────────────

def test_authorised_connection_receives_session_started(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        first = ws.receive_json()
        assert first["type"] == ev.SESSION_STARTED
        assert first["session_id"] == SESSION_ID
        assert first["pipeline_mode"] == "mock"
        assert "authenticity" in first["model_versions"]


def test_ping_receives_pong(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == ev.PONG


def test_unknown_message_type_returns_an_error_not_a_disconnect(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "teleport"})
        error = ws.receive_json()
        assert error["type"] == ev.ERROR
        assert error["code"] == "unknown_type"

        # The socket is still usable.
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == ev.PONG


def test_malformed_json_returns_an_error_not_a_disconnect(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        ws.receive_json()
        ws.send_text("{not json")
        error = ws.receive_json()
        assert error["type"] == ev.ERROR
        assert error["code"] == "bad_request"

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == ev.PONG


def test_invalid_base64_audio_is_rejected_without_dropping_the_socket(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_chunk", "data": "!!!not-base64!!!"})
        error = ws.receive_json()
        assert error["type"] == ev.ERROR
        assert error["code"] == "bad_audio"


# ── The full scenario over a real socket ──────────────────────────────────────

def test_demo_scenario_streams_a_complete_dashboard_narrative(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        assert ws.receive_json()["type"] == ev.SESSION_STARTED
        ws.send_json({"type": "start_demo"})
        events = _drain_demo(ws)

    by_type = {}
    for event in events:
        by_type.setdefault(event["type"], []).append(event)

    # Every event type the dashboard needs actually arrived.
    assert ev.RISK_UPDATE in by_type
    assert ev.AUDIO_QUALITY in by_type
    assert ev.DETECTED_EVENT in by_type
    assert ev.ALERT in by_type
    assert ev.POLICY_DECISION in by_type

    updates = by_type[ev.RISK_UPDATE]
    assert len(updates) >= 10

    # ── Risk score and state escalate ────────────────────────────────────────
    scores = [u["risk_score"] for u in updates]
    states = [u["risk_state"] for u in updates]
    assert scores[-1] > scores[0]
    assert states[-1] == "critical"
    assert {"suspicious", "high", "critical"} <= set(states)

    # ── The graph gets a moving series, not a flat line ──────────────────────
    assert len(set(scores)) > 3

    # ── Trend is reported ────────────────────────────────────────────────────
    assert "rising" in [u["risk_trend"] for u in updates]

    # ── All three evidence streams populate and stay separate ────────────────
    final = updates[-1]
    assert final["authenticity"]["spoof_probability"] > 0
    assert final["identity"]["enrollment_status"] != "NOT_ENROLLED"
    assert final["context"]["otp_request"] is True
    assert "otp_request" not in final["authenticity"]
    assert "spoof_probability" not in final["context"]

    # ── Security decision escalates ──────────────────────────────────────────
    decisions = [u["decision"] for u in updates]
    assert decisions[0] == "ALLOW"
    assert "VERIFY" in decisions
    assert decisions[-1] == "HOLD"

    # ── Alerts fire at elevated risk ─────────────────────────────────────────
    severities = {a["severity"] for a in by_type[ev.ALERT]}
    assert {"high", "critical"} <= severities

    # ── Timeline carries the narrative, without repeats ──────────────────────
    labels = [d["label"] for d in by_type[ev.DETECTED_EVENT]]
    assert len(labels) == len(set(labels))
    assert any("OTP" in label for label in labels)

    # ── Mock data is labelled as mock ────────────────────────────────────────
    assert all(u["pipeline_mode"] == "mock" for u in updates)
    assert final["authenticity"]["is_mock"] is True


def test_every_event_carries_the_envelope_and_sequences_monotonically(client):
    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        ws.receive_json()
        ws.send_json({"type": "start_demo"})
        events = _drain_demo(ws)

    assert events

    seqs = []
    ids = set()
    for event in events:
        assert event["type"] in ev.EVENT_TYPES
        for field in ("event_id", "seq", "session_id", "timestamp"):
            assert field in event, (event["type"], field)
        assert event["session_id"] == SESSION_ID
        seqs.append(event["seq"])
        ids.add(event["event_id"])

    # Strictly increasing, and every event id unique — the two properties the
    # client relies on for ordering and de-duplication.
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)
    assert len(ids) == len(events)


def test_real_audio_chunks_run_the_same_pipeline_as_the_demo(client):
    """A client-streamed chunk is analysed identically, but labelled 'live'."""
    import base64

    from app.simulation.mock_audio import generate_frame

    with client.websocket_connect(
        f"/ws/sessions/{SESSION_ID}?token={_token()}"
    ) as ws:
        ws.receive_json()
        payload = base64.b64encode(generate_frame(6, 12)).decode()
        ws.send_json({"type": "audio_chunk", "data": payload})

        updates = []
        for _ in range(12):
            try:
                event = ws.receive_json()
            except Exception:
                break
            if event["type"] == ev.RISK_UPDATE:
                updates.append(event)
                break

    assert updates, "a client audio chunk must produce a risk update"
    assert updates[0]["pipeline_mode"] == "live"
    assert updates[0]["authenticity"] is not None
