# Dhwani AI — Phase 1.5: Asynchronous Speech-to-Text

## 1. Problem

Phase 1 measured the real-audio pipeline and found the server could not hold its
own 1-second analysis hop:

| Stage | p50 | p95 |
|---|---:|---:|
| AASIST-L | 261.6 ms | 442.8 ms |
| ECAPA-TDNN | 84.1 ms | 185.8 ms |
| **faster-whisper** | **537.0 ms** | **784.3 ms** |
| Context | 0.05 ms | 0.05 ms |
| Risk Engine + policy | 0.11 ms | 0.13 ms |
| **Server total** | **895.2 ms** | **1240.5 ms** |

Whisper was ~60% of the budget, and p95 (1240 ms) exceeded the 1000 ms hop.

## 2. Where it blocked

`pipeline.analyze_window()` called `transcriber.transcribe()` inline, and
`analyze_window` is *synchronous* — invoked directly from the async `_process`.
So transcription sat both in the per-window critical path **and** on the
FastAPI event loop.

## 3. Architecture before

```
audio window → VAD → AASIST → ECAPA → Whisper → context → Risk → policy → events
                                      └── 537 ms p50, blocking ──┘
```

## 4. Architecture after

```
audio chunk
    │
    ├─ VAD ─ AASIST ─ ECAPA ─ fuse ─ policy ─ events        ← CRITICAL PATH
    │                                                          p95 542 ms
    └─ every 4th window ──▶ bounded asyncio.Queue (max 8)
                                    │
                                    ▼
                            1 worker task
                                    │  run_in_executor
                                    ▼
                            ThreadPoolExecutor
                                    │  faster-whisper
                                    ▼
                            transcript → context
                                    │
                                    ▼
                            Risk Engine (again) → policy → events
                                                  ← SEMANTIC UPDATE
                                                     p95 622 ms after submit
```

The acoustic path never waits. Context evidence arrives later and triggers an
**authoritative recomputation** by the same unmodified Risk Engine.

## 5. STT queue

| Property | Value | Why |
|---|---|---|
| Type | `asyncio.Queue` | matches the existing single-loop server |
| Max size | **8** | ~8 s of pending context at the chosen cadence |
| Queue-full policy | **drop oldest**, counted | newest audio carries the most relevant context; a stale backlog entry is the right thing to lose |
| Cadence | every **4th** analysis window | windows are 4.038 s wide arriving every 1 s → ~75% overlap; transcribing all of them is ~4× redundant for nearly the same text |
| Timeout | 20 s per job | a hung job cannot occupy the worker forever |

Drops, failures, timeouts, stale and duplicate results are all counted in
`STTMetrics` and logged — never silent.

## 6. Worker design and concurrency

**Threads, not processes.** faster-whisper/CTranslate2 releases the GIL during
inference, so a `ThreadPoolExecutor` gives real parallelism while keeping the
model loaded exactly once. A process pool would either duplicate the model per
worker or reload it per job, and would copy large float arrays over a pipe every
window.

**Worker count: 1 — chosen by measurement, not assumption** (§8):

| Workers | Critical p50 | Critical p95 | Semantic p95 | Max queue depth |
|---|---:|---:|---:|---:|
| **1** | 269.9 ms | **542.5 ms** | **622.3 ms** | 1 |
| 2 | 265.7 ms | 568.6 ms | 781.1 ms | 1 |

A second worker made both p95s *worse*. Queue depth never exceeded 1, so the
extra worker had no work to do and only added CPU contention.

## 7. Stale-result handling

Whisper can finish out of order. Every job carries `session_id` and
`window_seq`; `SessionState.last_context_seq` records the newest window whose
transcript has been applied. On arrival:

| Condition | Action |
|---|---|
| session missing or closed | drop, `dropped_session_gone++` |
| `window_seq < last_context_seq` | drop, `stale_stt_results++` |
| `window_seq == last_context_seq` | no-op (idempotent), `duplicate_stt_results++` |
| `window_seq > last_context_seq` | apply, advance cursor, re-decide |

Because the recomputed `risk_update` is published through the normal event
builder, it receives a fresh monotonic server `seq`, so the client's existing
stale-event guard keeps the dashboard from ever moving backwards.

## 8. Transcript deduplication

Windows overlap, so consecutive transcripts repeat text. Two mechanisms handle
it, both deterministic:

1. **Cadence** — running STT every 4th window makes consecutive transcribed
   windows nearly non-overlapping (4 windows × 1 s hop ≈ the 4.038 s width), so
   most duplication never occurs.
2. **Sequence cursor** — a window is applied at most once, and only if newer
   than the last applied. Re-delivery of the same window changes nothing.

No fuzzy text merging was added; a heuristic NLP dedup would be harder to
reason about than the window arithmetic and would not be testable in the same
way.

## 9. Session isolation

Jobs are bound to one `session_id` and resolved through `manager.get_state()`
at apply time. A result for a session that no longer exists is dropped and
counted. `close_session()` is called in `_teardown`, so a transcript that lands
after a call ends cannot resurrect it. Tests cover cross-session contamination,
terminated sessions, and vanished sessions.

## 10. Failure handling

| Failure | Behaviour |
|---|---|
| Whisper raises | counted, logged, worker survives and takes the next job |
| Whisper hangs | 20 s timeout, counted, worker survives |
| Queue full | oldest evicted, counted |
| Session ended mid-job | result discarded |
| No speech in window | cursor advances, **context stays unavailable** |

Missing context is never converted into "safe". It simply means the Risk Engine
receives no context stream — which is exactly what `INSUFFICIENT_EVIDENCE`
already represents.

## 11. Latency results

48 scored windows, real ML, chunks paced at wall-clock speed, Apple M4 CPU.

| Metric | Before (Phase 1) | After (Phase 1.5) |
|---|---:|---:|
| AASIST p50 / p95 | 261.6 / 442.8 ms | on critical path |
| ECAPA p50 / p95 | 84.1 / 185.8 ms | on critical path |
| Whisper execution p50 / p95 | 537.0 / 784.3 ms | **475.2 / 616.0 ms** (off critical path) |
| STT queue wait p50 / p95 | n/a | 0.31 / 0.78 ms |
| **Critical path p50 / p95** | **895.2 / 1240.5 ms** | **270.0 / 542.5 ms** |
| Semantic update p50 / p95 | n/a | 478.7 / 622.3 ms |

**Critical-path p95 is 542.5 ms — below the 1000 ms hop.** The comparison is
apples-to-apples in the only way that matters: the Phase 1 "server total"
*included* Whisper, and removing it is the change, not a measurement trick.
Whisper's full cost is still reported, in its own row.

First acoustic evidence remains ≈ 4.038 s (window fill) + ~0.27 s ≈ **4.3 s**.
First semantic evidence adds the cadence delay: STT runs on the 4th window, so
context typically lands ≈ 4 s later still.

## 12. Sustainability (120 s, 1 session)

| | |
|---|---|
| Chunks sent | 1,045 |
| Windows analysed | 101 |
| Critical p50 / p95 | 237.5 / 401.4 ms |
| STT submitted / completed / dropped | 20 / 20 / 0 |
| Stale / duplicate results | 0 / 0 |
| Max queue depth | 1 |
| RSS | 980 → 1303 MB |

RSS profile: 980 → 1122 MB in the first 10 s (lazy model loading), then a
plateau of 1188–1209 MB between 30 s and 80 s (+21 MB over 50 s), a step to
1298 MB at 90 s, then flat. That is consistent with one-time loading and
allocator arenas rather than per-window growth — but a longer soak would be
needed to rule out slow growth conclusively.

## 13. Concurrency limit — measured, not claimed

Cadence achieved against wall clock (600 chunks expected per session per 60 s):

| Sessions | Chunk cadence | Critical p95 | Notes |
|---|---:|---:|---|
| 1 | **87%** | 401 ms | |
| 2 | 73% / 72% | 557 / 631 ms | |
| 3 | 63% each | 541 / 807 / 430 ms | STT wait rises to 353 ms p50 |

Session isolation held perfectly at every level: separate context cursors, 0
stale, 0 duplicate, no cross-session effects.

**Honest reading:** the 1-second *hop* budget is met with large margin even at
3 sessions. What does not hold is 100 ms *chunk ingestion* cadence — even a
single session reaches only 87%, because AASIST + ECAPA (~250 ms) still execute
**synchronously on the event loop**. Whisper is no longer the bottleneck; the
remaining acoustic work is. This machine sustains roughly **one** real-ML
session at near-real-time.

## 14. Why AASIST and the Risk Engine were not changed

Neither needed to change, and both are protected. The bottleneck was scheduling,
not modelling: the same AASIST-L checkpoint (`814331d0…ce27a`) and the same
Risk Engine weights/thresholds produce the same decisions — they simply receive
context evidence a few seconds later, and re-decide when it arrives. The Risk
Engine source was not touched.

## 15. Limitations

1. AASIST + ECAPA still run on the event loop; that is now the limiting factor.
2. ~1 concurrent real-ML session at near-real-time on this hardware.
3. Semantic evidence lags acoustic evidence by roughly one STT cadence (~4 s).
4. `STT_EVERY_N_WINDOWS = 4` is derived from window geometry, not from a WER
   study; transcription quality against a lower cadence was not measured.
5. Memory growth over 120 s is consistent with lazy loading but not proven flat
   over hours.
6. Mock mode deliberately keeps STT inline, so the async path is exercised only
   in real-ML mode.
