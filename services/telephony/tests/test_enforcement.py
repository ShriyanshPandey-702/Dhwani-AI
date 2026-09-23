"""
Deterministic Unit Tests for Phase 4.2 & Phase 5.1 VoiceShield VoIP Security Enforcement
and Interactive Challenge Hardening.

Covers:
Phase 4.2:
1. OBSERVE_ONLY + ALLOW
2. OBSERVE_ONLY + BLOCK
3. DRY_RUN + BLOCK
4. ENFORCE + BLOCK
5. duplicate BLOCK
6. ALLOW
7. HOLD
8. 404 during BLOCK
9. ARI timeout
10. ARI unavailable
11. late event after TERMINATED
12. StasisEnd during TERMINATING
13. invalid enforcement mode defaults to OBSERVE_ONLY

Phase 5.1 Interactive Challenge Hardening:
14. Challenge creation occurs exactly once and stores challenge_id/text/type
15. Inbound mute occurs before challenge playback starts
16. Playback starts with correct media URI and captures playback_id
17. Matching PlaybackFinished unmutes caller and enters CHALLENGE_LISTENING
18. Stale/mismatched PlaybackFinished is safely ignored
19. Playback watchdog unmuting upon timeout
20. Response window collection and drain delay
21. Matching spoken response evaluates to PASSED and posts result
22. Non-matching/contradictory response evaluates to FAILED and posts result
23. Silence during window evaluates to TIMEOUT and posts result
24. Speech detected without transcription evaluates to FAILED
25. Challenge creation idempotency (duplicate VERIFY dropped)
26. Challenge result submission idempotency
27. Hangup during challenge cleans up tasks and unmutes
28. ARI mute failure resilience
29. ARI playback failure resilience and defensive unmute
30. Backend challenge creation failure resilience
31. Backend result submission failure resilience
32. Deterministic dynamic phrase/sequence/question evaluation matrix

Phase 5.2 Failure & Watchdog Hardening:
35. RTP inactivity watchdog hangs up caller channel with reason="normal"
36. RTP inactivity watchdog refreshed continuously by incoming RTP packets
37. ARI WebSocket disconnect cleans active session locally
38. Backend session setup failure hangs up caller with reason="congestion"
39. Backend WebSocket disconnect triggers controlled fail-safe teardown
40. ML analysis_error counter and reset on valid risk_update
41. Consecutive ML analysis_error threshold triggers controlled fail-safe teardown
42. Startup reconciliation only reaps owned VoiceShield bridges and channels
43. Normal SIP BYE during/around watchdog handling is idempotent
44. Real Asterisk HOLD followed by ALLOW/unhold
"""

from __future__ import annotations

import asyncio
import json
from typing import List, Optional
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import websockets

from services.telephony.gateway.audio_gateway import (
    ActiveCallSession,
    CallState,
    EnforcementMode,
    TelephonyGateway,
    evaluate_challenge_response,
    extract_challenge_target,
    normalize_challenge_text,
    resolve_challenge_prompt_sound,
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


def make_gateway(
    mode: EnforcementMode = EnforcementMode.OBSERVE_ONLY,
    response_status: int = 200,
    exception_to_raise: Exception | None = None,
    backend_exception: Exception | None = None,
    recorded_list: list | None = None,
    challenge_payload: dict | None = None,
    listening_window_duration: float = 0.05,
    playback_watchdog_timeout: float = 0.1,
    rtp_inactivity_timeout: float = 5.0,
    max_consecutive_analysis_errors: int = 3,
) -> TelephonyGateway:
    if challenge_payload is None:
        challenge_payload = {
            "id": "chal-test-12345",
            "session_id": "session-vs-001",
            "challenge_text": "Please say: 'The security of this call matters.'",
            "challenge_type": "phrase",
            "state": "pending",
        }

    def ari_handler(request: httpx.Request) -> httpx.Response:
        if exception_to_raise:
            raise exception_to_raise
        if recorded_list is not None:
            recorded_list.append(request)
        if "/play" in str(request.url) and request.method == "POST":
            return httpx.Response(201, json={"id": "pb-test-999", "state": "queued"})
        if response_status == 204:
            return httpx.Response(204)
        return httpx.Response(response_status, json={})

    def backend_handler(request: httpx.Request) -> httpx.Response:
        if backend_exception:
            raise backend_exception
        if recorded_list is not None:
            recorded_list.append(request)
        url_str = str(request.url)
        if "/challenge/" in url_str:
            if url_str.endswith("/result"):
                return httpx.Response(200, json={"state": "passed", **challenge_payload})
            return httpx.Response(201, json=challenge_payload)
        return httpx.Response(200, json={})

    ari_transport = httpx.MockTransport(ari_handler)
    backend_transport = httpx.MockTransport(backend_handler)

    ari_client = httpx.AsyncClient(transport=ari_transport, base_url="http://localhost:8088")
    backend_client = httpx.AsyncClient(transport=backend_transport, base_url="http://localhost:8000")

    return TelephonyGateway(
        ari_url="http://localhost:8088/ari",
        backend_http_url="http://localhost:8000",
        enforcement_mode=mode,
        http_client=ari_client,
        backend_http_client=backend_client,
        listening_window_duration=listening_window_duration,
        playback_watchdog_timeout=playback_watchdog_timeout,
        rtp_inactivity_timeout=rtp_inactivity_timeout,
        max_consecutive_analysis_errors=max_consecutive_analysis_errors,
    )


# ── Phase 4.2 Baseline Enforcement Tests ─────────────────────────────────────


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
    """3. In DRY_RUN, BLOCK transitions state to TERMINATING, records action, zero live calls."""
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
    """5. Multiple consecutive BLOCK events execute ARI DELETE exactly once (Idempotency)."""
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
    """10. ARI timeout is caught safely without crashing the gateway."""
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
    """11. ARI unreachable / connection error is handled gracefully."""
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
    """12. Late events arriving after CallState.TERMINATED are ignored immediately."""
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


# ── Phase 5.1 Interactive Challenge Hardening Unit Tests ─────────────────────


@pytest.mark.asyncio
async def test_15_challenge_creation_and_mute_before_play(dummy_session):
    """
    Requirements 3, 4, 5:
    A. Receive VERIFY event.
    B. Create exactly one backend Challenge.
    C. Store challenge_id, challenge_text, challenge_type.
    D. Inbound mute occurs BEFORE playback starts.
    E. Start playback and store playback_id.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=["interactive_challenge_required"],
    )

    # 1. State must be CHALLENGE_PLAYING
    assert dummy_session.state == CallState.CHALLENGE_PLAYING
    # 2. Challenge metadata stored in session
    assert dummy_session.challenge_id == "chal-test-12345"
    assert dummy_session.challenge_text == "Please say: 'The security of this call matters.'"
    assert dummy_session.challenge_type == "phrase"
    assert dummy_session.challenge_playback_id == "pb-test-999"
    assert dummy_session.is_caller_muted is True
    assert dummy_session.challenge_watchdog_task is not None

    # 3. Check sequence of HTTP requests:
    # req 0: POST /challenge/session-vs-001 (Backend challenge creation)
    # req 1: POST /ari/channels/.../mute?direction=in (Inbound mute)
    # req 2: POST /ari/channels/.../play?media=sound:challenge_prompt (Playback)
    assert len(reqs) == 3
    assert reqs[0].method == "POST"
    assert reqs[0].url.path == f"/challenge/{dummy_session.session_id}"

    assert reqs[1].method == "POST"
    assert reqs[1].url.path == f"/ari/channels/{dummy_session.caller_channel_id}/mute"
    assert "direction=in" in str(reqs[1].url)

    assert reqs[2].method == "POST"
    assert reqs[2].url.path == f"/ari/channels/{dummy_session.caller_channel_id}/play"
    assert "media=sound" in str(reqs[2].url)

    # Teardown background tasks
    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_16_playback_finished_unmutes_and_starts_listening(dummy_session):
    """
    Requirements 5, 6, 7:
    Matching PlaybackFinished cancels watchdog, unbinds playback_id,
    unmutes caller, and enters CHALLENGE_LISTENING.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.active_session = dummy_session

    # Step 1: Initiate challenge
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=["interactive_challenge_required"],
    )
    assert dummy_session.state == CallState.CHALLENGE_PLAYING
    assert dummy_session.is_caller_muted is True
    playback_id = dummy_session.challenge_playback_id

    # Step 2: Receive matching PlaybackFinished event
    await gateway._handle_ari_event({
        "type": "PlaybackFinished",
        "playback": {"id": playback_id},
    })

    # Assert caller is unmuted and state is CHALLENGE_LISTENING
    assert dummy_session.is_caller_muted is False
    assert dummy_session.state == CallState.CHALLENGE_LISTENING
    assert dummy_session.challenge_playback_id is None
    assert dummy_session.challenge_listening_active is True
    assert dummy_session.challenge_window_task is not None

    # Verify DELETE /mute?direction=in was called
    unmute_req = next((r for r in reqs if r.method == "DELETE" and "mute" in r.url.path), None)
    assert unmute_req is not None
    assert "direction=in" in str(unmute_req.url)

    # Teardown
    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_17_stale_playback_finished_ignored(dummy_session):
    """
    Requirement 6:
    A late or stale PlaybackFinished for an unknown/stale playback_id is ignored.
    Caller is NOT unmuted and state does not advance prematurely.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )
    assert dummy_session.state == CallState.CHALLENGE_PLAYING

    # Stale PlaybackFinished with unknown id
    await gateway._handle_ari_event({
        "type": "PlaybackFinished",
        "playback": {"id": "stale-old-playback-id"},
    })

    # Must remain in CHALLENGE_PLAYING and caller remains muted
    assert dummy_session.state == CallState.CHALLENGE_PLAYING
    assert dummy_session.is_caller_muted is True

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_18_playback_watchdog_unmutes_and_timeouts(dummy_session):
    """
    Requirement 6:
    Arm a watchdog after playback starts. If PlaybackFinished is not received:
    - unmute caller
    - do not leave caller permanently muted
    - log timeout and transition to CHALLENGE_TIMEOUT
    """
    reqs = []
    # Short watchdog timeout (50ms) for test
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        playback_watchdog_timeout=0.05,
    )
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )
    assert dummy_session.state == CallState.CHALLENGE_PLAYING
    assert dummy_session.is_caller_muted is True

    # Allow watchdog timer to fire
    await asyncio.sleep(0.08)

    # Caller must be unmuted and state transitioned to CHALLENGE_TIMEOUT
    assert dummy_session.is_caller_muted is False
    assert dummy_session.state == CallState.CHALLENGE_TIMEOUT

    # Result submitted as 'timeout'
    result_req = next((r for r in reqs if "/result" in str(r.url)), None)
    assert result_req is not None
    payload = json.loads(result_req.content.decode("utf-8"))
    assert payload["outcome"] == "timeout"

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_19_challenge_matching_response_passes(dummy_session):
    """
    Requirements 7, 8, 9:
    Speech detected + transcript satisfies issued challenge_text ->
    State transitions to CHALLENGE_PASSED -> Submits POST result with outcome='passed'.
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        listening_window_duration=0.05,
    )
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    # PlaybackFinished -> CHALLENGE_LISTENING
    await gateway._handle_ari_event({
        "type": "PlaybackFinished",
        "playback": {"id": dummy_session.challenge_playback_id},
    })
    assert dummy_session.state == CallState.CHALLENGE_LISTENING

    # Simulate caller speaking matching response during listening window
    dummy_session.challenge_speech_detected = True
    dummy_session.challenge_transcripts.append("The security of this call matters.")

    # Wait for listening window (0.05s) + drain delay (0.05s) to complete
    await asyncio.sleep(0.12)

    assert dummy_session.state == CallState.CHALLENGE_PASSED
    result_req = next((r for r in reqs if "/result" in str(r.url)), None)
    assert result_req is not None
    body = json.loads(result_req.content.decode("utf-8"))
    assert body["outcome"] == "passed"
    assert "matched" in body["detail"].lower() or "satisfied" in body["detail"].lower()

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_20_challenge_wrong_response_fails(dummy_session):
    """
    Requirements 8, 9:
    Speech detected + non-matching transcript ->
    State transitions to CHALLENGE_FAILED -> Submits POST result with outcome='failed'.
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        listening_window_duration=0.05,
    )
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    await gateway._handle_ari_event({
        "type": "PlaybackFinished",
        "playback": {"id": dummy_session.challenge_playback_id},
    })

    # Non-matching caller response
    dummy_session.challenge_speech_detected = True
    dummy_session.challenge_transcripts.append("I am ordering a hamburger with fries.")

    await asyncio.sleep(0.12)

    assert dummy_session.state == CallState.CHALLENGE_FAILED
    result_req = next((r for r in reqs if "/result" in str(r.url)), None)
    assert result_req is not None
    body = json.loads(result_req.content.decode("utf-8"))
    assert body["outcome"] == "failed"

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_21_challenge_silence_timeouts(dummy_session):
    """
    Requirements 8, 9:
    No speech detected during response window ->
    State transitions to CHALLENGE_TIMEOUT -> Submits POST result with outcome='timeout'.
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        listening_window_duration=0.05,
    )
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    await gateway._handle_ari_event({
        "type": "PlaybackFinished",
        "playback": {"id": dummy_session.challenge_playback_id},
    })

    # Silence: speech_detected is False, no transcripts
    assert dummy_session.challenge_speech_detected is False

    await asyncio.sleep(0.12)

    assert dummy_session.state == CallState.CHALLENGE_TIMEOUT
    result_req = next((r for r in reqs if "/result" in str(r.url)), None)
    assert result_req is not None
    body = json.loads(result_req.content.decode("utf-8"))
    assert body["outcome"] == "timeout"

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_22_challenge_speech_without_transcript_fails(dummy_session):
    """
    Requirement 8:
    If speech exists but transcription is unavailable / empty, classify deterministically
    as failed according to the contract.
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        listening_window_duration=0.05,
    )
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    await gateway._handle_ari_event({
        "type": "PlaybackFinished",
        "playback": {"id": dummy_session.challenge_playback_id},
    })

    # Speech detected (e.g. noise or unparsed audio) but transcript is empty
    dummy_session.challenge_speech_detected = True
    dummy_session.challenge_transcripts = []

    await asyncio.sleep(0.12)

    assert dummy_session.state == CallState.CHALLENGE_FAILED
    result_req = next((r for r in reqs if "/result" in str(r.url)), None)
    assert result_req is not None
    body = json.loads(result_req.content.decode("utf-8"))
    assert body["outcome"] == "failed"
    assert "transcription was unavailable" in body["detail"]

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_23_challenge_creation_idempotency(dummy_session):
    """
    Requirement 4:
    A single active challenge may exist per call/session.
    Duplicate VERIFY/CHALLENGE events while in progress are ignored and do NOT
    create a second backend Challenge record.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.active_session = dummy_session

    # Send 5 consecutive VERIFY events
    for _ in range(5):
        await gateway._handle_policy_verdict(
            session=dummy_session,
            decision="VERIFY",
            action="challenge",
            risk_state="suspicious",
            risk_score=55,
            reasons=[],
        )

    # Exactly one backend challenge creation request and one ARI play request
    backend_chal_reqs = [r for r in reqs if r.method == "POST" and f"/challenge/{dummy_session.session_id}" == r.url.path]
    ari_play_reqs = [r for r in reqs if r.method == "POST" and "/play" in r.url.path]
    assert len(backend_chal_reqs) == 1
    assert len(ari_play_reqs) == 1

    await gateway._teardown_session(dummy_session)


@pytest.mark.asyncio
async def test_24_duplicate_result_submission_prevented(dummy_session):
    """
    Requirement 9:
    POST /challenge/{session_id}/{challenge_id}/result is protected with an
    idempotency flag so duplicate timers or events cannot submit twice.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    dummy_session.challenge_id = "chal-12345"
    dummy_session.challenge_result_submitted = False

    # Submit outcome 3 times
    for _ in range(3):
        await gateway._submit_challenge_result(dummy_session, outcome="passed", detail="test passed")

    result_reqs = [r for r in reqs if "/result" in str(r.url)]
    assert len(result_reqs) == 1


@pytest.mark.asyncio
async def test_25_hangup_during_challenge_cleans_up_and_unmutes(dummy_session):
    """
    Requirement 11:
    Caller hangs up during playback/challenge.
    Tasks are cancelled, playback stopped, caller unmuted, state reaches TERMINATED.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )
    assert dummy_session.state == CallState.CHALLENGE_PLAYING
    assert dummy_session.is_caller_muted is True

    # StasisEnd arrives
    await gateway._handle_ari_event({
        "type": "StasisEnd",
        "channel": {"id": dummy_session.caller_channel_id},
    })

    assert dummy_session.state == CallState.TERMINATED
    assert dummy_session.is_terminated is True
    assert dummy_session.is_caller_muted is False
    assert dummy_session.challenge_playback_id is None
    assert gateway.active_session is None


@pytest.mark.asyncio
async def test_26_ari_mute_failure_resilience(dummy_session):
    """
    Requirement 11:
    ARI mute returns failure (e.g. 500 error). Gateway reverts state safely to ACTIVE
    and does not start playback.
    """
    reqs = []
    def fail_mute(request: httpx.Request) -> httpx.Response:
        reqs.append(request)
        if "/mute" in str(request.url):
            return httpx.Response(500, text="Internal Asterisk Mute Error")
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(fail_mute)
    ari_client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8088")
    gateway = make_gateway(mode=EnforcementMode.ENFORCE)
    gateway.http_client = ari_client

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    # Must revert to ACTIVE safely
    assert dummy_session.state == CallState.ACTIVE
    assert dummy_session.is_caller_muted is False
    # No play request issued
    assert not any("/play" in str(r.url) for r in reqs)


@pytest.mark.asyncio
async def test_27_ari_playback_failure_unmutes_and_recovers(dummy_session):
    """
    Requirement 11:
    ARI play returns 404 or 500. Gateway unbinds and unmutes caller, returning to ACTIVE.
    """
    reqs = []
    def fail_play(request: httpx.Request) -> httpx.Response:
        reqs.append(request)
        if "/play" in str(request.url):
            return httpx.Response(404, text="Channel not found")
        return httpx.Response(200, json={})

    transport = httpx.MockTransport(fail_play)
    ari_client = httpx.AsyncClient(transport=transport, base_url="http://localhost:8088")
    gateway = make_gateway(mode=EnforcementMode.ENFORCE)
    gateway.http_client = ari_client

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    # Must revert to ACTIVE and caller must NOT be left muted
    assert dummy_session.state == CallState.ACTIVE
    assert dummy_session.is_caller_muted is False


@pytest.mark.asyncio
async def test_28_backend_challenge_creation_failure_resilience(dummy_session):
    """
    Requirement 11:
    Backend challenge creation fails with 500 error.
    Gateway handles error safely, reverts state to ACTIVE, zero ARI mute or play performed.
    """
    reqs = []
    def fail_backend(request: httpx.Request) -> httpx.Response:
        reqs.append(request)
        return httpx.Response(500, text="Database Unavailable")

    backend_transport = httpx.MockTransport(fail_backend)
    backend_client = httpx.AsyncClient(transport=backend_transport, base_url="http://localhost:8000")
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.backend_http_client = backend_client

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    assert dummy_session.state == CallState.ACTIVE
    assert dummy_session.challenge_id is None
    assert dummy_session.is_caller_muted is False


@pytest.mark.asyncio
async def test_29_backend_result_failure_resilience(dummy_session):
    """
    Requirement 11:
    Backend result submission fails (e.g. timeout or 500).
    Gateway catches error gracefully without raising unhandled exception.
    """
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        backend_exception=httpx.ConnectError("Backend unreachable"),
    )
    dummy_session.challenge_id = "chal-12345"

    # Should not raise an exception
    await gateway._submit_challenge_result(dummy_session, outcome="passed", detail="test")
    assert dummy_session.challenge_result_submitted is True


def test_30_deterministic_challenge_evaluation_matrix():
    """
    Requirements 1, 8:
    Verify dynamic phrase extraction, normalization (case, whitespace, punctuation),
    token overlap, number sequence, open question, speech without transcript, and silence.
    """
    # 1. Exact quoted phrase
    chal = "Please say: 'The security of this call matters.'"
    res, _ = evaluate_challenge_response(chal, "phrase", "the security of this call matters", True)
    assert res == "passed"

    # 2. Quoted phrase with punctuation & case differences
    res, _ = evaluate_challenge_response(chal, "phrase", "THE SECURITY OF THIS CALL MATTERS!", True)
    assert res == "passed"

    # 3. Partial transcript with >= 50% key token overlap ("security", "call", "matters")
    res, _ = evaluate_challenge_response(chal, "phrase", "voice verification, security of this call matters", True)
    assert res == "passed"

    # 4. Completely unrelated phrase -> failed
    res, _ = evaluate_challenge_response(chal, "phrase", "I am going to the supermarket", True)
    assert res == "failed"

    # 5. Silence -> timeout
    res, _ = evaluate_challenge_response(chal, "phrase", "", False)
    assert res == "timeout"

    # 6. Speech detected but transcript empty -> failed
    res, _ = evaluate_challenge_response(chal, "phrase", "", True)
    assert res == "failed"

    # 7. Sequence challenge ("Count from 1 to 5 slowly.")
    seq_chal = "Count from 1 to 5 slowly."
    res, _ = evaluate_challenge_response(seq_chal, "sequence", "one two three four five", True)
    assert res == "passed"

    res, _ = evaluate_challenge_response(seq_chal, "sequence", "1 2 3", True)
    assert res == "passed"

    res, _ = evaluate_challenge_response(seq_chal, "sequence", "apple orange banana", True)
    assert res == "failed"

    # 8. Open question ("Which city did you register from?")
    q_chal = "Which city did you register from?"
    res, _ = evaluate_challenge_response(q_chal, "question", "Chicago", True)
    assert res == "passed"

    res, _ = evaluate_challenge_response(q_chal, "question", "no cancel", True)
    assert res == "failed"

    # 9. Dynamic custom phrase issued by backend
    dyn_chal = "Please repeat: 'blue horizon seven alpha'"
    res, _ = evaluate_challenge_response(dyn_chal, "phrase", "blue horizon seven alpha", True)
    assert res == "passed"

    res, _ = evaluate_challenge_response(dyn_chal, "phrase", "red apple", True)
    assert res == "failed"


def test_31_prompt_selection_for_all_supported_backend_challenges():
    """
    Requirement 2:
    The gateway must resolve the exact matching prompt audio asset for every
    supported challenge in the backend CHALLENGE_POOL (services/api/app/api/challenge.py).
    """
    backend_pool = [
        ("phrase", "Please say: 'The security of this call matters.'", "sound:challenge_phrase_security"),
        ("phrase", "Please say your full name clearly.", "sound:challenge_phrase_name"),
        ("question", "What are the last 4 digits of your registered mobile number?", "sound:challenge_question_digits"),
        ("question", "Which city did you register from?", "sound:challenge_question_city"),
        ("sequence", "Count from 1 to 5 slowly.", "sound:challenge_sequence"),
        ("phrase", "Please say: 'I authorize this transaction.'", "sound:challenge_phrase_authorize"),
        ("phrase", "Repeat after me: 'VoiceShield verification active.'", "sound:challenge_phrase_active"),
        ("question", "What is today's date?", "sound:challenge_question_date"),
    ]

    for ctype, ctext, expected_sound in backend_pool:
        resolved = resolve_challenge_prompt_sound(ctext, ctype)
        assert resolved == expected_sound, f"Failed mapping [{ctype}] '{ctext}': expected {expected_sound}, got {resolved}"

    # Verify unmapped prompt returns None
    assert resolve_challenge_prompt_sound("What is your mother's maiden name?", "question") is None
    assert resolve_challenge_prompt_sound("", "phrase") is None


@pytest.mark.asyncio
async def test_32_unsupported_unmapped_challenge_fails_safely_without_playing_prompt(dummy_session):
    """
    Requirement 2 & 3:
    When backend issues an unmapped/unsupported challenge, the gateway fails safely:
    - Does NOT mute caller channel
    - Does NOT send ARI play request
    - Submits outcome='failed' with descriptive detail to backend
    - Reverts session state safely to ACTIVE
    """
    reqs = []
    unsupported_payload = {
        "id": "chal-unsupported-999",
        "session_id": "session-vs-001",
        "challenge_text": "Please provide your cryptographic private key.",
        "challenge_type": "custom_unsupported",
        "state": "pending",
    }
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        challenge_payload=unsupported_payload,
    )
    gateway.active_session = dummy_session

    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="VERIFY",
        action="challenge",
        risk_state="suspicious",
        risk_score=55,
        reasons=[],
    )

    # Caller must NOT have been muted
    assert dummy_session.is_caller_muted is False
    # No ARI mute request was sent
    assert not any("/mute" in str(r.url) for r in reqs)
    # No ARI play request was sent
    assert not any("/play" in str(r.url) for r in reqs)
    # State reverts safely to ACTIVE
    assert dummy_session.state == CallState.ACTIVE

    # Failed result submitted to backend with clear detail
    result_reqs = [r for r in reqs if "/result" in str(r.url) and r.method == "POST"]
    assert len(result_reqs) == 1
    res_body = json.loads(result_reqs[0].content.decode("utf-8"))
    assert res_body["outcome"] == "failed"
    assert "Unsupported challenge prompt" in res_body["detail"]


@pytest.mark.asyncio
async def test_33_strict_5s_cutoff_post_cutoff_speech_cannot_change_timeout(dummy_session):
    """
    Requirement 1 & 3:
    Caller is silent during the 0.0-5.0s window.
    At 5.0s, the strict cutoff is reached: challenge_listening_active is False, challenge_drain_active is True.
    Speech arriving after 5.0s (during the 1.2s drain):
    - Is buffered in challenge_buffered_chunks (not sent to backend during drain)
    - VAD audio_quality events received after cutoff CANNOT set speech_detected
    - At 6.2s evaluation, snapshot is frozen with speech_detected=False
    - Outcome is TIMEOUT, proving post-cutoff speech cannot alter the result
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        listening_window_duration=0.1,  # Fast window for test
    )
    gateway.active_session = dummy_session
    dummy_session.ws = AsyncMock()
    dummy_session.ws.closed = False

    # Simulate entering CHALLENGE_LISTENING
    dummy_session.state = CallState.CHALLENGE_LISTENING
    dummy_session.challenge_id = "chal-test-cutoff"
    dummy_session.challenge_text = "Please say: 'The security of this call matters.'"
    dummy_session.challenge_type = "phrase"
    dummy_session.challenge_speech_detected = False
    dummy_session.challenge_transcripts = []
    dummy_session.challenge_listening_active = True
    dummy_session.challenge_drain_active = False

    # Start the listening window task
    window_task = asyncio.create_task(gateway._run_challenge_listening_window(dummy_session))

    # Wait for the active window to expire (0.1s)
    await asyncio.sleep(0.12)
    assert dummy_session.challenge_listening_active is False
    assert dummy_session.challenge_drain_active is True

    # Now simulate speech arriving AFTER the 5.0s cutoff (during the drain)
    # 1. Post-cutoff RTP packet arrives
    fake_rtp = b"\x80\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00" + (b"\x10\x00" * 4000)
    gateway.on_rtp_datagram(fake_rtp, ("127.0.0.1", 10000))
    # Audio must be buffered, not sent to WS during drain
    assert len(dummy_session.challenge_buffered_chunks) > 0

    # 2. Even if a VAD audio_quality event arrives after cutoff, it is rejected by gateway
    vad_event = json.dumps({
        "type": "audio_quality",
        "active": True,
        "audio": {"is_silent": False, "quality": "GOOD"},
    })
    # Run a single iteration of message handling
    async def mock_iter(*args):
        yield vad_event
    dummy_session.ws.__aiter__ = mock_iter
    listener_task = asyncio.create_task(gateway._listen_voiceshield_ws(dummy_session))
    await asyncio.sleep(0.02)
    listener_task.cancel()

    # Crucial assertion: speech_detected MUST still be False
    assert dummy_session.challenge_speech_detected is False

    # Let the drain complete (min(1.2, 0.1) = 0.1s)
    await window_task

    # Outcome must be strictly TIMEOUT
    assert dummy_session.state == CallState.CHALLENGE_TIMEOUT
    result_reqs = [r for r in reqs if "/result" in str(r.url)]
    assert len(result_reqs) == 1
    res_body = json.loads(result_reqs[0].content.decode("utf-8"))
    assert res_body["outcome"] == "timeout"


@pytest.mark.asyncio
async def test_34_strict_5s_cutoff_post_cutoff_speech_cannot_change_failed(dummy_session):
    """
    Requirement 1 & 3:
    Caller speaks invalid/wrong content during 0.0-5.0s window:
    - speech_detected = True
    - transcript = "hello who is this"
    At 5.0s, cutoff occurs.
    During the drain, caller attempts to say the matching phrase:
    - New audio is buffered, not admitted to backend
    - Snapshot evaluated at 6.2s remains strictly the frozen 0.0-5.0s evidence
    - Outcome is FAILED, proving post-cutoff matching words cannot convert failed to passed
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        listening_window_duration=0.1,
    )
    gateway.active_session = dummy_session
    dummy_session.ws = AsyncMock()
    dummy_session.ws.closed = False

    dummy_session.state = CallState.CHALLENGE_LISTENING
    dummy_session.challenge_id = "chal-test-failed"
    dummy_session.challenge_text = "Please say: 'The security of this call matters.'"
    dummy_session.challenge_type = "phrase"
    # Pre-cutoff wrong speech admitted
    dummy_session.challenge_speech_detected = True
    dummy_session.challenge_transcripts = ["hello who is this"]
    dummy_session.challenge_listening_active = True
    dummy_session.challenge_drain_active = False

    window_task = asyncio.create_task(gateway._run_challenge_listening_window(dummy_session))
    await asyncio.sleep(0.12)
    assert dummy_session.challenge_listening_active is False
    assert dummy_session.challenge_drain_active is True

    # Post-cutoff caller speaks matching words over RTP
    fake_rtp = b"\x80\x00\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00" + (b"\x10\x00" * 4000)
    gateway.on_rtp_datagram(fake_rtp, ("127.0.0.1", 10000))
    assert len(dummy_session.challenge_buffered_chunks) > 0

    await window_task

    # Must be strictly FAILED
    assert dummy_session.state == CallState.CHALLENGE_FAILED
    result_reqs = [r for r in reqs if "/result" in str(r.url)]
    assert len(result_reqs) == 1
    res_body = json.loads(result_reqs[0].content.decode("utf-8"))
    assert res_body["outcome"] == "failed"


# ── Phase 5.2 Failure & Watchdog Hardening Tests ─────────────────────────────


@pytest.mark.asyncio
async def test_35_rtp_inactivity_watchdog_hangs_up_caller_channel(dummy_session):
    """
    Scenario F1: Watchdog tracks absence of RTP packets only (not silence).
    When no RTP arrives within rtp_inactivity_timeout:
    - Initiates controlled teardown.
    - Hangs up caller channel with reason="normal".
    - Session transitions to TERMINATED.
    - No false security verdict generated.
    """
    import time
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        rtp_inactivity_timeout=0.05,
    )
    gateway.active_session = dummy_session
    dummy_session.last_rtp_received_at = time.monotonic() - 0.1  # Already expired

    await gateway._rtp_inactivity_watchdog(dummy_session)

    assert dummy_session.is_terminated is True
    assert dummy_session.state == CallState.TERMINATED
    assert dummy_session.enforcement_action_taken is None  # NOT a security policy verdict
    # Verify hangup request sent to ARI
    hangup_reqs = [r for r in reqs if f"/channels/{dummy_session.caller_channel_id}" in str(r.url) and r.method == "DELETE"]
    assert len(hangup_reqs) == 1
    assert "reason=normal" in str(hangup_reqs[0].url)


@pytest.mark.asyncio
async def test_36_rtp_inactivity_watchdog_refreshed_by_rtp_packets(dummy_session):
    """
    Scenario F1 negative case: Watchdog is continuously refreshed by incoming RTP packets.
    As long as RTP packets arrive within the timeout window:
    - Session remains active.
    - Caller channel is NOT terminated.
    """
    import time
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        rtp_inactivity_timeout=0.15,
    )
    gateway.active_session = dummy_session
    dummy_session.last_rtp_received_at = time.monotonic()

    # Start watchdog
    watchdog_task = asyncio.create_task(gateway._rtp_inactivity_watchdog(dummy_session))

    # Send RTP packets every 0.03s for 0.15s (total 5 packets)
    fake_rtp = b"\x80\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00" + (b"\x10\x00" * 160)
    for _ in range(5):
        await asyncio.sleep(0.03)
        gateway.on_rtp_datagram(fake_rtp, ("127.0.0.1", 20000))

    assert dummy_session.is_terminated is False
    assert dummy_session.state == CallState.ACTIVE
    watchdog_task.cancel()
    try:
        await watchdog_task
    except asyncio.CancelledError:
        pass
    assert not any(r.method == "DELETE" and f"/channels/{dummy_session.caller_channel_id}" in str(r.url) for r in reqs)


@pytest.mark.asyncio
async def test_37_ari_disconnect_cleans_active_session_locally(dummy_session):
    """
    Scenario F2/F3: Asterisk stops or restarts during active call.
    When ARI connection is lost:
    - Session is torn down locally without leaking ghost state.
    - gateway.active_session is cleared to None.
    """
    gateway = make_gateway(mode=EnforcementMode.ENFORCE)
    gateway.active_session = dummy_session

    with patch("websockets.connect", side_effect=websockets.ConnectionClosed(None, None)):
        gateway.running = True
        loop_task = asyncio.create_task(gateway._run_ari_event_loop())
        await asyncio.sleep(0.02)
        gateway.running = False
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

    assert dummy_session.is_terminated is True
    assert gateway.active_session is None


@pytest.mark.asyncio
async def test_38_backend_setup_failure_hangs_up_caller_with_congestion(dummy_session):
    """
    Scenario F6 (pre-call): Backend is down or fails during session setup.
    - Hangs up caller channel with reason="congestion".
    - Session cleaned up.
    - gateway.active_session is cleared.
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        backend_exception=httpx.ConnectError("Connection refused"),
    )
    gateway.active_session = dummy_session

    await gateway._setup_call_and_streaming(dummy_session)

    assert dummy_session.is_terminated is True
    assert gateway.active_session is None
    hangup_reqs = [r for r in reqs if f"/channels/{dummy_session.caller_channel_id}" in str(r.url) and r.method == "DELETE"]
    assert len(hangup_reqs) == 1
    assert "reason=congestion" in str(hangup_reqs[0].url)


@pytest.mark.asyncio
async def test_39_backend_ws_disconnect_triggers_fail_safe_teardown(dummy_session):
    """
    Scenario F6 (mid-call): Backend WebSocket is lost during active call.
    Mandatory correction:
    - Do NOT add reconnect yet.
    - Controlled teardown: close session, clean resources, hang up caller channel with reason="congestion".
    - Do not leave an unmonitored active call.
    - Do not emit false security verdict.
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
    )
    gateway.active_session = dummy_session

    class FailingWs:
        def __aiter__(self):
            return self
        async def __anext__(self):
            raise websockets.ConnectionClosed(None, None)

    dummy_session.ws = FailingWs()

    await gateway._listen_voiceshield_ws(dummy_session)

    assert dummy_session.is_terminated is True
    assert dummy_session.state == CallState.TERMINATED
    assert dummy_session.enforcement_action_taken is None  # NO fake security verdict
    hangup_reqs = [r for r in reqs if f"/channels/{dummy_session.caller_channel_id}" in str(r.url) and r.method == "DELETE"]
    assert len(hangup_reqs) == 1
    assert "reason=congestion" in str(hangup_reqs[0].url)


@pytest.mark.asyncio
async def test_40_ml_analysis_error_counter_and_reset(dummy_session):
    """
    Scenario F7: Observe and count analysis_error events.
    - Transient errors increment consecutive counter.
    - Valid risk_update resets counter to 0.
    - Call remains active, no false alert or verdict.
    """
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, max_consecutive_analysis_errors=3)
    gateway.active_session = dummy_session

    events = [
        json.dumps({"type": "error", "code": "analysis_error", "message": "Inference timeout window 1"}),
        json.dumps({"type": "error", "code": "analysis_error", "message": "Inference timeout window 2"}),
        json.dumps({"type": "risk_update", "risk_score": 12, "risk_state": "low", "decision": "ALLOW"}),
    ]

    class MockWs:
        def __init__(self, evs):
            self.evs = list(evs)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.evs:
                return self.evs.pop(0)
            raise asyncio.CancelledError()

    dummy_session.ws = MockWs(events)

    task = asyncio.create_task(gateway._listen_voiceshield_ws(dummy_session))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert dummy_session.consecutive_analysis_errors == 0  # Successfully reset
    assert dummy_session.is_terminated is False
    assert dummy_session.enforcement_action_taken is None


@pytest.mark.asyncio
async def test_41_ml_analysis_error_threshold_triggers_fail_safe_teardown(dummy_session):
    """
    Scenario F7: Sustained ML failure exceeding consecutive threshold (3 consecutive errors = 3.0s).
    Mandatory correction:
    - Observe and count analysis_error events.
    - Do NOT convert infrastructure/ML failure into a fake HIGH/CRITICAL security verdict.
    - Define deterministic failure behavior after threshold:
      controlled fail-safe teardown -> hang up caller with reason="congestion".
    """
    reqs = []
    gateway = make_gateway(
        mode=EnforcementMode.ENFORCE,
        recorded_list=reqs,
        max_consecutive_analysis_errors=3,
    )
    gateway.active_session = dummy_session

    events = [
        json.dumps({"type": "error", "code": "analysis_error", "message": "CUDA out of memory window 1"}),
        json.dumps({"type": "error", "code": "analysis_error", "message": "CUDA out of memory window 2"}),
        json.dumps({"type": "error", "code": "analysis_error", "message": "CUDA out of memory window 3"}),
    ]

    class MockWs:
        def __init__(self, evs):
            self.evs = list(evs)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.evs:
                return self.evs.pop(0)
            raise asyncio.CancelledError()

    dummy_session.ws = MockWs(events)

    await gateway._listen_voiceshield_ws(dummy_session)

    assert dummy_session.consecutive_analysis_errors == 3
    assert dummy_session.is_terminated is True
    assert dummy_session.state == CallState.TERMINATED
    assert dummy_session.enforcement_action_taken is None  # NO fake security verdict!
    hangup_reqs = [r for r in reqs if f"/channels/{dummy_session.caller_channel_id}" in str(r.url) and r.method == "DELETE"]
    assert len(hangup_reqs) == 1
    assert "reason=congestion" in str(hangup_reqs[0].url)


@pytest.mark.asyncio
async def test_42_startup_reconciliation_only_reaps_owned_resources():
    """
    Scenario F5: Startup reconciliation.
    Mandatory correction:
    - NEVER delete all Asterisk bridges/channels blindly.
    - Reconcile only resources demonstrably owned by VoiceShield.
    - Identify ownership using existing VoiceShield/Stasis/externalMedia metadata:
      Bridge: creator == 'Stasis' and bridge_class == 'stasis'
      Channel: 'UnicastRTP' in name or app_data == '(Outgoing Line)'
    - If ownership cannot be established, leave the resource untouched and log it.
    """
    deleted_urls = []
    def ari_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if request.method == "DELETE":
            deleted_urls.append(url_str)
            return httpx.Response(204)
        if "/applications/voiceshield" in url_str:
            return httpx.Response(200, json={
                "bridge_ids": ["b-owned-stasis", "b-foreign-confbridge"],
                "channel_ids": ["c-owned-rtp", "c-owned-outgoing", "c-foreign-caller"],
            })
        if "/bridges/b-owned-stasis" in url_str:
            return httpx.Response(200, json={"id": "b-owned-stasis", "creator": "Stasis", "bridge_class": "stasis"})
        if "/bridges/b-foreign-confbridge" in url_str:
            return httpx.Response(200, json={"id": "b-foreign-confbridge", "creator": "ConfBridge", "bridge_class": "softmix"})
        if "/channels/c-owned-rtp" in url_str:
            return httpx.Response(200, json={"id": "c-owned-rtp", "name": "UnicastRTP/127.0.0.1:20000", "dialplan": {}})
        if "/channels/c-owned-outgoing" in url_str:
            return httpx.Response(200, json={"id": "c-owned-outgoing", "name": "Local/100@default", "dialplan": {"app_data": "(Outgoing Line)"}})
        if "/channels/c-foreign-caller" in url_str:
            return httpx.Response(200, json={"id": "c-foreign-caller", "name": "PJSIP/alice-0001", "dialplan": {"app_data": "100"}})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(ari_handler), base_url="http://localhost:8088")
    gateway = TelephonyGateway(http_client=client)

    await gateway._reconcile_startup_resources()

    # Owned resources must be deleted
    assert any("/bridges/b-owned-stasis" in u for u in deleted_urls)
    assert any("/channels/c-owned-rtp" in u for u in deleted_urls)
    assert any("/channels/c-owned-outgoing" in u for u in deleted_urls)

    # Foreign resources must NOT be deleted
    assert not any("/bridges/b-foreign-confbridge" in u for u in deleted_urls)
    assert not any("/channels/c-foreign-caller" in u for u in deleted_urls)


@pytest.mark.asyncio
async def test_43_normal_sip_bye_during_watchdog_is_idempotent(dummy_session):
    """
    Scenario F8: Normal SIP BYE arrives via ARI StasisEnd around watchdog handling.
    - Teardown executes cleanly.
    - Watchdog task is cancelled.
    - Repeated teardown call is idempotent (no-op).
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.active_session = dummy_session

    async def mock_watchdog():
        await asyncio.sleep(10.0)
    dummy_session.rtp_watchdog_task = asyncio.create_task(mock_watchdog())

    # Simulate ARI StasisEnd event
    await gateway._handle_ari_event({
        "type": "StasisEnd",
        "channel": {"id": dummy_session.caller_channel_id},
    })

    assert dummy_session.is_terminated is True
    await asyncio.sleep(0.01)
    assert dummy_session.rtp_watchdog_task.cancelled()
    assert gateway.active_session is None

    # Secondary teardown attempt is a complete no-op
    req_count_before = len(reqs)
    await gateway._teardown_session(dummy_session)
    assert len(reqs) == req_count_before


@pytest.mark.asyncio
async def test_44_enforce_hold_followed_by_allow_unhold(dummy_session):
    """
    Scenario F9: Real Asterisk HOLD followed by ALLOW / unhold.
    - Decision HOLD executes POST /channels/{id}/hold and transitions to HOLD state.
    - Subsequent Decision ALLOW executes DELETE /channels/{id}/hold and transitions to ACTIVE state.
    """
    reqs = []
    gateway = make_gateway(mode=EnforcementMode.ENFORCE, recorded_list=reqs)
    gateway.active_session = dummy_session

    # 1. Trigger HOLD
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="HOLD",
        action="hold",
        risk_state="suspicious",
        risk_score=60,
        reasons=["suspicious_pattern"],
    )
    assert dummy_session.state == CallState.HOLD
    assert dummy_session.enforcement_action_taken == "HOLD"
    hold_reqs = [r for r in reqs if r.method == "POST" and f"/channels/{dummy_session.caller_channel_id}/hold" in str(r.url)]
    assert len(hold_reqs) == 1

    # 2. Trigger ALLOW
    await gateway._handle_policy_verdict(
        session=dummy_session,
        decision="ALLOW",
        action="allow",
        risk_state="low",
        risk_score=15,
        reasons=[],
    )
    assert dummy_session.state == CallState.ACTIVE
    unhold_reqs = [r for r in reqs if r.method == "DELETE" and f"/channels/{dummy_session.caller_channel_id}/hold" in str(r.url)]
    assert len(unhold_reqs) == 1
