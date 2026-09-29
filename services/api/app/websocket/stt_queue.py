"""
Asynchronous speech-to-text queue (Phase 1.5).

Whisper used to run inline inside `analyze_window`, which put ~537 ms (p50) of
transcription directly in the per-window critical path — on the event loop — so
the 1 s acoustic hop could not be met. This module moves that work off the
critical path without weakening any security property.

Design decisions, and why:

* **Bounded `asyncio.Queue` + worker tasks + a `ThreadPoolExecutor`.**
  faster-whisper/CTranslate2 releases the GIL during inference, so threads give
  real parallelism here. A process pool was rejected: it would either duplicate
  the ~75 MB model per worker or reload it per job, and would copy large float
  arrays across a pipe for every window.

* **Drop-oldest when full.** For transcription the *newest* audio carries the
  most relevant conversation context; discarding a stale backlog entry keeps
  semantics current under load. Every drop is counted, never silent.

* **STT runs on every Nth analysis window.** Windows are 4.038 s wide and
  arrive every 1 s, so consecutive windows overlap by ~75%. Transcribing all of
  them is ~4x redundant work for nearly the same text.

Security invariant: a missing, dropped, failed or stale transcript makes
context evidence **unavailable**. It is never converted into "safe" — the Risk
Engine simply receives no context stream, which is what INSUFFICIENT_EVIDENCE
already means.
"""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

import numpy as np
import structlog

log = structlog.get_logger()

# Tunables. Deliberately conservative for the M4 development machine; §8 of the
# brief asks for measurement rather than assumption, and the benchmark script
# sweeps worker counts.
DEFAULT_MAX_QUEUE = 8
DEFAULT_WORKERS = 1
DEFAULT_TIMEOUT_S = 20.0
STT_EVERY_N_WINDOWS = 1


@dataclass
class STTJob:
    """One unit of transcription work, bound to exactly one session."""
    session_id: str
    window_seq: int
    audio: np.ndarray
    submitted_at: float = field(default_factory=time.perf_counter)
    pipeline_mode: str = "live"


@dataclass
class STTMetrics:
    submitted: int = 0
    completed: int = 0
    dropped_queue_full: int = 0
    dropped_stale: int = 0
    dropped_session_gone: int = 0
    failed: int = 0
    timed_out: int = 0
    max_queue_depth: int = 0
    wait_ms: list = field(default_factory=list)
    exec_ms: list = field(default_factory=list)

    def snapshot(self) -> dict:
        def pct(xs, p):
            if not xs:
                return None
            s = sorted(xs)
            k = max(0, min(len(s) - 1, int(round((p / 100) * (len(s) - 1)))))
            return round(s[k], 2)
        return {
            "submitted": self.submitted, "completed": self.completed,
            "dropped_queue_full": self.dropped_queue_full,
            "dropped_stale": self.dropped_stale,
            "dropped_session_gone": self.dropped_session_gone,
            "failed": self.failed, "timed_out": self.timed_out,
            "max_queue_depth": self.max_queue_depth,
            "wait_ms_p50": pct(self.wait_ms, 50), "wait_ms_p95": pct(self.wait_ms, 95),
            "exec_ms_p50": pct(self.exec_ms, 50), "exec_ms_p95": pct(self.exec_ms, 95),
        }


# The callback the worker invokes with a finished transcript. It receives the
# job and the transcriber's segment (or None), and is responsible for the
# sequence check, context classification, risk recomputation and publishing.
ApplyFn = Callable[[STTJob, object], Awaitable[None]]


class STTQueue:
    """Bounded work queue with a fixed number of transcription workers."""

    def __init__(self, transcribe_fn, apply_fn: ApplyFn,
                 max_queue: int = DEFAULT_MAX_QUEUE,
                 workers: int = DEFAULT_WORKERS,
                 timeout_s: float = DEFAULT_TIMEOUT_S):
        self._transcribe = transcribe_fn
        self._apply = apply_fn
        self.max_queue = max_queue
        self.workers = workers
        self.timeout_s = timeout_s
        self._queue: Optional[asyncio.Queue] = None
        self._tasks: list = []
        self._pool: Optional[ThreadPoolExecutor] = None
        self._closed_sessions: set = set()
        self.metrics = STTMetrics()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        if self._tasks:
            return
        self._queue = asyncio.Queue(maxsize=self.max_queue)
        self._pool = ThreadPoolExecutor(max_workers=self.workers,
                                        thread_name_prefix="stt")
        self._tasks = [asyncio.create_task(self._worker(i))
                       for i in range(self.workers)]
        log.info("stt.queue_started", workers=self.workers, max_queue=self.max_queue)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
            self._pool = None
        self._queue = None

    @property
    def running(self) -> bool:
        return bool(self._tasks)

    def depth(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    # ── Session lifecycle ────────────────────────────────────────────────────

    def close_session(self, session_id: str) -> None:
        """
        Stop accepting work for a session and ignore anything still in flight.

        A transcript that lands after the call ended must never resurrect or
        mutate a completed session (§25).
        """
        self._closed_sessions.add(session_id)

    def reopen_session(self, session_id: str) -> None:
        self._closed_sessions.discard(session_id)

    def is_closed(self, session_id: str) -> bool:
        return session_id in self._closed_sessions

    # ── Producer ─────────────────────────────────────────────────────────────

    def submit(self, job: STTJob) -> bool:
        """
        Enqueue transcription work without ever blocking the caller.

        Returns True when accepted. When the queue is full the oldest pending
        job is evicted to make room, because newer audio is the more useful
        context. Never raises: the acoustic path must not care.
        """
        if self._queue is None or self.is_closed(job.session_id):
            return False
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull:
            try:
                evicted = self._queue.get_nowait()
                self._queue.task_done()
                self.metrics.dropped_queue_full += 1
                log.warning("stt.dropped_queue_full",
                            session_id=evicted.session_id,
                            window_seq=evicted.window_seq,
                            depth=self._queue.qsize())
            except asyncio.QueueEmpty:
                pass
            try:
                self._queue.put_nowait(job)
            except asyncio.QueueFull:
                self.metrics.dropped_queue_full += 1
                return False
        self.metrics.submitted += 1
        self.metrics.max_queue_depth = max(self.metrics.max_queue_depth,
                                           self._queue.qsize())
        return True

    # ── Worker ───────────────────────────────────────────────────────────────

    async def _worker(self, index: int) -> None:
        loop = asyncio.get_running_loop()
        while True:
            job = await self._queue.get()
            try:
                if self.is_closed(job.session_id):
                    self.metrics.dropped_session_gone += 1
                    continue
                self.metrics.wait_ms.append(
                    (time.perf_counter() - job.submitted_at) * 1000)

                t0 = time.perf_counter()
                try:
                    segment = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._pool, self._transcribe, job.session_id, job.audio),
                        timeout=self.timeout_s,
                    )
                except asyncio.TimeoutError:
                    self.metrics.timed_out += 1
                    log.warning("stt.timeout", session_id=job.session_id,
                                window_seq=job.window_seq)
                    continue
                except Exception as e:
                    # A transcription failure degrades context to unavailable.
                    # It must not touch the acoustic path or any other session.
                    self.metrics.failed += 1
                    log.warning("stt.failed", session_id=job.session_id,
                                window_seq=job.window_seq, error=str(e))
                    continue
                self.metrics.exec_ms.append((time.perf_counter() - t0) * 1000)

                if self.is_closed(job.session_id):
                    self.metrics.dropped_session_gone += 1
                    continue
                try:
                    await self._apply(job, segment)
                    self.metrics.completed += 1
                except Exception as e:
                    self.metrics.failed += 1
                    log.warning("stt.apply_failed", session_id=job.session_id,
                                window_seq=job.window_seq, error=str(e))
            except asyncio.CancelledError:
                raise
            except Exception as e:                      # pragma: no cover
                log.error("stt.worker_error", worker=index, error=str(e))
            finally:
                self._queue.task_done()
