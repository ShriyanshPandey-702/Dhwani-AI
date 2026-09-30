"""
Deepgram Live Streaming STT Client (WebSockets).

Maintains a persistent, low-latency WebSocket connection to Deepgram Nova-2
for real-time streaming audio transcription with interim (partial) results.
"""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Optional

import structlog
import websockets

from app.core.config import settings

log = structlog.get_logger()

# Callback signature: (transcript_text, is_final, speech_final, confidence)
TranscriptCallback = Callable[[str, bool, bool, float], Awaitable[None]]


class DeepgramLiveStreamer:
    """
    Persistent WebSocket streaming client to Deepgram Nova-2.
    Streams raw linear16 16kHz PCM chunks and emits interim/final transcript events.
    """

    DEEPGRAM_WS_URL = (
        "wss://api.deepgram.com/v1/listen?"
        "model=nova-2&"
        "smart_format=true&"
        "interim_results=true&"
        "encoding=linear16&"
        "sample_rate=16000&"
        "channels=1"
    )

    def __init__(
        self,
        session_id: str,
        on_transcript: TranscriptCallback,
        api_key: Optional[str] = None,
    ):
        self.session_id = session_id
        self.on_transcript = on_transcript
        self.api_key = api_key or settings.DEEPGRAM_API_KEY
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._audio_queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=128)
        self._send_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._is_connected = False

    @property
    def is_active(self) -> bool:
        return self._is_running and self._is_connected

    async def start(self) -> bool:
        """Start the streaming connection and worker tasks."""
        if not self.api_key:
            log.info("deepgram_stream.no_key", session_id=self.session_id)
            return False

        if self._is_running:
            return True

        self._is_running = True
        try:
            headers = {"Authorization": f"Token {self.api_key}"}
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self.DEEPGRAM_WS_URL,
                    extra_headers=headers,
                    ping_interval=15,
                    ping_timeout=10,
                ),
                timeout=5.0,
            )
            self._is_connected = True
            log.info("deepgram_stream.connected", session_id=self.session_id)

            self._receive_task = asyncio.create_task(self._receive_loop())
            self._send_task = asyncio.create_task(self._send_loop())
            return True
        except Exception as e:
            log.warning("deepgram_stream.connect_failed", session_id=self.session_id, error=str(e))
            self._is_connected = False
            self._is_running = False
            return False

    def push_audio(self, pcm_bytes: bytes) -> bool:
        """Enqueue PCM bytes to be sent to Deepgram without blocking."""
        if not self._is_running or not self._is_connected:
            return False
        try:
            self._audio_queue.put_nowait(pcm_bytes)
            return True
        except asyncio.QueueFull:
            # Drop oldest to maintain real-time freshness
            try:
                self._audio_queue.get_nowait()
                self._audio_queue.put_nowait(pcm_bytes)
                return True
            except Exception:
                return False

    async def _send_loop(self) -> None:
        """Continuously sends queued PCM audio chunks to Deepgram."""
        try:
            while self._is_running and self._ws is not None:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    break
                if self._ws.open:
                    await self._ws.send(chunk)
                self._audio_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.debug("deepgram_stream.send_error", session_id=self.session_id, error=str(e))

    async def _receive_loop(self) -> None:
        """Continuously receives transcription events from Deepgram."""
        try:
            while self._is_running and self._ws is not None:
                msg_text = await self._ws.recv()
                if not isinstance(msg_text, str):
                    continue
                try:
                    data = json.loads(msg_text)
                except Exception:
                    continue

                if data.get("type") == "Results":
                    channel = data.get("channel", {})
                    alts = channel.get("alternatives", [])
                    if alts:
                        transcript = alts[0].get("transcript", "")
                        confidence = float(alts[0].get("confidence", 0.0))
                        is_final = bool(data.get("is_final", False))
                        speech_final = bool(data.get("speech_final", False))

                        if transcript.strip():
                            await self.on_transcript(
                                transcript.strip(),
                                is_final,
                                speech_final,
                                confidence,
                            )
        except asyncio.CancelledError:
            pass
        except websockets.exceptions.ConnectionClosed:
            log.info("deepgram_stream.closed", session_id=self.session_id)
        except Exception as e:
            log.warning("deepgram_stream.receive_error", session_id=self.session_id, error=str(e))
        finally:
            self._is_connected = False

    async def stop(self) -> None:
        """Gracefully close streaming connection."""
        self._is_running = False
        self._is_connected = False

        if self._send_task and not self._send_task.done():
            self._send_task.cancel()
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()

        if self._ws is not None:
            try:
                # Send empty binary chunk / close frame to finalize
                if self._ws.open:
                    await asyncio.wait_for(self._ws.close(), timeout=1.0)
            except Exception:
                pass
            self._ws = None

        log.info("deepgram_stream.stopped", session_id=self.session_id)
