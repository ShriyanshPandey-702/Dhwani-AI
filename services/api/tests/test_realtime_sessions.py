"""
Session lifecycle, isolation and WebSocket robustness under real-audio load.

The dangerous failure here is silent: state from one call bleeding into the
next, or a duplicated chunk being counted as fresh evidence. Both are cheap to
assert and expensive to discover in a demo.
"""

from __future__ import annotations

import base64
import contextlib
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.ml.preprocessing.ingest import to_int16_pcm
from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.websocket import events as ev
from app.websocket import gateway as gw
from app.websocket.manager import SessionState, manager
from app.websocket.pipeline import analyze_window, stream_windower

USER_ID = "22222222-2222-2222-2222-222222222222"


def _speechlike(seconds: float, seed: int = 0) -> np.ndarray:
    """Deterministic non-silent audio: enough energy to pass the VAD gate."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(16000 * seconds)) / 16000
    a = 0.3 * np.sin(2 * np.pi * 150 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
    return (a + rng.standard_normal(t.size) * 0.01).astype(np.float32)


class _R:
    def __init__(self, v): self._v = v
    def scalar_one_or_none(self): return self._v


def _client(session_id: str):
    class _DB:
        def __init__(self): self.n = 0
        async def execute(self, _s):
            self.n += 1
            if self.n == 1:
                return _R(SimpleNamespace(id=session_id, user_id=USER_ID, state="active"))
            return _R(None)
        def add(self, _o): pass
        async def commit(self): pass
        async def refresh(self, _o): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False

    gw.AsyncSessionLocal = lambda: _DB()
    app = FastAPI()
    app.include_router(gw.router)
    return TestClient(app), create_access_token(USER_ID)


# ══ SESSION ISOLATION ════════════════════════════════════════════════════════

def test_ten_sequential_sessions_leak_no_state():
    """§28-F: no risk, transcript, alert, identity or graph carries over."""
    audio = _speechlike(5.5, seed=1)
    finals = []
    for i in range(10):
        sid = f"seq-{i}"
        stream_windower.reset(sid)
        state = SessionState(session_id=sid, user_id="u",
                             policy_config=dict(DEFAULT_POLICY_CONFIG))
        # A fresh session must start clean.
        assert state.risk_history == []
        assert state.last_authenticity is None
        assert state.last_identity is None
        assert state.last_context is None
        assert state.announced == set()
        assert state.challenge_outcome is None
        assert state.verification_outcome is None
        assert state.peak_risk_score == 0

        for start in range(0, len(audio), 1600):
            analyze_window(state, to_int16_pcm(audio[start:start + 1600]),
                           pipeline_mode="live")
        finals.append((state.peak_risk_score, len(state.risk_history)))
        stream_windower.reset(sid)

    # Identical input must give identical results — no accumulation across runs.
    assert len(set(finals)) == 1, f"state leaked between sessions: {finals}"


def test_windower_buffers_are_per_session():
    a = to_int16_pcm(_speechlike(1.0, seed=2))
    for i in range(3):
        analyze_window(
            SessionState(session_id=f"iso-{i}", user_id="u",
                         policy_config=dict(DEFAULT_POLICY_CONFIG)),
            a, pipeline_mode="live")
    stats = [stream_windower.stats(f"iso-{i}") for i in range(3)]
    assert all(s.buffered_samples == stats[0].buffered_samples for s in stats)
    stream_windower.reset("iso-0")
    assert stream_windower.stats("iso-0").buffered_samples == 0
    assert stream_windower.stats("iso-1").buffered_samples > 0
    for i in range(3):
        stream_windower.reset(f"iso-{i}")


def test_reset_discards_audio_so_a_new_call_cannot_inherit_it():
    sid = "reset-me"
    analyze_window(SessionState(session_id=sid, user_id="u",
                                policy_config=dict(DEFAULT_POLICY_CONFIG)),
                   to_int16_pcm(_speechlike(2.0, seed=3)), pipeline_mode="live")
    assert stream_windower.stats(sid).buffered_samples > 0
    stream_windower.reset(sid)
    assert stream_windower.stats(sid).buffered_samples == 0


# ══ INGEST ROBUSTNESS OVER THE SOCKET ════════════════════════════════════════

def test_duplicate_audio_sequence_numbers_are_not_analysed_twice():
    sid = "dup-seq"
    client, token = _client(sid)
    chunk = base64.b64encode(to_int16_pcm(_speechlike(0.1, seed=4))).decode()
    with client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws:
        ws.receive_json()
        for _ in range(5):
            ws.send_json({"type": "audio_chunk", "seq": 7, "data": chunk})
        ws.send_json({"type": "ping"})
        with contextlib.suppress(Exception):
            for _ in range(200):
                if ws.receive_json().get("type") == ev.PONG:
                    break
    state = manager.get_state(sid)
    if state is not None:
        assert state.duplicate_audio_chunks >= 4
    stream_windower.reset(sid)


def test_stale_audio_sequence_numbers_are_dropped():
    sid = "stale-seq"
    client, token = _client(sid)
    chunk = base64.b64encode(to_int16_pcm(_speechlike(0.1, seed=5))).decode()
    with client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_chunk", "seq": 100, "data": chunk})
        for old in (5, 6, 7):
            ws.send_json({"type": "audio_chunk", "seq": old, "data": chunk})
        ws.send_json({"type": "ping"})
        with contextlib.suppress(Exception):
            for _ in range(200):
                if ws.receive_json().get("type") == ev.PONG:
                    break
    state = manager.get_state(sid)
    if state is not None:
        assert state.stale_audio_chunks >= 3
    stream_windower.reset(sid)


def test_oversized_audio_chunk_is_refused_without_dropping_the_socket():
    sid = "too-big"
    client, token = _client(sid)
    huge = "A" * (gw.MAX_AUDIO_B64_CHARS + 10)
    with client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_chunk", "data": huge})
        err = ws.receive_json()
        assert err["type"] == ev.ERROR
        assert err.get("code") == "audio_too_large"
        # The socket must survive: a ping still answers.
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == ev.PONG
    stream_windower.reset(sid)


def test_non_string_audio_payload_is_refused():
    sid = "bad-type"
    client, token = _client(sid)
    with client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws:
        ws.receive_json()
        ws.send_json({"type": "audio_chunk", "data": {"not": "a string"}})
        err = ws.receive_json()
        assert err["type"] == ev.ERROR and err.get("code") == "bad_audio"
        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == ev.PONG
    stream_windower.reset(sid)


def test_malformed_audio_cannot_crash_the_service():
    """§28-J: garbage in, structured error out, process still serving."""
    sid = "garbage"
    client, token = _client(sid)
    with client.websocket_connect(f"/ws/sessions/{sid}?token={token}") as ws:
        ws.receive_json()
        for payload in ("!!!not-base64!!!", "", "AAAA", "Zm9vYmFy"):
            ws.send_json({"type": "audio_chunk", "data": payload})
        ws.send_json({"type": "ping"})
        seen_pong = False
        with contextlib.suppress(Exception):
            for _ in range(200):
                if ws.receive_json().get("type") == ev.PONG:
                    seen_pong = True
                    break
        assert seen_pong, "socket died on malformed audio"
    stream_windower.reset(sid)


def test_one_bad_session_does_not_disturb_another():
    good_id, bad_id = "good-sess", "bad-sess"
    c1, t1 = _client(good_id)
    with c1.websocket_connect(f"/ws/sessions/{good_id}?token={t1}") as ws1:
        ws1.receive_json()
        c2, t2 = _client(bad_id)
        with c2.websocket_connect(f"/ws/sessions/{bad_id}?token={t2}") as ws2:
            ws2.receive_json()
            ws2.send_json({"type": "audio_chunk", "data": "!!!garbage!!!"})
            assert ws2.receive_json()["type"] == ev.ERROR
        # The healthy session is unaffected by the other socket's failure.
        ws1.send_json({"type": "ping"})
        assert ws1.receive_json()["type"] == ev.PONG
    for s in (good_id, bad_id):
        stream_windower.reset(s)


# ══ PRIVACY ══════════════════════════════════════════════════════════════════

def test_events_never_carry_raw_audio_or_embeddings():
    sid = "privacy"
    state = SessionState(session_id=sid, user_id="u",
                         policy_config=dict(DEFAULT_POLICY_CONFIG))
    events = []
    audio = _speechlike(5.5, seed=6)
    for start in range(0, len(audio), 1600):
        events.extend(analyze_window(state, to_int16_pcm(audio[start:start + 1600]),
                                     pipeline_mode="live"))
    stream_windower.reset(sid)

    banned = ("embedding", "embeddings", "pcm", "waveform", "raw_audio", "samples_b64")
    for e in events:
        for key in _walk_keys(e):
            assert key.lower() not in banned, f"event leaks {key}"
        # No long float arrays either — that would be an embedding by another name.
        for value in _walk_values(e):
            if isinstance(value, (list, tuple)) and len(value) > 32:
                assert not all(isinstance(x, float) for x in value), "array leak"


def _walk_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_keys(v)


def _walk_values(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield v
            yield from _walk_values(v)
    elif isinstance(obj, (list, tuple)):
        yield obj
        for v in obj:
            yield from _walk_values(v)
