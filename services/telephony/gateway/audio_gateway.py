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
import json
import logging
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
        self.external_channel_id: Optional[str] = None
        self.bridge_id: Optional[str] = None
        self.session_id: Optional[str] = None
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.depacketizer = RtpDepacketizer(is_big_endian=True)
        self.accumulator = PcmAccumulator(sample_rate=16000, chunk_duration_ms=250)
        self.chunks_sent = 0
        self.ws_receive_task: Optional[asyncio.Task] = None


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

        self.http_client: Optional[httpx.AsyncClient] = None
        self.udp_transport: Optional[asyncio.DatagramTransport] = None
        self.active_session: Optional[ActiveCallSession] = None
        self.running = False

    async def start(self) -> None:
        self.running = True
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
            log.info(f"Bridged caller channel and externalMedia channel into bridge {session.bridge_id}")
            log.info("Media bridge active. Streaming RTP audio to VoiceShield pipeline.")

        except Exception as e:
            log.error(f"Failed to set up call media session: {e}", exc_info=True)
            await self._teardown_session(session)
            self.active_session = None

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

    # ── VoiceShield WebSocket Listener (Observation Only) ────────────────────

    async def _listen_voiceshield_ws(self, session: ActiveCallSession) -> None:
        log.info(f"Starting VoiceShield event listener for session {session.session_id}")
        try:
            async for raw in session.ws:
                try:
                    event = json.loads(raw)
                    ev_type = event.get("type")
                    if ev_type == "risk_update":
                        score = event.get("risk_score")
                        state = event.get("risk_state")
                        decision = event.get("decision")
                        log.info(
                            f"Live Risk Observation [Session {session.session_id[:8]}]: "
                            f"Score={score}, State={state}, Decision={decision}"
                        )
                    elif ev_type == "policy_decision":
                        dec = event.get("decision")
                        action = event.get("action")
                        log.info(f"Policy Decision Emitted [OBSERVATION ONLY]: {dec} (Action: {action})")
                    elif ev_type == "alert":
                        log.warning(f"VoiceShield Alert [OBSERVATION ONLY]: {event.get('message')}")
                except Exception as e:
                    log.warning(f"Failed parsing VoiceShield event: {e}")
        except websockets.ConnectionClosed:
            log.info(f"VoiceShield WebSocket closed for session {session.session_id}")
        except Exception as e:
            log.error(f"Error in VoiceShield WebSocket listener: {e}")

    # ── Teardown ─────────────────────────────────────────────────────────────

    async def _teardown_session(self, session: ActiveCallSession) -> None:
        log.info(f"Tearing down call session for channel {session.caller_channel_id}...")

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
                    await self.http_client.delete(f"{self.ari_url}/bridges/{session.bridge_id}")
                    log.info(f"Destroyed bridge {session.bridge_id}")
                except Exception as e:
                    log.warning(f"Failed deleting bridge: {e}")

            if session.external_channel_id:
                try:
                    await self.http_client.delete(f"{self.ari_url}/channels/{session.external_channel_id}")
                    log.info(f"Destroyed externalMedia channel {session.external_channel_id}")
                except Exception as e:
                    log.warning(f"Failed deleting externalMedia channel: {e}")

        # 4. Log telemetry summary
        t = session.depacketizer.telemetry
        log.info(
            f"Session Telemetry Summary [Channel {session.caller_channel_id}]: "
            f"RTP Packets Received={t.packets_received}, Bytes={t.bytes_received}, "
            f"Samples={t.samples_received}, Sequence Gaps={t.sequence_gaps}, "
            f"Invalid Packets={t.packets_invalid}, Chunks Forwarded={session.chunks_sent}"
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
    args = parser.parse_args()

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
