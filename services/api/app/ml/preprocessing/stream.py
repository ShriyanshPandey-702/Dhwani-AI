"""
Streaming analysis windows.

VoiceShield is a real-time system: a call is never fed to a model in one piece.
Client frames arrive roughly every second, but the anti-spoofing checkpoint was
trained on ~4.04 s of audio, so a rolling per-session buffer assembles
overlapping windows of the length the model expects.

    frames in (≈1 s each)
        ↓
    rolling buffer (bounded)
        ↓
    overlapping windows (window_ms, advanced by hop_ms)
        ↓
    model inference

Window and hop are configuration, not magic numbers — see `Settings`.
Memory is bounded: the buffer never holds more than one window plus one hop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np

SAMPLE_RATE = 16000


@dataclass
class BufferStats:
    """Per-session buffer telemetry, useful for latency and coverage reporting."""

    buffered_samples: int = 0
    buffered_ms: int = 0
    windows_emitted: int = 0
    frames_received: int = 0
    ready: bool = False


@dataclass
class _SessionBuffer:
    samples: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    since_last_window: int = 0
    windows_emitted: int = 0
    frames_received: int = 0


class StreamWindower:
    """
    Per-session rolling buffers producing overlapping analysis windows.

    `push()` returns a window only when both conditions hold:
      * at least one full window of audio has accumulated, and
      * at least one hop of new audio has arrived since the last window.

    Otherwise it returns None and the caller reports insufficient evidence for
    that stream — it does not invent a shorter window for the model.
    """

    def __init__(
        self,
        window_ms: int = 4038,
        hop_ms: int = 1000,
        sample_rate: int = SAMPLE_RATE,
    ):
        self.sample_rate = sample_rate
        self.window_samples = max(1, int(sample_rate * window_ms / 1000))
        self.hop_samples = max(1, int(sample_rate * hop_ms / 1000))
        # Keep one window plus one hop so a window is always assemblable.
        self._max_samples = self.window_samples + self.hop_samples
        self._buffers: Dict[str, _SessionBuffer] = {}

    # ── Buffer lifecycle ─────────────────────────────────────────────────────

    def reset(self, session_id: str) -> None:
        """Clear a session's buffer — call on disconnect so audio is not retained."""
        self._buffers.pop(session_id, None)

    def stats(self, session_id: str) -> BufferStats:
        buf = self._buffers.get(session_id)
        if buf is None:
            return BufferStats()
        n = int(buf.samples.size)
        return BufferStats(
            buffered_samples=n,
            buffered_ms=int(1000 * n / self.sample_rate),
            windows_emitted=buf.windows_emitted,
            frames_received=buf.frames_received,
            ready=n >= self.window_samples,
        )

    # ── Ingest ───────────────────────────────────────────────────────────────

    def push(self, session_id: str, audio: Optional[np.ndarray]) -> Optional[np.ndarray]:
        """
        Append one decoded frame and return the newest analysis window, if due.

        Malformed or empty input is ignored rather than raising: a single bad
        frame must never interrupt the stream.
        """
        if audio is None:
            return None
        try:
            frame = np.asarray(audio, dtype=np.float32).ravel()
        except (TypeError, ValueError):
            return None
        if frame.size == 0 or not np.all(np.isfinite(frame)):
            return None

        buf = self._buffers.setdefault(session_id, _SessionBuffer())
        buf.frames_received += 1
        buf.samples = np.concatenate([buf.samples, frame])
        buf.since_last_window += int(frame.size)

        # Bound memory: retain only what a future window can need.
        if buf.samples.size > self._max_samples:
            buf.samples = buf.samples[-self._max_samples:]

        if buf.samples.size < self.window_samples:
            return None
        if buf.windows_emitted > 0 and buf.since_last_window < self.hop_samples:
            return None

        buf.since_last_window = 0
        buf.windows_emitted += 1
        # Copy so downstream inference cannot alias the live buffer.
        return np.array(buf.samples[-self.window_samples:], dtype=np.float32, copy=True)
