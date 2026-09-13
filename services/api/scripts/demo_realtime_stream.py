#!/usr/bin/env python3
"""
VoiceShield — Real-Time Audio Streaming & Live Demonstration CLI (Phase 1.7)
=============================================================================
Streams real audio (microphone or WAV/FLAC files) in real-time through the
WebSocket gateway to the complete VoiceShield ML & Policy pipeline:
  Real Audio (16 kHz mono int16 PCM)
      ↓
  WebSocket Gateway (/ws/sessions/{id})
      ↓
  StreamWindower (64,608 / 16,000 / 80,608)
      ↓
  AASIST-L Authenticity + ECAPA-TDNN Identity + faster-whisper Context
      ↓
  Risk Engine (multi-modal fusion)
      ↓
  Security Policy (ALLOW / CHALLENGE / HOLD / BLOCK)
      ↓
  Live Dashboard / Telemetry Console

Usage Examples:
  # 1. In-process demo using bundled InTheWild spoof sample:
  python services/api/scripts/demo_realtime_stream.py --sample spoof --in-process

  # 2. In-process demo using bundled InTheWild bona-fide sample:
  python services/api/scripts/demo_realtime_stream.py --sample bonafide --in-process

  # 3. Live microphone streaming (in-process or against server):
  python services/api/scripts/demo_realtime_stream.py --mic --max-seconds 15 --in-process

  # 4. Stream against live running server:
  python services/api/scripts/demo_realtime_stream.py --file path/to/sample.wav \
      --url ws://127.0.0.1:8000 --http-url http://127.0.0.1:8000

  # 5. Automated challenge demonstration (issue at 5s, pass at 8s):
  python services/api/scripts/demo_realtime_stream.py --sample spoof --in-process \
      --challenge-at 5.0 --resolve-at 8.0 --resolve-outcome passed
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Generator, List, Optional, Tuple

# Ensure repository and API roots are in sys.path
REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(API_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Default to real ML mode unless explicitly requested otherwise
if "PIPELINE_MODE" not in os.environ:
    os.environ["PIPELINE_MODE"] = "real_ml"
if "MODEL_DIR" not in os.environ:
    os.environ["MODEL_DIR"] = str(API_ROOT / "models")

from app.core.security import create_access_token
from app.ml.preprocessing.ingest import (
    AudioIngestError,
    iter_pcm_chunks,
    load_audio_file,
)

# ANSI terminal styling
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_CYAN = "\033[36m"
COLOR_MAGENTA = "\033[35m"
COLOR_GRAY = "\033[90m"

SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # 16-bit signed integer PCM

PRESET_SAMPLES = {
    "spoof": REPO_ROOT / "data" / "external" / "InTheWild" / "release_in_the_wild" / "1.wav",
    "bonafide": REPO_ROOT / "data" / "external" / "InTheWild" / "release_in_the_wild" / "45.wav",
}


def log(msg: str, tag: str = "INFO", color: str = COLOR_CYAN) -> None:
    now = time.strftime("%H:%M:%S")
    print(f"{COLOR_GRAY}[{now}]{COLOR_RESET} {color}[{tag}]{COLOR_RESET} {msg}", flush=True)


def format_decision(decision: str) -> str:
    dec = (decision or "ALLOW").upper()
    if dec == "ALLOW":
        return f"{COLOR_GREEN}{COLOR_BOLD}ALLOW{COLOR_RESET}"
    if dec == "CHALLENGE":
        return f"{COLOR_YELLOW}{COLOR_BOLD}CHALLENGE{COLOR_RESET}"
    if dec == "HOLD":
        return f"{COLOR_MAGENTA}{COLOR_BOLD}HOLD{COLOR_RESET}"
    if dec == "BLOCK":
        return f"{COLOR_RED}{COLOR_BOLD}BLOCK{COLOR_RESET}"
    return dec


def format_risk_state(state: str, score: Optional[int]) -> str:
    s = (state or "LOW").upper()
    score_str = f"({score})" if score is not None else ""
    if s == "LOW":
        return f"{COLOR_GREEN}{s} {score_str}{COLOR_RESET}"
    if s in ("SUSPICIOUS", "MEDIUM"):
        return f"{COLOR_YELLOW}{s} {score_str}{COLOR_RESET}"
    if s in ("HIGH", "CRITICAL"):
        return f"{COLOR_RED}{COLOR_BOLD}{s} {score_str}{COLOR_RESET}"
    return f"{s} {score_str}"


def display_telemetry(update: Dict[str, Any], elapsed: float) -> None:
    """Print formatted live telemetry for a risk_update or detected_event."""
    ev_type = update.get("type", "")
    if ev_type == "risk_update":
        score = update.get("risk_score")
        state = update.get("risk_state", "")
        dec = update.get("decision", "ALLOW")
        auth = update.get("authenticity") or {}
        ident = update.get("identity") or {}
        ctx = update.get("context") or {}

        spoof_prob = auth.get("spoof_probability")
        spoof_str = f"{spoof_prob:.4f}" if isinstance(spoof_prob, float) else "N/A"
        auth_mode = auth.get("pipeline_mode", "mock")
        auth_model = auth.get("model_version", "AASIST")

        sim_score = ident.get("similarity_score")
        sim_str = f"{sim_score:.4f}" if isinstance(sim_score, float) else "N/A"

        transcript = (ctx.get("transcript") or "").strip()
        if len(transcript) > 40:
            transcript = transcript[:37] + "..."
        triggers = ctx.get("trigger_words") or []

        reasons = update.get("reasons") or []
        reason_str = f" | Reasons: {', '.join(reasons)}" if reasons else ""

        print(
            f"{COLOR_BOLD}T+{elapsed:05.1f}s{COLOR_RESET} │ "
            f"Decision: {format_decision(dec)} │ "
            f"Risk: {format_risk_state(state, score)} │ "
            f"Authenticity (AASIST): {COLOR_BOLD}{spoof_str}{COLOR_RESET} [{auth_mode}] │ "
            f"Speaker Sim: {sim_str} │ "
            f"STT: \"{transcript or '<silence>'}\"{reason_str}",
            flush=True,
        )
    elif ev_type == "challenge_started":
        print(
            f"{COLOR_YELLOW}{COLOR_BOLD}[CHALLENGE STARTED]{COLOR_RESET} "
            f"Type: {update.get('challenge_type')} | Prompt: \"{update.get('challenge_text')}\"",
            flush=True,
        )
    elif ev_type == "challenge_result":
        outcome = update.get("outcome", "")
        col = COLOR_GREEN if outcome == "passed" else COLOR_RED
        print(
            f"{col}{COLOR_BOLD}[CHALLENGE RESULT]{COLOR_RESET} "
            f"Outcome: {outcome.upper()} | New Risk: {update.get('new_risk_score')}",
            flush=True,
        )
    elif ev_type == "alert":
        print(
            f"{COLOR_RED}{COLOR_BOLD}[ALERT: {update.get('severity', '').upper()}]{COLOR_RESET} "
            f"{update.get('title')}: {update.get('message')}",
            flush=True,
        )


def capture_mic_chunks(
    chunk_ms: int = 250,
    device: str = ":0",
    max_seconds: Optional[float] = None,
) -> Generator[bytes, None, None]:
    """Capture 16 kHz mono signed 16-bit PCM chunks directly from live microphone via ffmpeg."""
    ffmpeg_bin = (
        shutil.which("ffmpeg")
        or "/opt/homebrew/bin/ffmpeg"
        or "/usr/local/bin/ffmpeg"
        or "ffmpeg"
    )
    bytes_per_chunk = int(SAMPLE_RATE * (chunk_ms / 1000.0) * BYTES_PER_SAMPLE)

    cmd = [
        ffmpeg_bin,
        "-f", "avfoundation",
        "-i", device,
        "-ar", str(SAMPLE_RATE),
        "-ac", "1",
        "-f", "s16le",
        "-loglevel", "error",
        "pipe:1",
    ]

    log(f"Starting microphone capture: {' '.join(cmd[:5])} ...", "MIC", COLOR_GREEN)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=bytes_per_chunk * 10,
    )

    t0 = time.time()
    try:
        while True:
            if max_seconds and (time.time() - t0) >= max_seconds:
                break
            raw = proc.stdout.read(bytes_per_chunk)
            if not raw:
                break
            if len(raw) == bytes_per_chunk:
                yield raw
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except Exception:
            proc.kill()
        log("Microphone capture stopped.", "MIC", COLOR_YELLOW)


def build_in_process_session(session_id: str, user_id: str):
    """Build in-process TestClient with real gateway, real ML models, and lightweight mock DB."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.websocket import gateway as gw
    from app.models.models import Session, Policy, Challenge
    from app.risk.policy import DEFAULT_POLICY_CONFIG

    challenges: Dict[str, Any] = {}

    class _MockResult:
        def __init__(self, val):
            self._val = val
        def scalar_one_or_none(self):
            return self._val
        def scalars(self):
            return self
        def all(self):
            return [self._val] if self._val else []

    class _MockDB:
        def __init__(self):
            self.query_count = 0

        async def execute(self, statement):
            self.query_count += 1
            s_str = str(statement)
            if "FROM sessions" in s_str:
                return _MockResult(SimpleNamespace(id=session_id, user_id=user_id, state="active"))
            if "FROM policies" in s_str:
                return _MockResult(SimpleNamespace(id="pol-1", config=DEFAULT_POLICY_CONFIG, is_active=True))
            if "FROM challenges" in s_str or "challenges" in s_str:
                params = getattr(statement, "_params", {}) or {}
                for cid, ch in challenges.items():
                    if cid in str(statement) or any(cid in str(v) for v in params.values()):
                        return _MockResult(ch)
                if challenges:
                    return _MockResult(list(challenges.values())[-1])
                return _MockResult(None)

        def add(self, obj):
            if isinstance(obj, Challenge):
                if not obj.id:
                    obj.id = str(uuid.uuid4())
                if not getattr(obj, "created_at", None):
                    from datetime import datetime, timezone
                    obj.created_at = datetime.now(timezone.utc)
                challenges[obj.id] = obj

        async def commit(self):
            pass

        async def refresh(self, obj):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    gw.AsyncSessionLocal = lambda: _MockDB()
    from app.websocket import pipeline as pipe
    pipe.AsyncSessionLocal = lambda: _MockDB()

    app = FastAPI(title="VoiceShield In-Process Stream")
    app.include_router(gw.router)

    from app.api import challenge as ch_router
    from app.api.deps import get_current_user
    from app.core.database import get_db

    async def _mock_get_db():
        yield _MockDB()

    async def _mock_get_user():
        return SimpleNamespace(id=user_id, email="test@voiceshield.ai", is_active=True)

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_current_user] = _mock_get_user
    app.include_router(ch_router.router, prefix="/api/v1/challenge")

    token = create_access_token(user_id)
    return TestClient(app), token, challenges


def stream_audio_session(
    source_type: str,
    file_path: Optional[str] = None,
    chunk_ms: int = 250,
    mic_device: str = ":0",
    max_seconds: Optional[float] = None,
    realtime: bool = True,
    in_process: bool = True,
    server_url: str = "ws://127.0.0.1:8000",
    http_url: str = "http://127.0.0.1:8000",
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    token: Optional[str] = None,
    challenge_at: Optional[float] = None,
    resolve_at: Optional[float] = None,
    resolve_outcome: str = "passed",
) -> Dict[str, Any]:
    """Execute complete streaming session and return collected telemetry and results."""
    session_id = session_id or str(uuid.uuid4())
    user_id = user_id or str(uuid.uuid4())

    log(f"Session ID: {session_id}", "SETUP")
    log(f"User ID:    {user_id}", "SETUP")
    log(f"Chunk Size: {chunk_ms} ms (pacing={'realtime' if realtime else 'unpaced'})", "SETUP")

    events_received: List[Dict[str, Any]] = []
    chunks_sent = 0
    bytes_sent = 0
    active_challenge_id: Optional[str] = None
    challenge_issued = False
    challenge_resolved = False

    if in_process:
        log("Running in-process against real VoiceShield ML models...", "SETUP", COLOR_GREEN)
        from app.websocket import gateway as gw
        client, token, challenge_store = build_in_process_session(session_id, user_id)

        ws_url = f"/ws/sessions/{session_id}?token={token}"
        t_start = time.perf_counter()

        with client.websocket_connect(ws_url) as ws:
            init_msg = ws.receive_json()
            events_received.append(init_msg)
            log(f"Connected: mode={init_msg.get('pipeline_mode')} versions={init_msg.get('model_versions')}", "WS")

            # Prepare audio generator
            if source_type == "mic":
                chunk_gen = capture_mic_chunks(chunk_ms, mic_device, max_seconds)
            else:
                if not file_path or not os.path.exists(file_path):
                    raise FileNotFoundError(f"Audio file not found: {file_path}")
                audio_pcm, meta = load_audio_file(file_path)
                if max_seconds:
                    audio_pcm = audio_pcm[: int(SAMPLE_RATE * max_seconds)]
                log(f"Loaded {meta.duration_s:.2f}s audio from {Path(file_path).name}", "AUDIO")
                chunk_gen = iter_pcm_chunks(audio_pcm, chunk_ms)

            # Stream loop
            for seq, chunk in enumerate(chunk_gen):
                now_elapsed = time.perf_counter() - t_start

                # Trigger automated challenge if configured
                if challenge_at and now_elapsed >= challenge_at and not challenge_issued:
                    challenge_issued = True
                    log(f"Issuing challenge at T+{now_elapsed:.2f}s...", "CHALLENGE", COLOR_YELLOW)
                    res = client.post(
                        f"/api/v1/challenge/{session_id}",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if res.status_code == 200:
                        ch_data = res.json()
                        active_challenge_id = ch_data.get("id")
                        log(f"Issued Challenge {active_challenge_id}: '{ch_data.get('challenge_text')}'", "CHALLENGE")

                # Resolve automated challenge if configured
                if (
                    resolve_at
                    and now_elapsed >= resolve_at
                    and active_challenge_id
                    and not challenge_resolved
                ):
                    challenge_resolved = True
                    log(f"Resolving challenge {active_challenge_id} with outcome '{resolve_outcome}'...", "CHALLENGE", COLOR_YELLOW)
                    res = client.post(
                        f"/api/v1/challenge/{session_id}/{active_challenge_id}/result",
                        json={"outcome": resolve_outcome, "detail": "Automated CLI verification test"},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if res.status_code == 200:
                        log("Challenge resolved successfully.", "CHALLENGE", COLOR_GREEN)

                # Send chunk
                b64_data = base64.b64encode(chunk).decode("ascii")
                ws.send_json({"type": "audio_chunk", "seq": seq, "data": b64_data})
                chunks_sent += 1
                bytes_sent += len(chunk)

                # Drain any messages ready on the socket non-blockingly
                if hasattr(ws, "_send_queue"):
                    while not ws._send_queue.empty():
                        msg = ws.receive_json()
                        events_received.append(msg)
                        display_telemetry(msg, time.perf_counter() - t_start)

                if realtime and source_type != "mic":
                    time.sleep(chunk_ms / 1000.0)

            log("Audio stream transmission complete. Flushing analysis barrier...", "STREAM")

            # Allow any in-flight async inference task to settle
            for _ in range(25):
                st = gw.manager.get_state(session_id)
                if st and st.pending_audio_tasks > 0:
                    time.sleep(0.2)
                    if hasattr(ws, "_send_queue"):
                        while not ws._send_queue.empty():
                            msg = ws.receive_json()
                            events_received.append(msg)
                            display_telemetry(msg, time.perf_counter() - t_start)
                else:
                    break

            # Flusher barrier via ping/pong rounds
            for _ in range(250):
                ws.send_json({"type": "ping"})
                rounds_drained = 0
                for _ in range(5000):
                    msg = ws.receive_json()
                    if msg.get("type") == "pong":
                        break
                    events_received.append(msg)
                    rounds_drained += 1
                    display_telemetry(msg, time.perf_counter() - t_start)
                if rounds_drained == 0:
                    break

        total_elapsed = time.perf_counter() - t_start
    else:
        # Remote WebSocket streaming
        import websockets.sync.client as ws_sync
        token = token or create_access_token(user_id)
        ws_endpoint = f"{server_url}/ws/sessions/{session_id}?token={token}"
        log(f"Connecting to {ws_endpoint} ...", "WS")

        t_start = time.perf_counter()
        with ws_sync.connect(ws_endpoint) as ws:
            init_msg = json.loads(ws.recv())
            events_received.append(init_msg)
            log(f"Connected: mode={init_msg.get('pipeline_mode')}", "WS")

            if source_type == "mic":
                chunk_gen = capture_mic_chunks(chunk_ms, mic_device, max_seconds)
            else:
                audio_pcm, meta = load_audio_file(file_path)
                if max_seconds:
                    audio_pcm = audio_pcm[: int(SAMPLE_RATE * max_seconds)]
                chunk_gen = iter_pcm_chunks(audio_pcm, chunk_ms)

            for seq, chunk in enumerate(chunk_gen):
                b64_data = base64.b64encode(chunk).decode("ascii")
                ws.send(json.dumps({"type": "audio_chunk", "seq": seq, "data": b64_data}))
                chunks_sent += 1
                bytes_sent += len(chunk)

                # Try to receive events without hanging
                try:
                    while True:
                        msg_str = ws.recv(timeout=0.01)
                        ev_data = json.loads(msg_str)
                        events_received.append(ev_data)
                        display_telemetry(ev_data, time.perf_counter() - t_start)
                except TimeoutError:
                    pass

                if realtime:
                    time.sleep(chunk_ms / 1000.0)

            # Drain remainder
            time.sleep(1.0)
            try:
                while True:
                    msg_str = ws.recv(timeout=1.0)
                    ev_data = json.loads(msg_str)
                    events_received.append(ev_data)
                    display_telemetry(ev_data, time.perf_counter() - t_start)
            except TimeoutError:
                pass

        total_elapsed = time.perf_counter() - t_start

    # Build summary
    risk_events = [e for e in events_received if e.get("type") == "risk_update"]
    auth_scores = [
        (e.get("authenticity") or {}).get("spoof_probability")
        for e in risk_events
        if isinstance((e.get("authenticity") or {}).get("spoof_probability"), (int, float))
    ]
    decisions = [e.get("decision") for e in risk_events if e.get("decision")]

    summary = {
        "session_id": session_id,
        "user_id": user_id,
        "source": "microphone" if source_type == "mic" else str(file_path),
        "chunks_sent": chunks_sent,
        "bytes_sent": bytes_sent,
        "audio_seconds_sent": round(bytes_sent / (SAMPLE_RATE * BYTES_PER_SAMPLE), 2),
        "wall_clock_seconds": round(total_elapsed, 2),
        "total_events": len(events_received),
        "risk_updates": len(risk_events),
        "decisions_seen": list(set(decisions)),
        "final_decision": decisions[-1] if decisions else None,
        "final_risk_score": risk_events[-1].get("risk_score") if risk_events else None,
        "final_risk_state": risk_events[-1].get("risk_state") if risk_events else None,
        "authenticity_spoof_prob_mean": round(sum(auth_scores) / len(auth_scores), 4) if auth_scores else None,
    }

    print("\n" + "=" * 60)
    print(f"{COLOR_BOLD}VOICESHIELD SESSION COMPLETED{COLOR_RESET}")
    print("=" * 60)
    for k, v in summary.items():
        print(f"  {k:28s}: {v}")
    print("=" * 60 + "\n")

    return {"summary": summary, "events": events_received}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to WAV or FLAC audio file")
    group.add_argument("--sample", choices=list(PRESET_SAMPLES.keys()), help="Preset sample from InTheWild dataset")
    group.add_argument("--mic", action="store_true", help="Stream live microphone input")

    parser.add_argument("--chunk-ms", type=int, default=250, choices=[20, 40, 100, 250], help="Chunk duration in ms")
    parser.add_argument("--mic-device", default=":0", help="avfoundation microphone device (default ':0')")
    parser.add_argument("--max-seconds", type=float, default=None, help="Maximum stream duration in seconds")
    parser.add_argument("--unpaced", action="store_true", help="Do not sleep between chunk sends (burst mode)")
    parser.add_argument("--in-process", action="store_true", default=True, help="Run in-process against real ML (default True)")
    parser.add_argument("--server", action="store_true", help="Connect to running external server instead of in-process")
    parser.add_argument("--url", default="ws://127.0.0.1:8000", help="WebSocket server URL")
    parser.add_argument("--http-url", default="http://127.0.0.1:8000", help="HTTP server URL")
    parser.add_argument("--session-id", default=None, help="Custom session UUID")
    parser.add_argument("--user-id", default=None, help="Custom user UUID")
    parser.add_argument("--token", default=None, help="Custom JWT access token")
    parser.add_argument("--challenge-at", type=float, default=None, help="Seconds into stream to trigger challenge")
    parser.add_argument("--resolve-at", type=float, default=None, help="Seconds into stream to resolve challenge")
    parser.add_argument("--resolve-outcome", choices=["passed", "failed", "timeout"], default="passed", help="Outcome for challenge resolution")
    parser.add_argument("--json", action="store_true", help="Output summary in JSON format")

    args = parser.parse_args()

    if args.sample:
        file_path = str(PRESET_SAMPLES[args.sample])
        source_type = "file"
    elif args.file:
        file_path = args.file
        source_type = "file"
    else:
        file_path = None
        source_type = "mic"

    in_process = not args.server

    try:
        results = stream_audio_session(
            source_type=source_type,
            file_path=file_path,
            chunk_ms=args.chunk_ms,
            mic_device=args.mic_device,
            max_seconds=args.max_seconds,
            realtime=not args.unpaced,
            in_process=in_process,
            server_url=args.url,
            http_url=args.http_url,
            session_id=args.session_id,
            user_id=args.user_id,
            token=args.token,
            challenge_at=args.challenge_at,
            resolve_at=args.resolve_at,
            resolve_outcome=args.resolve_outcome,
        )
        if args.json:
            print(json.dumps(results["summary"], indent=2))
        return 0
    except Exception as exc:
        log(f"Fatal error: {exc}", "ERROR", COLOR_RED)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
