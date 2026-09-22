"""
Deterministic Unit Tests for Phase 4.2 VoiceShield VoIP Security Enforcement.

Covers the 14 mandatory test cases:
1. OBSERVE_ONLY + ALLOW
2. OBSERVE_ONLY + BLOCK
3. DRY_RUN + BLOCK
4. ENFORCE + BLOCK
5. duplicate BLOCK
6. ALLOW
7. VERIFY/CHALLENGE
8. HOLD
9. 404 during BLOCK
10. ARI timeout
11. ARI unavailable
12. late event after TERMINATED
13. StasisEnd during TERMINATING
14. invalid enforcement mode defaults to OBSERVE_ONLY
"""

from __future__ import annotations

import asyncio
from typing import List
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from services.telephony.gateway.audio_gateway import (
    ActiveCallSession,
    CallState,
    EnforcementMode,
    TelephonyGateway,
)


@pytest.fixture
def dummy_session() -> ActiveCallSession:
    session = ActiveCallSession(
        caller_channel_id="1790099999.1",
        caller_number="+15550199",
        sip_call_id="call-uuid-12345",
    )
    session.session_id = "session-vs-001"
    session.bridge_id = "bridge-vs-001"
    session.external_channel_id = "ext-vs-001"
    session.state = CallState.ACTIVE
    return session


@pytest.fixture
def recorded_requests():
    return []


def make_gateway(
    mode: EnforcementMode = EnforcementMode.OBSERVE_ONLY,
    response_status: int = 204,
    exception_to_raise: Exception | None = None,
    recorded_list: list | None = None,
) -> TelephonyGateway:
    def handler(request: httpx.Request) -> httpx.Response:
        if exception_to_raise:
            raise exception_to_raise
        if recorded_list is not None:
            recorded_list.append(request)
        return httpx.Response(response_status, text="{}")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8088")
    return TelephonyGateway(
        ari_url="http://localhost:8088/ari",
        enforcement_mode=mode,
        http_client=client,
    )


@pytest.mark.asyncio
async def test_01_observe_only_allow(dummy_session):
    """1. In OBSERVE_ONLY, ALLOW maintains ACTIVE state and performs zero ARI calls."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.OBSERVE_ONLY, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="ALLOW",
        action="allow",
        risk_state="low",
        risk_score=15,
        reasons=[],
    )
    assert dummy_session.state == CallState.ACTIVE
    assert len(reqs) == 0


@pytest.mark.asyncio
async def test_02_observe_only_block(dummy_session):
    """2. In OBSERVE_ONLY, BLOCK transitions internal state to TERMINATING but makes zero ARI calls."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.OBSERVE_ONLY, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=92,
        reasons=["synthetic_voice_detected"],
    )
    assert dummy_session.state == CallState.TERMINATING
    assert dummy_session.enforcement_action_taken == "BLOCK"
    assert len(reqs) == 0
    assert len(dummy_session.ari_actions_log) == 1
    assert dummy_session.ari_actions_log[0]["executed"] is False
    assert dummy_session.ari_actions_log[0]["mode"] == "observe_only"


@pytest.mark.asyncio
async def test_03_dry_run_block(dummy_session):
    """3. In DRY_RUN, BLOCK transitions state to TERMINATING, records the planned ARI action, but executes zero live calls."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.DRY_RUN, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=88,
        reasons=["synthetic_voice_detected"],
    )
    assert dummy_session.state == CallState.TERMINATING
    assert dummy_session.enforcement_action_taken == "BLOCK"
    assert len(reqs) == 0
    assert len(dummy_session.ari_actions_log) == 1
    assert dummy_session.ari_actions_log[0]["executed"] is False
    assert dummy_session.ari_actions_log[0]["mode"] == "dry_run"


@pytest.mark.asyncio
async def test_04_enforce_block(dummy_session):
    """4. In ENFORCE mode, BLOCK executes ARI DELETE against the caller channel."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=204, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=95,
        reasons=["spoof_confirmed"],
    )
    assert dummy_session.state == CallState.TERMINATING
    assert dummy_session.enforcement_action_taken == "BLOCK"
    assert len(reqs) == 1
    assert reqs[0].method == "DELETE"
    assert reqs[0].url.path == f"/ari/channels/{dummy_session.caller_channel_id}"
    assert "reason=congestion" in str(reqs[0].url)
    assert dummy_session.ari_actions_log[0]["executed"] is True
    assert dummy_session.ari_actions_log[0]["status_code"] == 204


@pytest.mark.asyncio
async def test_05_duplicate_block(dummy_session):
    """5. Multiple consecutive BLOCK events execute the ARI DELETE action exactly once (Idempotency)."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=204, recorded_list=reqs)
    for _ in range(5):
        await gateway._handle_policy_verdict(
            session=dummy_session,
            decision="BLOCK",
            action="block",
            risk_state="critical",
            risk_score=90,
            reasons=["duplicate_test"],
        )
    assert len(reqs) == 1
    assert len(dummy_session.ari_actions_log) == 1


@pytest.mark.asyncio
async def test_06_allow_action(dummy_session):
    """6. ALLOW maintains ACTIVE state and unholds channel if coming out of HOLD."""
    reqs = []
    dummy_session.state = CallState.HOLD
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=204, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="ALLOW",
        action="allow",
        risk_state="low",
        risk_score=10,
        reasons=[],
    )
    assert dummy_session.state == CallState.ACTIVE
    assert len(reqs) == 1
    assert reqs[0].method == "DELETE"
    assert reqs[0].url.path == f"/ari/channels/{dummy_session.caller_channel_id}/hold"


@pytest.mark.asyncio
async def test_07_verify_challenge(dummy_session):
    """7. VERIFY/CHALLENGE in ENFORCE mode plays the predefined challenge prompt via ARI."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=200, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=52,
        reasons=["unverified_caller"],
    )
    assert dummy_session.state == CallState.CHALLENGED
    assert dummy_session.enforcement_action_taken == "CHALLENGE"
    assert len(reqs) == 1
    assert reqs[0].method == "POST"
    assert reqs[0].url.path == f"/ari/channels/{dummy_session.caller_channel_id}/play"
    assert "media=sound%3Achallenge_prompt" in str(reqs[0].url) or "media=sound:challenge_prompt" in str(reqs[0].url)
    assert dummy_session.ari_actions_log[0]["executed"] is True


@pytest.mark.asyncio
async def test_08_hold_action(dummy_session):
    """8. HOLD in ENFORCE mode calls POST /channels/{id}/hold."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=204, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="HOLD",
        action="hold",
        risk_state="critical",
        risk_score=86,
        reasons=["high_consequence_unverified"],
    )
    assert dummy_session.state == CallState.HOLD
    assert dummy_session.enforcement_action_taken == "HOLD"
    assert len(reqs) == 1
    assert reqs[0].method == "POST"
    assert reqs[0].url.path == f"/ari/channels/{dummy_session.caller_channel_id}/hold"
    assert dummy_session.ari_actions_log[0]["executed"] is True


@pytest.mark.asyncio
async def test_09_404_during_block(dummy_session):
    """9. ARI 404 on DELETE is treated cleanly as already-terminated without error."""
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=404, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=90,
        reasons=["spoof"],
    )
    assert dummy_session.state == CallState.TERMINATING
    assert len(reqs) == 1
    assert dummy_session.ari_actions_log[0]["status_code"] == 404
    assert dummy_session.ari_actions_log[0]["executed"] is False


@pytest.mark.asyncio
async def test_10_ari_timeout(dummy_session):
    """10. ARI timeout is caught safely without raising an unhandled exception or crashing the gateway."""
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        exception_to_raise=httpx.TimeoutException("ARI connection timed out"),
    )
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=90,
        reasons=["spoof"],
    )
    assert dummy_session.state == CallState.TERMINATING
    assert dummy_session.ari_actions_log[0]["executed"] is False


@pytest.mark.asyncio
async def test_11_ari_unavailable(dummy_session):
    """11. ARI unreachable / connection error is handled gracefully without crash."""
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        exception_to_raise=httpx.ConnectError("Failed to connect to Asterisk on port 8088"),
    )
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=90,
        reasons=["spoof"],
    )
    assert dummy_session.state == CallState.TERMINATING
    assert dummy_session.ari_actions_log[0]["executed"] is False


@pytest.mark.asyncio
async def test_12_late_event_after_terminated(dummy_session):
    """12. Late events arriving after CallState.TERMINATED are ignored immediately with zero ARI actions."""
    reqs = []
    dummy_session.state = CallState.TERMINATED
    dummy_session.is_terminated = True
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="BLOCK",
        action="block",
        risk_state="critical",
        risk_score=99,
        reasons=["late_block"],
    )
    assert len(reqs) == 0
    assert len(dummy_session.ari_actions_log) == 0


@pytest.mark.asyncio
async def test_13_stasis_end_during_terminating(dummy_session):
    """13. StasisEnd arriving while CallState.TERMINATING cleans up resources and transitions to TERMINATED."""
    reqs = []
    dummy_session.state = CallState.TERMINATING
    dummy_session.is_terminating = True
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, response_status=204, recorded_list=reqs)
    gateway.active_session = dummy_session

    await gateway._handle_ari_event({
        "type": "StasisEnd",
        "channel": {"id": dummy_session.caller_channel_id},
    })

    assert dummy_session.state == CallState.TERMINATED
    assert dummy_session.is_terminated is True
    assert gateway.active_session is None
    # Verifies bridge and externalMedia channel deletions were attempted
    del_bridge = any(f"/bridges/{dummy_session.bridge_id}" in str(r.url) for r in reqs)
    del_ext = any(f"/channels/{dummy_session.external_channel_id}" in str(r.url) for r in reqs)
    assert del_bridge is True
    assert del_ext is True


def test_14_invalid_mode_defaults_to_observe_only():
    """14. An invalid or unrecognized enforcement mode safely defaults to OBSERVE_ONLY."""
    assert EnforcementMode.from_str(None) == EnforcementMode.OBSERVE_ONLY
    assert EnforcementMode.from_str("") == EnforcementMode.OBSERVE_ONLY
    assert EnforcementMode.from_str("invalid_mode") == EnforcementMode.OBSERVE_ONLY
    assert EnforcementMode.from_str("RANDOM_TEXT") == EnforcementMode.OBSERVE_ONLY
    assert EnforcementMode.from_str("dry_run") == EnforcementMode.DRY_RUN
    assert EnforcementMode.from_str("ENFORCE") == EnforcementMode.ENFORCE
