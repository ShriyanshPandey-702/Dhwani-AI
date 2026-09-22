"""
VoiceShield Telephony Gateway — Controlled VoIP/SIP Live Call Adapter.

Acts as a clean, decoupled bridge between Asterisk 20 and VoiceShield:
1. Subscribes to Asterisk ARI Stasis events ('voiceshield' application).
2. On inbound call (StasisStart):
   - Creates & activates a VoiceShield session via FastAPI REST API.
   - Answers the SIP call and creates an externalMedia channel (slin16 RTP).
   - Bridges the caller channel with the externalMedia channel.
   - Connects to VoiceShield WebSocket (/ws/sessions/{session_id}).
3. On incoming RTP UDP datagrams:
   - Depacketizes RFC 3550 RTP packets and extracts 16 kHz Signed Linear PCM.
   - Converts big-endian network byte order to little-endian int16.
   - Accumulates samples into canonical 250 ms chunks (4,000 samples = 8,000 bytes).
   - Pushes sequence-numbered audio_chunk messages to VoiceShield WebSocket.
4. Observes live risk_update and policy_decision events (OBSERVATION ONLY).
5. On hangup (StasisEnd):
   - Tears down Asterisk bridge & channels.
   - Closes VoiceShield WebSocket, triggering backend session teardown.
"""

from __future__ import annotations

import argparse
import asyncio
from enum import Enum
import json
import logging
import os
import signal
import sys
from typing import Dict, Optional, Tuple

import httpx
import websockets

from services.telephony.gateway.rtp import PcmAccumulator, RtpDepacketizer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("voiceshield.telephony_gateway")


class EnforcementMode(str, Enum):
    OBSERVE_ONLY = "observe_only"
    DRY_RUN = "dry_run"
    ENFORCE = "enforce"

    @classmethod
    def from_str(cls, val: Optional[str]) -> EnforcementMode:
        if not val:
            return cls.OBSERVE_ONLY
        normalized = val.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        log.warning(f"Invalid enforcement mode '{val}', defaulting to {cls.OBSERVE_ONLY.value}")
        return cls.OBSERVE_ONLY


class CallState(str, Enum):
    INIT = "INIT"
    ACTIVE = "ACTIVE"
    CHALLENGED = "CHALLENGED"
    HOLD = "HOLD"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"


def _get_active_user_id() -> str:
    try:
        import sqlite3
        conn = sqlite3.connect("services/api/voiceshield.db")
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE is_active = 1 ORDER BY created_at ASC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    return "afea1d7c-09e0-4422-86d0-f8680b7bad67"


def _make_service_token(secret: str = "local-dev-secret-not-for-production-1234567890abcdef") -> str:
    try:
        from datetime import datetime, timedelta, timezone
        from jose import jwt
        user_id = _get_active_user_id()
        expire = datetime.now(timezone.utc) + timedelta(hours=24)
        payload = {"sub": user_id, "exp": expire, "type": "access"}
        return jwt.encode(payload, secret, algorithm="HS256")
    except Exception:
        return ""


class RtpUdpProtocol(asyncio.DatagramProtocol):
    """Async UDP Protocol for receiving RTP datagrams from Asterisk."""

    def __init__(self, gateway: TelephonyGateway):
        self.gateway = gateway

    def connection_made(self, transport: asyncio.DatagramTransport):
        self.gateway.udp_transport = transport
        log.info("RTP UDP listener bound and ready")

    def datagram_received(self, data: bytes, addr: Tuple[str, int]):
        self.gateway.on_rtp_datagram(data, addr)

    def error_received(self, exc: Exception):
        log.error(f"RTP UDP error: {exc}")


class ActiveCallSession:
    """Encapsulates state for one active VoIP call."""

    def __init__(
        self,
        caller_channel_id: str,
        caller_number: str,
        sip_call_id: str,
    ):
        self.caller_channel_id = caller_channel_id
        self.caller_number = caller_number
        self.sip_call_id = sip_call_id
        self.state: CallState = CallState.INIT
        self.enforcement_action_taken: Optional[str] = None
        self.external_channel_id: Optional[str] = None
        self.bridge_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.depacketizer = RtpDepacketizer(is_big_endian=True)
        self.accumulator = PcmAccumulator(sample_rate=16000, chunk_duration_ms=250)
        self.chunks_sent = 0
        self.ws_receive_task: Optional[asyncio.Task] = None
        self.is_terminating: bool = False
        self.is_terminated: bool = False
        self.ari_actions_log: list[dict] = []


class TelephonyGateway:
    def __init__(
        self,
        ari_url: str = "http://localhost:8088/ari",
        ari_ws_url: str = "ws://localhost:8088/ari/events",
        ari_username: str = "voiceshield",
        ari_password: str = "voiceshield_secret_pass",
        ari_app: str = "voiceshield",
        backend_http_url: str = "http://localhost:8000",
        backend_ws_url: str = "ws://localhost:8000/ws/sessions",
        rtp_bind_host: str = "0.0.0.0",
        rtp_bind_port: int = 20000,
        asterisk_external_host: str = "host.docker.internal:20000",
        enforcement_mode: EnforcementMode = EnforcementMode.OBSERVE_ONLY,
        challenge_sound: str = "sound:challenge_prompt",
        test_verdict: Optional[str] = None,
        test_verdict_delay: float = 3.0,
        test_verdict_repeat: int = 1,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.ari_url = ari_url.rstrip("/")
        self.ari_ws_url = ari_ws_url
        self.ari_username = ari_username
        self.ari_password = ari_password
        self.ari_app = ari_app
        self.backend_http_url = backend_http_url.rstrip("/")
        self.backend_ws_url = backend_ws_url.rstrip("/")
        self.rtp_bind_host = rtp_bind_host
        self.rtp_bind_port = rtp_bind_port
        self.asterisk_external_host = asterisk_external_host
        self.enforcement_mode = enforcement_mode
        self.challenge_sound = challenge_sound
        self.test_verdict = test_verdict
        self.test_verdict_delay = test_verdict_delay
        self.test_verdict_repeat = test_verdict_repeat

        self.http_client: Optional[httpx.AsyncClient] = http_client
        self.udp_transport: Optional[asyncio.DatagramTransport] = None
        self.active_session: Optional[ActiveCallSession] = None
        self.running = False

    async def start(self) -> None:
        self.running = True
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                auth=(self.ari_username, self.ari_password),
                timeout=10.0,
            )

        loop = asyncio.get_running_loop()
        log.info(f"Binding RTP UDP socket on {self.rtp_bind_host}:{self.rtp_bind_port}...")
        await loop.create_datagram_endpoint(
            lambda: RtpUdpProtocol(self),
            local_addr=(self.rtp_bind_host, self.rtp_bind_port),
        )

        await self._run_ari_event_loop()

    async def stop(self) -> None:
        log.info("Stopping Telephony Gateway...")
        self.running = False
        if self.active_session:
            await self._teardown_session(self.active_session)
        if self.udp_transport:
            self.udp_transport.close()
        if self.http_client:
            await self.http_client.aclose()
        log.info("Telephony Gateway stopped.")

    # ── ARI Event Loop ────────────────────────────────────────────────────────

    async def _run_ari_event_loop(self) -> None:
        ws_url = f"{self.ari_ws_url}?app={self.ari_app}&api_key={self.ari_username}:{self.ari_password}"
        log.info(f"Connecting to Asterisk ARI WebSocket: {self.ari_ws_url} (app={self.ari_app})...")

        while self.running:
            try:
                async with websockets.connect(ws_url) as ws:
                    log.info("Connected to Asterisk ARI. Waiting for call events...")
                    async for raw_msg in ws:
                        if not self.running:
                            break
                        try:
                            event = json.loads(raw_msg)
                            await self._handle_ari_event(event)
                        except Exception as e:
                            log.error(f"Error handling ARI event: {e}", exc_info=True)
            except (websockets.ConnectionClosed, OSError) as e:
                if not self.running:
                    break
                log.warning(f"ARI connection lost ({e}). Reconnecting in 3s...")
                await asyncio.sleep(3.0)

    async def _handle_ari_event(self, event: dict) -> None:
        ev_type = event.get("type")
        if ev_type == "StasisStart":
            channel = event.get("channel", {})
            channel_id = channel.get("id")
            channel_name = channel.get("name", "")

            # Ignore channels created for externalMedia
            if "UnicastRTP" in channel_name or channel.get("dialplan", {}).get("app_data") == "(Outgoing Line)":
                return

            caller_num = channel.get("caller", {}).get("number", "unknown")
            log.info(f"Inbound call received in Stasis: channel={channel_id}, caller={caller_num}")

            if self.active_session:
                log.warning(f"Active session already running for {self.active_session.caller_channel_id}. Tearing down previous session.")
                await self._teardown_session(self.active_session)

            session = ActiveCallSession(
                caller_channel_id=channel_id,
                caller_number=caller_num,
                sip_call_id=channel.get("variables", {}).get("SIPCALLID", channel_id),
            )
            self.active_session = session
            await self._setup_call_and_streaming(session)

        elif ev_type == "StasisEnd":
            channel = event.get("channel", {})
            channel_id = channel.get("id")
            if self.active_session and channel_id == self.active_session.caller_channel_id:
                log.info(f"Caller hung up: channel={channel_id}. Initiating teardown.")
                await self._teardown_session(self.active_session)
                self.active_session = None

    # ── Call Setup & Media Routing ───────────────────────────────────────────

    async def _setup_call_and_streaming(self, session: ActiveCallSession) -> None:
        try:
            token = _make_service_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}

            # 1. Create VoiceShield session via FastAPI REST API
            async with httpx.AsyncClient(timeout=5.0, headers=headers) as client:
                res = await client.post(
                    f"{self.backend_http_url}/sessions",
                    json={
                        "metadata": {
                            "call_source": "sip_voip",
                            "caller_number": session.caller_number,
                            "asterisk_channel_id": session.caller_channel_id,
                            "sip_call_id": session.sip_call_id,
                        }
                    },
                )
                res.raise_for_status()
                session_data = res.json()
                session.session_id = session_data["id"]
                log.info(f"VoiceShield session created: id={session.session_id}")

                # 2. Activate session
                start_res = await client.post(f"{self.backend_http_url}/sessions/{session.session_id}/start")
                start_res.raise_for_status()
                log.info(f"VoiceShield session activated: id={session.session_id}")

            # 3. Connect to VoiceShield WebSocket (with service JWT token for authoritative user binding)
            token_query = f"?token={token}" if token else ""
            ws_url = f"{self.backend_ws_url}/{session.session_id}{token_query}"
            session.ws = await websockets.connect(ws_url)
            log.info(f"Connected to VoiceShield WebSocket: {self.backend_ws_url}/{session.session_id}")

            # Start background listener for risk updates
            session.ws_receive_task = asyncio.create_task(self._listen_voiceshield_ws(session))

            # 4. Answer incoming SIP channel in Asterisk (if not already answered in dialplan)
            try:
                ans_res = await self.http_client.post(f"{self.ari_url}/channels/{session.caller_channel_id}/answer")
                log.info(f"Answered caller channel {session.caller_channel_id}: status={ans_res.status_code}")
            except Exception as e:
                log.info(f"Caller channel {session.caller_channel_id} already answered or in state Up: {e}")

            # 5. Create externalMedia channel in Asterisk (slin16 RTP to host UDP port)
            ext_res = await self.http_client.post(
                f"{self.ari_url}/channels/externalMedia",
                params={
                    "app": self.ari_app,
                    "external_host": self.asterisk_external_host,
                    "format": "slin16",
                    "encapsulation": "rtp",
                    "transport": "udp",
                    "direction": "both",
                },
            )
            ext_res.raise_for_status()
            ext_data = ext_res.json()
            session.external_channel_id = ext_data["id"]
            log.info(f"Created externalMedia channel: {session.external_channel_id} (target={self.asterisk_external_host})")

            # 6. Create mixing bridge and add both channels
            br_res = await self.http_client.post(f"{self.ari_url}/bridges", params={"type": "mixing"})
            br_res.raise_for_status()
            session.bridge_id = br_res.json()["id"]
            log.info(f"Created mixing bridge: {session.bridge_id}")

            add_res = await self.http_client.post(
                f"{self.ari_url}/bridges/{session.bridge_id}/addChannel",
                params={"channel": f"{session.caller_channel_id},{session.external_channel_id}"},
            )
            add_res.raise_for_status()
            session.state = CallState.ACTIVE
            log.info(f"Bridged caller channel and externalMedia channel into bridge {session.bridge_id}")
            log.info(f"Media bridge active. Streaming RTP audio to VoiceShield pipeline (CallState={session.state.value}).")

            if self.test_verdict:
                asyncio.create_task(
                    self._schedule_test_verdicts(
                        session=session,
                        verdict=self.test_verdict,
                        delay=self.test_verdict_delay,
                        repeat=self.test_verdict_repeat,
                    )
                )

        except Exception as e:
            log.error(f"Failed to set up call media session: {e}", exc_info=True)
            await self._teardown_session(session)
            self.active_session = None

    async def _schedule_test_verdicts(
        self, session: ActiveCallSession, verdict: str, delay: float, repeat: int = 1
    ) -> None:
        try:
            await asyncio.sleep(delay)
            if not session or session.is_terminated or session.state == CallState.TERMINATED:
                return

            v_upper = verdict.upper()
            action = v_upper.lower()
            if v_upper == "BLOCK":
                score = 95
                state = "critical"
                reasons = ["voice_authenticity_anomaly", "synthetic_speech_detected"]
            elif v_upper in ("VERIFY", "CHALLENGE"):
                score = 65
                state = "high"
                reasons = ["interactive_challenge_required"]
            elif v_upper == "HOLD":
                score = 80
                state = "critical"
                reasons = ["high_consequence_hold"]
            else:
                score = 10
                state = "low"
                reasons = ["benign_audio_verified"]

            for i in range(max(1, repeat)):
                if session.is_terminated or session.state == CallState.TERMINATED:
                    break
                log.info(
                    f"Emitting Policy Decision Event [{i+1}/{repeat}] for session {session.session_id}: "
                    f"Decision={v_upper}, Action={action}, Score={score}, State={state}"
                )
                await self._handle_policy_verdict(
                    session=session,
                    decision=v_upper,
                    action=action,
                    risk_state=state,
                    risk_score=score,
                    reasons=reasons,
                )
                if repeat > 1:
                    await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error in test verdict scheduler: {e}", exc_info=True)

    # ── RTP Datagram Processing ───────────────────────────────────────────────

    def on_rtp_datagram(self, datagram: bytes, addr: Tuple[str, int]) -> None:
        session = self.active_session
        if not session or not session.ws or session.ws.closed:
            return

        # Depacketize RFC 3550 RTP, convert big-endian to little-endian PCM16
        pcm_bytes = session.depacketizer.extract_pcm16_le(datagram)
        if not pcm_bytes:
            return

        # Accumulate into canonical 250 ms chunks (8,000 bytes = 4,000 samples)
        chunks = session.accumulator.push(pcm_bytes)
        for chunk in chunks:
            msg = session.accumulator.build_chunk_message(chunk)
            session.chunks_sent += 1
            # Forward over WebSocket asynchronously without blocking UDP socket
            asyncio.create_task(self._send_audio_chunk(session, msg))

    async def _send_audio_chunk(self, session: ActiveCallSession, msg: dict) -> None:
        try:
            if session.ws and not session.ws.closed:
                await session.ws.send(json.dumps(msg))
        except Exception as e:
            log.warning(f"Error sending audio chunk to VoiceShield: {e}")

    # ── VoiceShield WebSocket Listener & Enforcement Dispatcher ──────────────

    async def _listen_voiceshield_ws(self, session: ActiveCallSession) -> None:
        log.info(f"Starting VoiceShield event listener for session {session.session_id}")
        try:
            async for raw in session.ws:
                if session.is_terminated or session.state == CallState.TERMINATED:
                    break
                try:
                    event = json.loads(raw)
                    ev_type = event.get("type")
                    if ev_type == "risk_update":
                        score = event.get("risk_score", 0)
                        state = event.get("risk_state", "")
                        decision = event.get("decision", "")
                        log.info(
                            f"Live Risk Observation [Session {session.session_id[:8]}]: "
                            f"Score={score}, State={state}, Decision={decision}"
                        )
                        await self._handle_policy_verdict(
                            session=session,
                            decision=decision,
                            action=event.get("action", ""),
                            risk_state=state,
                            risk_score=score,
                            reasons=event.get("reasons", []),
                        )
                    elif ev_type == "policy_decision":
                        dec = event.get("decision", "")
                        action = event.get("action", "")
                        risk_score = event.get("risk_score", 0)
                        risk_state = event.get("risk_state", "")
                        reasons = event.get("reasons", [])
                        log.info(
                            f"Policy Decision Emitted [Session {session.session_id[:8]}]: "
                            f"Decision={dec}, Action={action}, Score={risk_score}, State={risk_state}"
                        )
                        await self._handle_policy_verdict(
                            session=session,
                            decision=dec,
                            action=action,
                            risk_state=risk_state,
                            risk_score=risk_score,
                            reasons=reasons,
                        )
                    elif ev_type == "alert":
                        log.warning(f"VoiceShield Alert [OBSERVATION ONLY]: {event.get('message')}")
                except Exception as e:
                    log.warning(f"Failed parsing VoiceShield event: {e}")
        except websockets.ConnectionClosed:
            log.info(f"VoiceShield WebSocket closed for session {session.session_id}")
        except Exception as e:
            log.error(f"Error in VoiceShield WebSocket listener: {e}")

    # ── Enforcement State Machine ─────────────────────────────────────────────

    async def _handle_policy_verdict(
        self,
        session: ActiveCallSession,
        decision: str,
        action: str,
        risk_state: str,
        risk_score: int,
        reasons: list[str],
    ) -> None:
        """
        Idempotent enforcement state machine handling VoiceShield decisions.
        """
        if session.is_terminating or session.is_terminated or session.state in (CallState.TERMINATING, CallState.TERMINATED):
            log.info(
                f"Policy decision '{decision}' ignored: session is already in state {session.state.value}"
            )
            return

        decision_upper = decision.upper() if decision else ""
        action_lower = action.lower() if action else ""

        if decision_upper in ("BLOCK", "ESCALATE") or action_lower in ("block", "escalate"):
            await self._enforce_block(session, reasons, risk_score)
        elif decision_upper == "HOLD" or action_lower == "hold":
            await self._enforce_hold(session, reasons, risk_score)
        elif decision_upper == "VERIFY" or action_lower in ("challenge", "verify"):
            await self._enforce_challenge(session, reasons, risk_score)
        elif decision_upper == "ALLOW" or action_lower == "allow":
            await self._enforce_allow(session)

    async def _enforce_allow(self, session: ActiveCallSession) -> None:
        if session.state == CallState.HOLD:
            log.info(f"Transitioning from HOLD to ACTIVE under ALLOW decision on channel {session.caller_channel_id}")
            if self.enforcement_mode == EnforcementMode.ENFORCE and self.http_client:
                try:
                    res = await self.http_client.delete(f"{self.ari_url}/channels/{session.caller_channel_id}/hold")
                    if res.status_code in (200, 204):
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} removed from hold")
                except Exception as e:
                    log.warning(f"Failed unholding channel {session.caller_channel_id}: {e}")
        session.state = CallState.ACTIVE
        log.info(f"Policy Decision [ALLOW]: Call on channel {session.caller_channel_id} remains ACTIVE")

    async def _enforce_challenge(
        self,
        session: ActiveCallSession,
        reasons: list[str],
        risk_score: int,
    ) -> None:
        if session.state == CallState.CHALLENGED:
            return
        session.state = CallState.CHALLENGED
        session.enforcement_action_taken = "CHALLENGE"

        action_record = {
            "action": "CHALLENGE",
            "channel_id": session.caller_channel_id,
            "mode": self.enforcement_mode.value,
            "media": self.challenge_sound,
            "executed": False,
        }
        session.ari_actions_log.append(action_record)

        if self.enforcement_mode == EnforcementMode.OBSERVE_ONLY:
            log.info(
                f"[OBSERVE_ONLY] Policy Decision VERIFY/CHALLENGE (Score={risk_score}, Reasons={reasons}). Zero ARI action performed."
            )
            return

        if self.enforcement_mode == EnforcementMode.DRY_RUN:
            log.info(
                f"[DRY_RUN] Would execute ARI: POST {self.ari_url}/channels/{session.caller_channel_id}/play?media={self.challenge_sound}"
            )
            return

        if self.enforcement_mode == EnforcementMode.ENFORCE:
            log.info(
                f"[ENFORCE] Executing ARI: POST {self.ari_url}/channels/{session.caller_channel_id}/play?media={self.challenge_sound}"
            )
            if self.http_client:
                try:
                    res = await self.http_client.post(
                        f"{self.ari_url}/channels/{session.caller_channel_id}/play",
                        params={"media": self.challenge_sound},
                    )
                    action_record["status_code"] = res.status_code
                    if res.status_code in (200, 201):
                        action_record["executed"] = True
                        log.info(f"[ENFORCE] Challenge audio playback started on channel {session.caller_channel_id}")
                    elif res.status_code == 404:
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} not found for challenge play (404)")
                    else:
                        log.warning(f"[ENFORCE] Unexpected ARI play status {res.status_code}: {res.text}")
                except httpx.TimeoutException:
                    log.error(f"[ENFORCE] ARI request timed out playing challenge on {session.caller_channel_id}")
                except httpx.RequestError as e:
                    log.error(f"[ENFORCE] ARI connection error playing challenge: {e}")
                except Exception as e:
                    log.error(f"[ENFORCE] Error playing challenge prompt: {e}", exc_info=True)

    async def _enforce_hold(
        self,
        session: ActiveCallSession,
        reasons: list[str],
        risk_score: int,
    ) -> None:
        if session.state == CallState.HOLD:
            return
        session.state = CallState.HOLD
        session.enforcement_action_taken = "HOLD"

        action_record = {
            "action": "HOLD",
            "channel_id": session.caller_channel_id,
            "mode": self.enforcement_mode.value,
            "executed": False,
        }
        session.ari_actions_log.append(action_record)

        if self.enforcement_mode == EnforcementMode.OBSERVE_ONLY:
            log.info(
                f"[OBSERVE_ONLY] Policy Decision HOLD (Score={risk_score}, Reasons={reasons}). Zero ARI action performed."
            )
            return

        if self.enforcement_mode == EnforcementMode.DRY_RUN:
            log.info(
                f"[DRY_RUN] Would execute ARI: POST {self.ari_url}/channels/{session.caller_channel_id}/hold"
            )
            return

        if self.enforcement_mode == EnforcementMode.ENFORCE:
            log.info(
                f"[ENFORCE] Executing ARI: POST {self.ari_url}/channels/{session.caller_channel_id}/hold"
            )
            if self.http_client:
                try:
                    res = await self.http_client.post(f"{self.ari_url}/channels/{session.caller_channel_id}/hold")
                    action_record["status_code"] = res.status_code
                    if res.status_code in (200, 204):
                        action_record["executed"] = True
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} placed on HOLD")
                    elif res.status_code == 404:
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} not found for hold (404)")
                    else:
                        log.warning(f"[ENFORCE] Unexpected ARI hold status {res.status_code}: {res.text}")
                except httpx.TimeoutException:
                    log.error(f"[ENFORCE] ARI request timed out putting {session.caller_channel_id} on hold")
                except httpx.RequestError as e:
                    log.error(f"[ENFORCE] ARI connection error during hold: {e}")
                except Exception as e:
                    log.error(f"[ENFORCE] Error placing channel on hold: {e}", exc_info=True)

    async def _enforce_block(
        self,
        session: ActiveCallSession,
        reasons: list[str],
        risk_score: int,
    ) -> None:
        # Idempotency guard: if already terminating or terminated, drop
        if session.is_terminating or session.is_terminated or session.state in (CallState.TERMINATING, CallState.TERMINATED):
            log.info(f"Duplicate BLOCK event ignored; channel {session.caller_channel_id} already in state {session.state.value}")
            return

        session.is_terminating = True
        session.state = CallState.TERMINATING
        session.enforcement_action_taken = "BLOCK"

        action_record = {
            "action": "BLOCK",
            "channel_id": session.caller_channel_id,
            "mode": self.enforcement_mode.value,
            "executed": False,
        }
        session.ari_actions_log.append(action_record)

        if self.enforcement_mode == EnforcementMode.OBSERVE_ONLY:
            log.info(
                f"[OBSERVE_ONLY] Policy Decision BLOCK (Score={risk_score}, Reasons={reasons}). Zero ARI action performed."
            )
            return

        if self.enforcement_mode == EnforcementMode.DRY_RUN:
            log.info(
                f"[DRY_RUN] Would execute ARI: DELETE {self.ari_url}/channels/{session.caller_channel_id}?reason=congestion"
            )
            return

        if self.enforcement_mode == EnforcementMode.ENFORCE:
            log.info(
                f"[ENFORCE] Executing ARI: DELETE {self.ari_url}/channels/{session.caller_channel_id}?reason=congestion"
            )
            if self.http_client:
                try:
                    res = await self.http_client.delete(
                        f"{self.ari_url}/channels/{session.caller_channel_id}",
                        params={"reason": "congestion"},
                    )
                    action_record["status_code"] = res.status_code
                    if res.status_code in (200, 204):
                        action_record["executed"] = True
                        log.info(f"[ENFORCE] Successfully terminated channel {session.caller_channel_id} via ARI DELETE")
                    elif res.status_code == 404:
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} already terminated (404 Not Found)")
                    else:
                        log.warning(f"[ENFORCE] Unexpected ARI hangup status {res.status_code}: {res.text}")
                except httpx.TimeoutException:
                    log.error(f"[ENFORCE] ARI request timed out deleting channel {session.caller_channel_id}")
                except httpx.RequestError as e:
                    log.error(f"[ENFORCE] ARI connection error during block: {e}")
                except Exception as e:
                    log.error(f"[ENFORCE] Unexpected error terminating channel: {e}", exc_info=True)

    # ── Teardown ─────────────────────────────────────────────────────────────

    async def _teardown_session(self, session: ActiveCallSession) -> None:
        if session.is_terminated:
            return
        session.is_terminated = True
        session.state = CallState.TERMINATED

        log.info(f"Tearing down call session for channel {session.caller_channel_id} (State={session.state.value})...")

        # 1. Cancel WebSocket listener
        if session.ws_receive_task and not session.ws_receive_task.done():
            session.ws_receive_task.cancel()

        # 2. Close VoiceShield WebSocket (triggers backend _teardown, flushes buffers & saves incident)
        if session.ws and not session.ws.closed:
            try:
                await session.ws.close()
                log.info(f"Closed VoiceShield WebSocket for session {session.session_id}")
            except Exception as e:
                log.warning(f"Error closing WebSocket: {e}")

        # 3. Destroy Asterisk Bridge and externalMedia channel
        if self.http_client:
            if session.bridge_id:
                try:
                    res = await self.http_client.delete(f"{self.ari_url}/bridges/{session.bridge_id}")
                    log.info(f"Destroyed bridge {session.bridge_id} (status={res.status_code})")
                except Exception as e:
                    log.warning(f"Failed deleting bridge: {e}")

            if session.external_channel_id:
                try:
                    res = await self.http_client.delete(f"{self.ari_url}/channels/{session.external_channel_id}")
                    log.info(f"Destroyed externalMedia channel {session.external_channel_id} (status={res.status_code})")
                except Exception as e:
                    log.warning(f"Failed deleting externalMedia channel: {e}")

        # 4. Log telemetry summary
        t = session.depacketizer.telemetry
        log.info(
            f"Session Telemetry Summary [Channel {session.caller_channel_id}]: "
            f"RTP Packets Received={t.packets_received}, Bytes={t.bytes_received}, "
            f"Samples={t.samples_received}, Sequence Gaps={t.sequence_gaps}, "
            f"Invalid Packets={t.packets_invalid}, Chunks Forwarded={session.chunks_sent}, "
            f"Final State={session.state.value}, Enforcement={session.enforcement_action_taken}"
        )


async def main():
    parser = argparse.ArgumentParser(description="VoiceShield Telephony Gateway")
    parser.add_argument("--ari-url", default="http://localhost:8088/ari", help="Asterisk ARI URL")
    parser.add_argument("--ari-ws", default="ws://localhost:8088/ari/events", help="Asterisk ARI WS URL")
    parser.add_argument("--ari-user", default="voiceshield", help="ARI username")
    parser.add_argument("--ari-pass", default="voiceshield_secret_pass", help="ARI password")
    parser.add_argument("--ari-app", default="voiceshield", help="ARI Stasis app name")
    parser.add_argument("--backend-http", default="http://localhost:8000", help="VoiceShield FastAPI HTTP URL")
    parser.add_argument("--backend-ws", default="ws://localhost:8000/ws/sessions", help="VoiceShield WS base URL")
    parser.add_argument("--rtp-host", default="0.0.0.0", help="RTP UDP bind host")
    parser.add_argument("--rtp-port", type=int, default=20000, help="RTP UDP bind port")
    parser.add_argument("--external-host", default="host.docker.internal:20000", help="Target external_host for Asterisk")
    parser.add_argument(
        "--enforcement-mode",
        default=os.getenv("VOICESHIELD_ENFORCEMENT_MODE", "observe_only"),
        choices=["observe_only", "dry_run", "enforce"],
        help="Enforcement mode: observe_only (default), dry_run, or enforce",
    )
    parser.add_argument(
        "--challenge-sound",
        default="sound:challenge_prompt",
        help="ARI sound URI to play for challenge/verify",
    )
    parser.add_argument(
        "--test-verdict",
        default=None,
        choices=["BLOCK", "CHALLENGE", "VERIFY", "HOLD", "ALLOW", "block", "challenge", "verify", "hold", "allow"],
        help="Deterministic policy decision trigger for controlled tests",
    )
    parser.add_argument(
        "--test-verdict-delay",
        type=float,
        default=3.0,
        help="Delay in seconds before triggering test policy decision",
    )
    parser.add_argument(
        "--test-verdict-repeat",
        type=int,
        default=1,
        help="Number of times to repeat the test policy decision (for idempotency testing)",
    )
    args = parser.parse_args()

    mode = EnforcementMode.from_str(args.enforcement_mode)
    log.info(f"Initializing Telephony Gateway with EnforcementMode={mode.value.upper()}")

    gateway = TelephonyGateway(
        ari_url=args.ari_url,
        ari_ws_url=args.ari_ws,
        ari_username=args.ari_user,
        ari_password=args.ari_pass,
        ari_app=args.ari_app,
        backend_http_url=args.backend_http,
        backend_ws_url=args.backend_ws,
        rtp_bind_host=args.rtp_host,
        rtp_bind_port=args.rtp_port,
        asterisk_external_host=args.external_host,
        enforcement_mode=mode,
        challenge_sound=args.challenge_sound,
        test_verdict=args.test_verdict,
        test_verdict_delay=args.test_verdict_delay,
        test_verdict_repeat=args.test_verdict_repeat,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(gateway.stop()))
        except NotImplementedError:
            pass

    try:
        await gateway.start()
    except asyncio.CancelledError:
        pass
    finally:
        await gateway.stop()


if __name__ == "__main__":
    asyncio.run(main())
