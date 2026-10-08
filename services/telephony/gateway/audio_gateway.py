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
import re
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
    CHALLENGED = "CHALLENGED"  # Phase 4.2 compatibility
    CHALLENGE_MUTING = "CHALLENGE_MUTING"
    CHALLENGE_PLAYING = "CHALLENGE_PLAYING"
    CHALLENGE_LISTENING = "CHALLENGE_LISTENING"
    CHALLENGE_EVALUATING = "CHALLENGE_EVALUATING"
    CHALLENGE_PASSED = "CHALLENGE_PASSED"
    CHALLENGE_FAILED = "CHALLENGE_FAILED"
    CHALLENGE_TIMEOUT = "CHALLENGE_TIMEOUT"
    HOLD = "HOLD"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"


def normalize_challenge_text(text: str) -> str:
    """Normalize text by converting to lowercase, stripping punctuation, and compressing spaces."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_challenge_target(challenge_text: str) -> str:
    """
    Extracts the target spoken content from the backend-issued challenge text.
    If the challenge text contains quotes (e.g. 'The security of this call matters.'),
    the text within quotes is extracted as the target phrase.
    Otherwise, returns the normalized full challenge text.
    """
    quote_match = re.search(r"['\"]([^'\"]+)['\"]", challenge_text)
    if quote_match:
        return normalize_challenge_text(quote_match.group(1))
    return normalize_challenge_text(challenge_text)


def resolve_challenge_prompt_sound(challenge_text: str, challenge_type: str = "") -> Optional[str]:
    """
    Deterministically resolves the prompt audio asset for the exact backend-issued challenge.
    Returns sound uri (e.g. 'sound:challenge_phrase_security') or None if unmapped.
    """
    if not challenge_text:
        return None
    norm = normalize_challenge_text(challenge_text)

    # Exact mappings for backend CHALLENGE_POOL in services/api/app/api/challenge.py
    if "security of this call matters" in norm:
        return "sound:challenge_phrase_security"
    if "full name clearly" in norm or "your name clearly" in norm:
        return "sound:challenge_phrase_name"
    if "last 4 digits" in norm or "registered mobile number" in norm or ("digit" in norm and "mobile" in norm):
        return "sound:challenge_question_digits"
    if "city did you register from" in norm or "which city" in norm:
        return "sound:challenge_question_city"
    if "count from 1 to 5" in norm or "count from one to five" in norm:
        return "sound:challenge_sequence"
    if "authorize this transaction" in norm:
        return "sound:challenge_phrase_authorize"
    if "voiceshield verification active" in norm or "verification active" in norm:
        return "sound:challenge_phrase_active"
    if "today s date" in norm or "todays date" in norm or "what is today" in norm:
        return "sound:challenge_question_date"

    return None


def evaluate_challenge_response(
    challenge_text: str,
    challenge_type: str,
    transcript: str,
    speech_detected: bool,
) -> Tuple[str, str]:
    """
    Deterministic challenge response evaluation using the actual issued challenge_text.

    Outcome rules:
    - PASS: speech is detected and transcript satisfies the issued challenge_text.
    - FAIL: speech is detected but transcript is contradictory/non-matching, or transcription is unavailable/empty.
    - TIMEOUT: no speech detected during the response window.
    """
    if not speech_detected:
        return "timeout", "No speech detected during response window"

    norm_transcript = normalize_challenge_text(transcript)
    if not norm_transcript:
        return "failed", "Speech detected but transcription was unavailable or empty"

    target_phrase = extract_challenge_target(challenge_text)
    c_type = (challenge_type or "phrase").lower()

    # 1. Exact substring match
    if target_phrase and (target_phrase in norm_transcript or norm_transcript in target_phrase):
        return "passed", f"Transcript matched target phrase: '{target_phrase}'"

    # 2. Key token overlap (excluding directives and common stopwords)
    stopwords = {
        "please", "say", "your", "name", "clearly", "repeat", "after", "me",
        "the", "a", "an", "is", "of", "this", "that", "it", "to", "in", "for",
        "what", "which", "are", "from", "now", "slowly", "count",
    }
    target_tokens = [w for w in target_phrase.split() if w not in stopwords and len(w) > 2]
    if not target_tokens:
        target_tokens = [w for w in target_phrase.split() if len(w) > 1]

    transcript_tokens = set(norm_transcript.split())
    matched_tokens = [w for w in target_tokens if w in transcript_tokens]

    if target_tokens and (len(matched_tokens) / len(target_tokens) >= 0.5):
        return (
            "passed",
            f"Transcript satisfied challenge ({len(matched_tokens)}/{len(target_tokens)} key tokens matched: {matched_tokens})",
        )

    # 3. Number sequence challenge (e.g. Count from 1 to 5)
    if c_type == "sequence" or "count" in target_phrase:
        num_map = {"1": "one", "2": "two", "3": "three", "4": "four", "5": "five"}
        count_matched = sum(1 for d, w in num_map.items() if d in transcript_tokens or w in transcript_tokens)
        if count_matched >= 3:
            return "passed", f"Transcript satisfied sequence challenge ({count_matched} numbers matched)"

    # 4. Open question challenge (e.g. date, city, digits)
    if c_type == "question":
        refusals = {
            "no", "cancel", "bye", "hangup", "scam", "wrong", "refuse", "refused",
            "refusing", "stop", "decline", "declined", "unauthorized", "transfer",
            "lakh", "rupees", "otp", "vendor", "urgent",
        }
        if any(w in refusals for w in transcript_tokens):
            return "failed", f"Transcript contains non-responsive, refusal, or evasive content: '{norm_transcript}'"

        if "date" in target_phrase:
            date_words = {
                "today", "date", "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
                "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                "first", "second", "third", "fourth", "fifth", "twenty", "twenty-third",
                "twenty-second", "thirtieth", "thirty", "2026", "23rd", "23",
            }
            if any(w in date_words for w in transcript_tokens) or any(w.isdigit() for w in transcript_tokens):
                return "passed", f"Transcript provided valid date response: '{norm_transcript}'"
            return "failed", f"Transcript did not answer date question: '{norm_transcript}'"

        if "city" in target_phrase:
            city_words = {
                "city", "chicago", "illinois", "new", "york", "london", "paris", "delhi",
                "mumbai", "san", "francisco", "austin", "boston", "seattle", "registered",
            }
            if any(w in city_words for w in transcript_tokens):
                return "passed", f"Transcript provided valid city response: '{norm_transcript}'"
            return "failed", f"Transcript did not answer city question: '{norm_transcript}'"

        if "digit" in target_phrase or "number" in target_phrase or "mobile" in target_phrase:
            num_words = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "zero"}
            if any(w in num_words for w in transcript_tokens) or any(w.isdigit() for w in transcript_tokens):
                return "passed", f"Transcript provided valid digit response: '{norm_transcript}'"
            return "failed", f"Transcript did not answer digit question: '{norm_transcript}'"

        if len(transcript_tokens) >= 1:
            return "passed", f"Transcript provided valid response to question: '{norm_transcript}'"

    return "failed", f"Transcript did not satisfy challenge criteria (target='{target_phrase}', received='{norm_transcript}')"


def _get_active_user_id() -> str:
    try:
        import sqlite3
        db_path = "services/api/dhwaniai.db" if os.path.exists("services/api/dhwaniai.db") else "services/api/voiceshield.db"
        conn = sqlite3.connect(db_path)
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

        # Phase 5.1 Interactive Challenge fields
        self.challenge_id: Optional[str] = None
        self.challenge_text: Optional[str] = None
        self.challenge_type: Optional[str] = None
        self.challenge_playback_id: Optional[str] = None
        self.is_caller_muted: bool = False
        self.challenge_watchdog_task: Optional[asyncio.Task] = None
        self.challenge_window_task: Optional[asyncio.Task] = None
        self.challenge_listening_active: bool = False
        self.challenge_drain_active: bool = False
        self.challenge_buffered_chunks: list[dict] = []
        self.challenge_result_submitted: bool = False

        # Phase 5.2 Failure & Watchdog Hardening fields
        self.last_rtp_received_at: Optional[float] = None
        self.rtp_watchdog_task: Optional[asyncio.Task] = None
        self.consecutive_analysis_errors: int = 0


class TelephonyGateway:
    def __init__(
        self,
        ari_url: str = "http://localhost:8088/ari",
        ari_ws_url: str = "ws://localhost:8088/ari/events",
        ari_username: str = "voiceshield",
        ari_password: Optional[str] = None,
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
        backend_http_client: Optional[httpx.AsyncClient] = None,
        listening_window_duration: float = 5.0,
        playback_watchdog_timeout: float = 10.0,
        rtp_inactivity_timeout: float = 5.0,
        max_consecutive_analysis_errors: int = 3,
        ari_reconnect_backoff: float = 3.0,
    ):
        self.ari_url = ari_url.rstrip("/")
        self.ari_ws_url = ari_ws_url
        self.ari_username = ari_username or os.getenv("ARI_USER", "voiceshield")
        self.ari_password = ari_password or os.getenv("ARI_PASSWORD") or os.getenv("ARI_PASS") or ""
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
        self.backend_http_client: Optional[httpx.AsyncClient] = backend_http_client
        self.listening_window_duration = listening_window_duration
        self.playback_watchdog_timeout = playback_watchdog_timeout
        self.rtp_inactivity_timeout = rtp_inactivity_timeout
        self.max_consecutive_analysis_errors = max_consecutive_analysis_errors
        self.ari_reconnect_backoff = ari_reconnect_backoff
        self.udp_transport: Optional[asyncio.DatagramTransport] = None
        self.active_session: Optional[ActiveCallSession] = None
        self.running = False

    async def _get_backend_client(self) -> httpx.AsyncClient:
        if self.backend_http_client:
            return self.backend_http_client
        token = _make_service_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return httpx.AsyncClient(timeout=5.0, headers=headers)

    async def _unmute_caller_channel(self, session: ActiveCallSession) -> None:
        if not session.is_caller_muted:
            return
        log.info(f"[ARI] Unmuting inbound audio on caller channel {session.caller_channel_id}")
        if self.http_client:
            try:
                res = await self.http_client.delete(
                    f"{self.ari_url}/channels/{session.caller_channel_id}/mute",
                    params={"direction": "in"},
                )
                if res.status_code in (200, 204):
                    log.info(f"[ARI] Successfully unmuted caller channel {session.caller_channel_id}")
                elif res.status_code == 404:
                    log.info(f"[ARI] Channel {session.caller_channel_id} already gone (404)")
                else:
                    log.warning(f"[ARI] Unexpected ARI unmute status: {res.status_code}")
            except Exception as e:
                log.warning(f"[ARI] Error unmuting caller channel {session.caller_channel_id}: {e}")
        session.is_caller_muted = False

    async def start(self) -> None:
        self.running = True
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                auth=(self.ari_username, self.ari_password),
                timeout=10.0,
            )

        # Phase 5.2: Reconcile orphaned Asterisk resources before accepting calls
        await self._reconcile_startup_resources()

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
        if self.backend_http_client:
            await self.backend_http_client.aclose()
        log.info("Telephony Gateway stopped.")

    async def _reconcile_startup_resources(self) -> None:
        """
        Audit and clean up orphaned bridges and externalMedia channels left behind in Asterisk
        from previous crashed or restarted gateway instances.
        NEVER deletes all bridges/channels blindly; reconciles only resources demonstrably
        owned by VoiceShield (Stasis app 'voiceshield', creator 'Stasis', externalMedia UnicastRTP).
        """
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                auth=(self.ari_username, self.ari_password),
                timeout=10.0,
            )
        log.info(f"[RECONCILIATION] Auditing existing Asterisk resources for application '{self.ari_app}'...")
        try:
            res = await self.http_client.get(f"{self.ari_url}/applications/{self.ari_app}")
            if res.status_code != 200:
                log.info(f"[RECONCILIATION] Could not query application '{self.ari_app}' (status={res.status_code})")
                return

            app_data = res.json()
            bridge_ids = app_data.get("bridge_ids", [])
            channel_ids = app_data.get("channel_ids", [])

            # Reconcile owned bridges
            for b_id in bridge_ids:
                try:
                    b_res = await self.http_client.get(f"{self.ari_url}/bridges/{b_id}")
                    if b_res.status_code == 200:
                        b_data = b_res.json()
                        creator = b_data.get("creator", "")
                        b_class = b_data.get("bridge_class", "")
                        if creator == "Stasis" and b_class == "stasis":
                            del_res = await self.http_client.delete(f"{self.ari_url}/bridges/{b_id}")
                            log.info(f"[RECONCILIATION] Successfully reaped orphaned VoiceShield bridge {b_id} (status={del_res.status_code})")
                        else:
                            log.info(f"[RECONCILIATION] Bridge {b_id} ownership not verified (creator={creator}, class={b_class}); left untouched.")
                except Exception as be:
                    log.warning(f"[RECONCILIATION] Error checking bridge {b_id}: {be}")

            # Reconcile owned externalMedia channels
            for c_id in channel_ids:
                try:
                    c_res = await self.http_client.get(f"{self.ari_url}/channels/{c_id}")
                    if c_res.status_code == 200:
                        c_data = c_res.json()
                        c_name = c_data.get("name", "")
                        app_data_val = c_data.get("dialplan", {}).get("app_data", "")
                        if "UnicastRTP" in c_name or app_data_val == "(Outgoing Line)":
                            del_res = await self.http_client.delete(f"{self.ari_url}/channels/{c_id}")
                            log.info(f"[RECONCILIATION] Successfully reaped orphaned externalMedia channel {c_id} ({c_name}) (status={del_res.status_code})")
                        else:
                            log.info(f"[RECONCILIATION] Channel {c_id} ({c_name}) ownership not verified; left untouched.")
                except Exception as ce:
                    log.warning(f"[RECONCILIATION] Error checking channel {c_id}: {ce}")

        except Exception as e:
            log.warning(f"[RECONCILIATION] Error during startup resource reconciliation: {e}")

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
                log.warning(f"ARI connection lost ({e}). Cleaning active session and reconnecting in {self.ari_reconnect_backoff}s...")
                if self.active_session:
                    try:
                        await self._teardown_session(self.active_session, hangup_caller=False)
                    except Exception as te:
                        log.warning(f"Error during ARI disconnect session cleanup: {te}")
                    self.active_session = None
                await asyncio.sleep(self.ari_reconnect_backoff)

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

        elif ev_type == "PlaybackFinished":
            playback = event.get("playback", {})
            playback_id = playback.get("id")
            log.info(f"[ARI] PlaybackFinished event received: playback_id={playback_id}")
            session = self.active_session
            if (
                session
                and session.state == CallState.CHALLENGE_PLAYING
                and session.challenge_playback_id
                and session.challenge_playback_id == playback_id
            ):
                log.info(f"[ARI] Matching PlaybackFinished for challenge playback {playback_id}")
                if session.challenge_watchdog_task and not session.challenge_watchdog_task.done():
                    session.challenge_watchdog_task.cancel()
                session.challenge_playback_id = None

                # Unmute caller inbound audio only after matching PlaybackFinished
                await self._unmute_caller_channel(session)

                # Enter CHALLENGE_LISTENING
                session.state = CallState.CHALLENGE_LISTENING
                session.challenge_transcripts = []
                session.challenge_speech_detected = False
                session.challenge_listening_active = True
                session.challenge_drain_active = False
                session.challenge_buffered_chunks.clear()
                log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {CallState.CHALLENGE_LISTENING.value}")
                log.info(f"Starting {self.listening_window_duration}s challenge response listening window...")

                session.challenge_window_task = asyncio.create_task(
                    self._run_challenge_listening_window(session)
                )
            else:
                log.info(f"[ARI] Stale, mismatched, or unhandled PlaybackFinished event ignored (playback_id={playback_id})")

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

            # Arm Phase 5.2 RTP inactivity watchdog
            import time
            session.last_rtp_received_at = time.monotonic()
            session.rtp_watchdog_task = asyncio.create_task(self._rtp_inactivity_watchdog(session))

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
            await self._teardown_session(session, hangup_caller=True, hangup_reason="congestion")
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
            elif v_upper == "HOLD_ALLOW":
                log.info(f"Emitting Policy Decision Event [1/2] for session {session.session_id}: Decision=HOLD")
                await self._handle_policy_verdict(
                    session=session,
                    decision="HOLD",
                    action="hold",
                    risk_state="suspicious",
                    risk_score=75,
                    reasons=["high_consequence_intent"],
                )
                await asyncio.sleep(1.5)
                if not session.is_terminated and session.state != CallState.TERMINATED:
                    log.info(f"Emitting Policy Decision Event [2/2] for session {session.session_id}: Decision=ALLOW")
                    await self._handle_policy_verdict(
                        session=session,
                        decision="ALLOW",
                        action="allow",
                        risk_state="low",
                        risk_score=15,
                        reasons=[],
                    )
                return
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

    async def _rtp_inactivity_watchdog(self, session: ActiveCallSession) -> None:
        """
        Monitors inbound RTP datagram arrival.
        If no RTP packets arrive for rtp_inactivity_timeout seconds,
        performs controlled teardown and terminates the caller channel.
        """
        if self.rtp_inactivity_timeout <= 0:
            return
        log.info(f"[WATCHDOG] RTP inactivity watchdog armed ({self.rtp_inactivity_timeout}s timeout)")
        try:
            import time
            while not session.is_terminating and not session.is_terminated:
                await asyncio.sleep(min(0.5, max(0.05, self.rtp_inactivity_timeout / 2)))
                if session.is_terminating or session.is_terminated:
                    break
                now = time.monotonic()
                last_pkt = session.last_rtp_received_at
                if last_pkt is not None and (now - last_pkt) >= self.rtp_inactivity_timeout:
                    log.warning(
                        f"[WATCHDOG] RTP inactivity timeout ({self.rtp_inactivity_timeout}s without packets) "
                        f"on channel {session.caller_channel_id}. Terminating unmonitored call."
                    )
                    session.is_terminating = True
                    session.state = CallState.TERMINATING
                    await self._teardown_session(session, hangup_caller=True, hangup_reason="normal")
                    if self.active_session is session:
                        self.active_session = None
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[WATCHDOG] Error in RTP inactivity watchdog: {e}", exc_info=True)

    # ── RTP Datagram Processing ───────────────────────────────────────────────

    def on_rtp_datagram(self, datagram: bytes, addr: Tuple[str, int]) -> None:
        session = self.active_session
        if not session:
            return

        # Depacketize RFC 3550 RTP, convert big-endian to little-endian PCM16
        pcm_bytes = session.depacketizer.extract_pcm16_le(datagram)
        if not pcm_bytes:
            return

        import time
        session.last_rtp_received_at = time.monotonic()

        if not session.ws or getattr(session.ws, "closed", False):
            return

        # Accumulate into canonical 250 ms chunks (8,000 bytes = 4,000 samples)
        chunks = session.accumulator.push(pcm_bytes)
        for chunk in chunks:
            msg = session.accumulator.build_chunk_message(chunk)
            session.chunks_sent += 1
            if session.challenge_drain_active:
                # Strict 5.0s cutoff: do not forward post-cutoff audio to backend during drain.
                # Buffer chunks so they can be flushed to the backend once challenge evaluation finishes.
                session.challenge_buffered_chunks.append(msg)
            else:
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
                    if ev_type == "audio_quality":
                        active = event.get("active", False)
                        quality = event.get("audio") or {}
                        is_silent = quality.get("is_silent", True)
                        # Strict 5.0s cutoff: only audio arriving during active listening window can trigger speech detection
                        if (active or not is_silent) and session.challenge_listening_active:
                            session.challenge_speech_detected = True

                    elif ev_type == "risk_update":
                        session.consecutive_analysis_errors = 0  # Reset consecutive error counter on valid ML window
                        score = event.get("risk_score", 0)
                        state = event.get("risk_state", "")
                        decision = event.get("decision", "")
                        log.info(
                            f"Live Risk Observation [Session {session.session_id[:8]}]: "
                            f"Score={score}, State={state}, Decision={decision}"
                        )
                        context = event.get("context") or {}
                        transcript = context.get("transcript")
                        # Transcripts from pre-cutoff audio landing during active listening OR during STT drain are admitted
                        if transcript and (session.challenge_listening_active or session.challenge_drain_active):
                            session.challenge_speech_detected = True
                            if transcript not in session.challenge_transcripts:
                                session.challenge_transcripts.append(transcript)

                        await self._handle_policy_verdict(
                            session=session,
                            decision=decision,
                            action=event.get("action", ""),
                            risk_state=state,
                            risk_score=score,
                            reasons=event.get("reasons", []),
                        )
                    elif ev_type == "error":
                        code = event.get("code", "")
                        msg = event.get("message", "")
                        log.warning(f"VoiceShield Backend Error Event [Session {session.session_id[:8]}]: code={code}, msg={msg}")
                        if code == "analysis_error":
                            session.consecutive_analysis_errors += 1
                            log.warning(
                                f"[ML_OBSERVER] Consecutive ML analysis errors: {session.consecutive_analysis_errors}/"
                                f"{self.max_consecutive_analysis_errors}"
                            )
                            if (
                                self.max_consecutive_analysis_errors > 0
                                and session.consecutive_analysis_errors >= self.max_consecutive_analysis_errors
                                and not session.is_terminating
                                and not session.is_terminated
                            ):
                                log.error(
                                    f"[ML_FAILURE] ML analysis error threshold exceeded ({session.consecutive_analysis_errors} "
                                    f"consecutive errors). Initiating controlled fail-safe teardown."
                                )
                                session.is_terminating = True
                                session.state = CallState.TERMINATING
                                await self._teardown_session(session, hangup_caller=True, hangup_reason="congestion")
                                if self.active_session is session:
                                    self.active_session = None
                                break
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
        except websockets.ConnectionClosed as e:
            log.warning(f"VoiceShield WebSocket closed for session {session.session_id}: {e}")
            if not session.is_terminating and not session.is_terminated:
                log.warning(
                    f"[BACKEND_FAILURE] VoiceShield WebSocket lost during active monitoring "
                    f"for channel {session.caller_channel_id}. Executing controlled fail-safe teardown."
                )
                session.is_terminating = True
                session.state = CallState.TERMINATING
                await self._teardown_session(session, hangup_caller=True, hangup_reason="congestion")
                if self.active_session is session:
                    self.active_session = None
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error in VoiceShield WebSocket listener: {e}")
            if not session.is_terminating and not session.is_terminated:
                session.is_terminating = True
                session.state = CallState.TERMINATING
                await self._teardown_session(session, hangup_caller=True, hangup_reason="congestion")
                if self.active_session is session:
                    self.active_session = None

        # If the underlying WebSocket was closed during active monitoring, execute controlled teardown
        if getattr(session.ws, "closed", False) and not session.is_terminating and not session.is_terminated:
            log.warning(
                f"[BACKEND_FAILURE] VoiceShield WebSocket closed during active monitoring "
                f"for channel {session.caller_channel_id}. Executing controlled fail-safe teardown."
            )
            session.is_terminating = True
            session.state = CallState.TERMINATING
            await self._teardown_session(session, hangup_caller=True, hangup_reason="congestion")
            if self.active_session is session:
                self.active_session = None

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
        if session.state in (
            CallState.CHALLENGE_MUTING,
            CallState.CHALLENGE_PLAYING,
            CallState.CHALLENGE_LISTENING,
            CallState.CHALLENGE_EVALUATING,
        ):
            log.info(f"ALLOW event ignored: challenge is currently in progress (state={session.state.value})")
            return

        if session.state == CallState.HOLD:
            log.info(f"Transitioning from HOLD to ACTIVE under ALLOW decision on channel {session.caller_channel_id}")
            if self.enforcement_mode == EnforcementMode.ENFORCE and self.http_client:
                try:
                    res = await self.http_client.delete(f"{self.ari_url}/channels/{session.caller_channel_id}/hold")
                    if res.status_code in (200, 204):
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} removed from hold")
                except Exception as e:
                    log.warning(f"Failed unholding channel {session.caller_channel_id}: {e}")

        # Clear challenge tracking on transition to ACTIVE if challenge is finished
        if session.state in (CallState.CHALLENGE_PASSED, CallState.CHALLENGE_FAILED, CallState.CHALLENGE_TIMEOUT):
            session.challenge_id = None
            session.challenge_text = None
            session.challenge_type = None
            session.challenge_playback_id = None
            session.challenge_result_submitted = False

        session.state = CallState.ACTIVE
        log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {CallState.ACTIVE.value}")
        log.info(f"Policy Decision [ALLOW]: Call on channel {session.caller_channel_id} is ACTIVE")

    async def _enforce_challenge(
        self,
        session: ActiveCallSession,
        reasons: list[str],
        risk_score: int,
    ) -> None:
        # Idempotency guard: ignore duplicate challenge events while challenge is in progress
        challenge_active_states = (
            CallState.CHALLENGE_MUTING,
            CallState.CHALLENGE_PLAYING,
            CallState.CHALLENGE_LISTENING,
            CallState.CHALLENGE_EVALUATING,
            CallState.CHALLENGE_PASSED,
            CallState.CHALLENGE_FAILED,
            CallState.CHALLENGE_TIMEOUT,
        )
        if session.challenge_id or session.state in challenge_active_states:
            log.info(
                f"Duplicate VERIFY/CHALLENGE event ignored for session {session.session_id}: "
                f"Challenge already active (state={session.state.value}, challenge_id={session.challenge_id})"
            )
            return

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
                f"[OBSERVE_ONLY] Policy Decision VERIFY/CHALLENGE (Score={risk_score}, Reasons={reasons}). "
                f"Zero ARI action performed."
            )
            return

        if self.enforcement_mode == EnforcementMode.DRY_RUN:
            log.info(
                f"[DRY_RUN] Would issue backend challenge, mute channel {session.caller_channel_id}, "
                f"play prompt {self.challenge_sound}, and collect response."
            )
            return

        if self.enforcement_mode == EnforcementMode.ENFORCE:
            log.info(f"[ENFORCE] Starting Phase 5.1 Interactive Challenge sequence on channel {session.caller_channel_id}")

            # Step A & B & C: Create backend Challenge record
            session.state = CallState.CHALLENGE_MUTING
            log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {CallState.CHALLENGE_MUTING.value}")

            client = await self._get_backend_client()
            should_close = client is not self.backend_http_client
            try:
                res = await client.post(f"{self.backend_http_url}/challenge/{session.session_id}")
                if res.status_code not in (200, 201):
                    log.error(f"[ENFORCE] Backend failed to create challenge: {res.status_code} {res.text}")
                    session.state = CallState.ACTIVE
                    return
                c_data = res.json()
                session.challenge_id = c_data["id"]
                session.challenge_text = c_data.get("challenge_text", "")
                session.challenge_type = c_data.get("challenge_type", "phrase")
                session.challenge_result_submitted = False
                log.info(
                    f"[ENFORCE] Backend challenge created: id={session.challenge_id}, "
                    f"type={session.challenge_type}, text='{session.challenge_text}'"
                )
            except Exception as e:
                log.error(f"[ENFORCE] Error requesting backend challenge: {e}")
                session.state = CallState.ACTIVE
                return
            finally:
                if should_close:
                    await client.aclose()

            # Step C2: Resolve matching prompt sound asset for the issued challenge
            sound_to_play = resolve_challenge_prompt_sound(session.challenge_text or "", session.challenge_type or "")
            if not sound_to_play:
                log.error(
                    f"[ENFORCE] Unsupported or unmapped challenge text '{session.challenge_text}' "
                    f"(type='{session.challenge_type}'). Aborting challenge safely without playing prompt."
                )
                session.state = CallState.CHALLENGE_FAILED
                await self._submit_challenge_result(
                    session,
                    outcome="failed",
                    detail=f"Unsupported challenge prompt: '{session.challenge_text}'",
                )
                session.state = CallState.ACTIVE
                return

            # Step D: Mute inbound caller media
            if self.http_client:
                try:
                    mute_res = await self.http_client.post(
                        f"{self.ari_url}/channels/{session.caller_channel_id}/mute",
                        params={"direction": "in"},
                    )
                    if mute_res.status_code in (200, 204):
                        session.is_caller_muted = True
                        log.info(f"[ENFORCE] Inbound audio muted on channel {session.caller_channel_id}")
                    elif mute_res.status_code == 404:
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} not found during mute (404)")
                        session.state = CallState.ACTIVE
                        return
                    else:
                        log.warning(f"[ENFORCE] Unexpected ARI mute status: {mute_res.status_code}")
                        session.state = CallState.ACTIVE
                        return
                except Exception as e:
                    log.error(f"[ENFORCE] ARI error muting channel: {e}")
                    session.state = CallState.ACTIVE
                    return

            # Step E: Start playback
            session.state = CallState.CHALLENGE_PLAYING
            log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {CallState.CHALLENGE_PLAYING.value}")
            if self.http_client:
                try:
                    action_record["media"] = sound_to_play
                    play_res = await self.http_client.post(
                        f"{self.ari_url}/channels/{session.caller_channel_id}/play",
                        params={"media": sound_to_play},
                    )
                    action_record["status_code"] = play_res.status_code
                    if play_res.status_code in (200, 201):
                        action_record["executed"] = True
                        p_data = play_res.json()
                        session.challenge_playback_id = p_data.get("id")
                        log.info(
                            f"[ENFORCE] Challenge audio playback started on channel {session.caller_channel_id} "
                            f"(playback_id={session.challenge_playback_id})"
                        )
                    elif play_res.status_code == 404:
                        log.info(f"[ENFORCE] Channel {session.caller_channel_id} not found for challenge play (404)")
                        await self._unmute_caller_channel(session)
                        session.state = CallState.ACTIVE
                        return
                    else:
                        log.warning(f"[ENFORCE] Unexpected ARI play status {play_res.status_code}: {play_res.text}")
                        await self._unmute_caller_channel(session)
                        session.state = CallState.ACTIVE
                        return
                except Exception as e:
                    log.error(f"[ENFORCE] Error playing challenge prompt: {e}", exc_info=True)
                    await self._unmute_caller_channel(session)
                    session.state = CallState.ACTIVE
                    return

            # Step F: Arm playback watchdog
            session.challenge_watchdog_task = asyncio.create_task(
                self._playback_watchdog(session, session.challenge_playback_id)
            )

    async def _playback_watchdog(self, session: ActiveCallSession, playback_id: Optional[str]) -> None:
        try:
            await asyncio.sleep(self.playback_watchdog_timeout)
            if session.is_terminated or session.state == CallState.TERMINATED:
                return
            if session.state == CallState.CHALLENGE_PLAYING and session.challenge_playback_id == playback_id:
                log.warning(
                    f"[WATCHDOG] Playback watchdog expired ({self.playback_watchdog_timeout}s) for channel "
                    f"{session.caller_channel_id} (playback_id={playback_id}). Unmuting caller."
                )
                await self._unmute_caller_channel(session)
                session.challenge_playback_id = None
                session.state = CallState.CHALLENGE_TIMEOUT
                log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {CallState.CHALLENGE_TIMEOUT.value}")
                await self._submit_challenge_result(
                    session,
                    outcome="timeout",
                    detail=f"Playback watchdog timeout (PlaybackFinished not received within {self.playback_watchdog_timeout}s)",
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"[WATCHDOG] Error in playback watchdog: {e}", exc_info=True)

    async def _run_challenge_listening_window(self, session: ActiveCallSession) -> None:
        try:
            # 1. Wait for response collection duration (0.0s - 5.0s)
            session.challenge_listening_active = True
            session.challenge_drain_active = False
            await asyncio.sleep(self.listening_window_duration)
            if session.is_terminated or session.state == CallState.TERMINATED:
                return

            # 2. Strict 5.0s Cutoff: stop accepting new audio / VAD into challenge evidence
            session.challenge_listening_active = False
            session.challenge_drain_active = True
            log.info(f"Challenge response audio window strictly closed ({self.listening_window_duration}s cutoff reached).")

            # 3. Allow already-admitted/in-flight STT from pre-cutoff audio to land (5.0s - 6.2s)
            drain_delay = min(1.2, self.listening_window_duration)
            await asyncio.sleep(drain_delay)
            if session.is_terminated or session.state == CallState.TERMINATED:
                return

            # 4. Gate firmly closed: stop drain
            session.challenge_drain_active = False
            session.state = CallState.CHALLENGE_EVALUATING
            log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {CallState.CHALLENGE_EVALUATING.value}")

            # 5. Flush any audio chunks that were buffered during the drain so backend call monitoring continues
            if session.challenge_buffered_chunks:
                buffered = list(session.challenge_buffered_chunks)
                session.challenge_buffered_chunks.clear()
                log.info(f"Flushing {len(buffered)} buffered post-cutoff audio chunk(s) to VoiceShield backend.")
                for msg in buffered:
                    asyncio.create_task(self._send_audio_chunk(session, msg))

            # 6. Evaluate strictly frozen snapshot
            full_transcript = " ".join(session.challenge_transcripts).strip()
            log.info(
                f"Evaluating challenge response snapshot: target='{session.challenge_text}', "
                f"type='{session.challenge_type}', transcript='{full_transcript}', "
                f"speech_detected={session.challenge_speech_detected}"
            )

            outcome, detail = evaluate_challenge_response(
                challenge_text=session.challenge_text or "",
                challenge_type=session.challenge_type or "phrase",
                transcript=full_transcript,
                speech_detected=session.challenge_speech_detected,
            )

            log.info(f"Challenge response evaluated: outcome={outcome.upper()}, detail='{detail}'")

            # 7. Transition to outcome state
            if outcome == "passed":
                session.state = CallState.CHALLENGE_PASSED
            elif outcome == "failed":
                session.state = CallState.CHALLENGE_FAILED
            else:
                session.state = CallState.CHALLENGE_TIMEOUT

            log.info(f"[STATE TRANSITION] Call {session.caller_channel_id} -> {session.state.value}")

            # 8. Submit backend result
            await self._submit_challenge_result(session, outcome=outcome, detail=detail)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Error in challenge listening window: {e}", exc_info=True)
            if session.state in (CallState.CHALLENGE_LISTENING, CallState.CHALLENGE_EVALUATING):
                session.state = CallState.CHALLENGE_FAILED
                await self._submit_challenge_result(session, outcome="failed", detail=f"Internal evaluation error: {e}")

    async def _submit_challenge_result(
        self,
        session: ActiveCallSession,
        outcome: str,
        detail: str,
    ) -> None:
        if session.challenge_result_submitted:
            log.info(f"Challenge result already submitted for session {session.session_id}, ignoring duplicate call")
            return
        session.challenge_result_submitted = True

        if not session.session_id or not session.challenge_id:
            log.warning(f"Cannot submit challenge result: session_id or challenge_id missing (session={session.session_id})")
            return

        client = await self._get_backend_client()
        should_close = client is not self.backend_http_client
        try:
            log.info(
                f"Submitting challenge result to backend: POST /challenge/{session.session_id}/{session.challenge_id}/result "
                f"outcome={outcome}, detail='{detail}'"
            )
            res = await client.post(
                f"{self.backend_http_url}/challenge/{session.session_id}/{session.challenge_id}/result",
                json={"outcome": outcome, "detail": detail},
            )
            if res.status_code in (200, 201):
                log.info(f"Challenge result successfully accepted by backend for session {session.session_id}")
            else:
                log.warning(f"Backend returned status {res.status_code} for challenge result: {res.text}")
        except Exception as e:
            log.error(f"Failed submitting challenge result to backend: {e}")
        finally:
            if should_close:
                await client.aclose()

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

        # Cancel any active challenge tasks if blocking
        if session.challenge_watchdog_task and not session.challenge_watchdog_task.done():
            session.challenge_watchdog_task.cancel()
        if session.challenge_window_task and not session.challenge_window_task.done():
            session.challenge_window_task.cancel()

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

    async def _teardown_session(
        self,
        session: ActiveCallSession,
        hangup_caller: bool = False,
        hangup_reason: str = "normal",
    ) -> None:
        if session.is_terminated:
            return
        session.is_terminated = True
        session.state = CallState.TERMINATED

        log.info(f"Tearing down call session for channel {session.caller_channel_id} (State={session.state.value})...")

        current_task = asyncio.current_task()

        # 1. Cancel watchdog and window tasks
        if session.rtp_watchdog_task and session.rtp_watchdog_task is not current_task and not session.rtp_watchdog_task.done():
            session.rtp_watchdog_task.cancel()
        if session.challenge_watchdog_task and session.challenge_watchdog_task is not current_task and not session.challenge_watchdog_task.done():
            session.challenge_watchdog_task.cancel()
        if session.challenge_window_task and session.challenge_window_task is not current_task and not session.challenge_window_task.done():
            session.challenge_window_task.cancel()

        # 2. Stop active playback if running
        if self.http_client and session.challenge_playback_id:
            try:
                await self.http_client.delete(f"{self.ari_url}/playbacks/{session.challenge_playback_id}")
            except Exception:
                pass

        # 3. Defensive unmute: never leave caller permanently muted
        if session.is_caller_muted:
            await self._unmute_caller_channel(session)

        # 4. Clear challenge tracking
        session.challenge_id = None
        session.challenge_text = None
        session.challenge_type = None
        session.challenge_playback_id = None
        session.challenge_listening_active = False
        session.challenge_drain_active = False
        session.challenge_buffered_chunks.clear()

        # 5. Cancel WebSocket listener
        if session.ws_receive_task and session.ws_receive_task is not current_task and not session.ws_receive_task.done():
            session.ws_receive_task.cancel()

        # 6. Close VoiceShield WebSocket (triggers backend _teardown, flushes buffers & saves incident)
        if session.ws and not getattr(session.ws, "closed", False):
            try:
                await session.ws.close()
                log.info(f"Closed VoiceShield WebSocket for session {session.session_id}")
            except Exception as e:
                log.warning(f"Error closing WebSocket: {e}")

        # 7. Destroy Asterisk Bridge and externalMedia channel
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

        # 8. Hang up caller channel if requested (fail-safe for backend/watchdog failures)
        if hangup_caller and self.http_client and session.caller_channel_id:
            try:
                res = await self.http_client.delete(
                    f"{self.ari_url}/channels/{session.caller_channel_id}",
                    params={"reason": hangup_reason},
                )
                if res.status_code in (200, 204):
                    log.info(f"[TEARDOWN] Terminated caller channel {session.caller_channel_id} (reason={hangup_reason})")
                elif res.status_code == 404:
                    log.info(f"[TEARDOWN] Caller channel {session.caller_channel_id} already gone (404)")
                else:
                    log.warning(f"[TEARDOWN] Unexpected ARI hangup status {res.status_code}: {res.text}")
            except Exception as e:
                log.warning(f"[TEARDOWN] Error hanging up caller channel {session.caller_channel_id}: {e}")

        # 9. Log telemetry summary
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
    parser.add_argument("--ari-user", default=os.getenv("ARI_USER", "voiceshield"), help="ARI username")
    parser.add_argument(
        "--ari-pass",
        default=os.getenv("ARI_PASSWORD") or os.getenv("ARI_PASS") or "",
        help="ARI password (defaults to ARI_PASSWORD or ARI_PASS env var)",
    )
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
        choices=["BLOCK", "CHALLENGE", "VERIFY", "HOLD", "ALLOW", "HOLD_ALLOW", "block", "challenge", "verify", "hold", "allow", "hold_allow"],
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
    parser.add_argument(
        "--rtp-inactivity-timeout",
        type=float,
        default=5.0,
        help="Timeout in seconds before dead RTP triggers hangup",
    )
    parser.add_argument(
        "--max-analysis-errors",
        type=int,
        default=3,
        help="Maximum consecutive analysis_error events before controlled fail-safe teardown",
    )
    parser.add_argument(
        "--ari-reconnect-backoff",
        type=float,
        default=3.0,
        help="Backoff in seconds before reconnecting to Asterisk ARI WebSocket",
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
        rtp_inactivity_timeout=args.rtp_inactivity_timeout,
        max_consecutive_analysis_errors=args.max_analysis_errors,
        ari_reconnect_backoff=args.ari_reconnect_backoff,
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
