# VoiceShield — Real Audio Pipeline

How real audio reaches the production ML pipeline, what the backend guarantees
about it, and what this prototype does **not** do.

---

## 1. Architecture

```
real audio (WAV/FLAC file, or a live PCM producer)
   │  ingest: validate → mono → 16 kHz → float32 [-1,1]        app/ml/preprocessing/ingest.py
   ▼
int16 PCM chunks, base64, over WebSocket                        scripts/stream_real_audio.py
   │  {"type":"audio_chunk","seq":N,"data":"<base64>"}
   ▼
gateway: auth → size limits → base64 → seq dedup                app/websocket/gateway.py
   ▼
decode_pcm → measure_quality (energy VAD gate)                  app/ml/preprocessing/audio.py
   │  silent → audio_quality event only, NO evidence
   ▼
StreamWindower: 64,608-sample window / 16,000-sample hop        app/ml/preprocessing/stream.py
   ▼
   ├── AASIST-L        authenticity   (frozen checkpoint)       app/ml/authenticity/
   ├── ECAPA-TDNN      identity                                 app/ml/identity/
   └── faster-whisper  transcript → context signals             app/ml/context/
   ▼
Risk Engine (0.50 / 0.25 / 0.25) → Policy Engine                app/risk/
   ▼
risk_update · policy_decision · detected_event · alert          app/websocket/events.py
   ▼
React Native dashboard (Zustand)                                src/store/riskStore.ts
   ▼
incident persistence at session end                             app/websocket/gateway.py
```

Three evidence streams stay independent and are fused **only** in the Risk
Engine. A stream with no evidence contributes nothing — it never contributes a
guess.

---

## 2. Audio contract

**Internal representation (unchanged from the validated pipeline):**

| | |
|---|---|
| Channels | mono |
| Sample rate | 16,000 Hz |
| Format | float32 in [-1, 1] |
| Window | 64,608 samples ≈ 4.038 s |
| Hop | 16,000 samples = 1.000 s |
| Max buffer | 80,608 samples ≈ 5.038 s |
| Model length policy | tile if short, centre-crop if long (64,600) |
| Preprocessing version | `prep-v1` |

**Wire format:** little-endian **int16 PCM**, base64-encoded, in
`audio_chunk` messages. The server does not accept container formats over the
socket — file parsing happens in the client/harness, exactly as a real
streaming client would. This keeps one decode path on the server and means the
validated model preprocessing was **not** altered to support real audio.

`app/ml/preprocessing/ingest.py` is the single place a file or foreign buffer
becomes the internal representation. AASIST, ECAPA, Whisper and the harness all
consume its output; none of them re-implements resampling or downmixing.

Accepted inputs: WAV/FLAC files (testing), raw PCM chunks (streaming), any
authorized media-stream producer that can emit 16 kHz mono PCM.

---

## 3. WebSocket protocol

**Client → server**

| Message | Fields |
|---|---|
| `audio_chunk` | `data` (base64 int16 PCM), optional `seq` (int) |
| `start_demo` / `stop_demo` | mock driver on/off |
| `ping` | liveness / synchronisation barrier |

**Server → client** — every event carries `type`, `event_id`, `seq`,
`session_id`, `timestamp`: `session_started`, `audio_quality`, `risk_update`,
`threshold_crossed`, `policy_decision`, `detected_event`, `alert`,
`challenge_*`, `verification_*`, `error`, `pong`.

**Ingest limits and ordering (§5, §15)**

| Guard | Behaviour |
|---|---|
| Base64 length > 1,400,000 chars | `error` code `audio_too_large`, socket survives |
| Decoded chunk > 1 MiB | `error` code `audio_too_large` |
| Non-string `data` | `error` code `bad_audio` |
| Undecodable base64 | `error` code `bad_audio` |
| `seq` repeated | dropped, `duplicate_audio_chunks` incremented |
| `seq` older than the last accepted | dropped, `stale_audio_chunks` incremented |
| No `seq` supplied | every chunk accepted (numbering is optional) |

The client mirrors this: `riskStore` drops duplicates by `event_id`, drops
stale events by `seq`, tolerates a reconnect's seq restart, and `reset()`s all
state on a new session. **The dashboard never computes risk** — it renders what
the backend decided.

---

## 4. Session lifecycle

`CREATED → ACTIVE → ANALYZING → COMPLETED`, with `FAILED` / `CANCELLED` as
terminal states. A new session starts from a fresh `SessionState`: empty risk
history, no authenticity/identity/context, no announced findings, no challenge
or verification outcome, and a windower buffer that is reset on disconnect.
Verified by `test_ten_sequential_sessions_leak_no_state`.

---

## 5. Real vs mock mode

| | Mock | Real |
|---|---|---|
| Selected by | `PIPELINE_MODE=mock` (default) or `start_demo` | `PIPELINE_MODE=real_ml` + `audio_chunk` |
| Audio | synthetic PCM from `simulation/mock_audio.py` | the caller's actual samples |
| Models | deterministic heuristics | AASIST-L, ECAPA-TDNN, faster-whisper |
| Event labelling | `pipeline_mode: "mock"`, `is_mock: true` | `pipeline_mode: "live"`, per-stream `real_ml` |

Both paths run the **same** `analyze_window`. Mock mode is preserved unchanged
and remains fully tested; a fallback is always labelled, never presented as
real ML.

---

## 6. Model provenance

| Stream | Model | Provenance |
|---|---|---|
| Authenticity | **AASIST-L**, frozen | `sha256 814331d0…ce27a`, pinned in `aasist.py` and `fetch_models.py`, asserted by test |
| Identity | ECAPA-TDNN | `speechbrain/spkrec-ecapa-voxceleb` |
| Transcript | faster-whisper | `tiny`, int8 |

No Phase 1 checkpoint is wired into production; `test_no_phase1_checkpoint_is_wired_into_production`
guards this.

---

## 7. Latency — measured, not claimed

`PIPELINE_MODE=real_ml python services/api/scripts/benchmark_realtime.py`

48 scored windows across the FUNCTIONAL_TEST set, 100 ms chunks, CPU
(Apple M4). **Only chunks where the windower actually emitted a window are
counted** — buffer-fill chunks run no model and averaging them in would
understate latency by an order of magnitude.

| Stage | p50 | p95 | max |
|---|---|---|---|
| AASIST-L authenticity | 261.6 ms | 442.8 ms | 654.2 ms |
| ECAPA-TDNN identity | 84.1 ms | 185.8 ms | 198.4 ms |
| faster-whisper STT | 537.0 ms | 784.3 ms | 1034.9 ms |
| Context analysis | 0.05 ms | 0.05 ms | — |
| Risk fusion + policy | 0.11 ms | 0.13 ms | — |
| **Server total per window** | **895.2 ms** | **1240.5 ms** | 1378.7 ms |

Cold start (first scored window, models warming): **1116.0 ms**.

**The honest characterisation:**

> Near-real-time streaming analysis with a ~4.0 s analysis window plus
> model inference and transport latency.

Two things this table does not include: network/WebSocket transport, and UI
rendering. And the term that dominates everything is not in the table at all —
**4,038 ms of audio must accumulate before the first window can be scored**, so
first evidence arrives at roughly 4.0 s + ~1.1 s ≈ **5.1 s** into a call.

**A real limitation, stated plainly:** server total p95 (1240 ms) **exceeds the
1000 ms hop**. On this hardware the pipeline keeps up at the median but falls
behind at the tail, so under sustained load windows will queue. This is a
prototype on CPU, not a tuned deployment.

---

## 8. Error handling

| Failure | Behaviour |
|---|---|
| Malformed / oversized / non-base64 audio | structured `error` event; socket and process survive |
| One session misbehaving | isolated; other sessions unaffected |
| AASIST failure | window degrades to the labelled heuristic; never a fabricated "safe" |
| ECAPA failure / no enrolment | identity reported as unavailable, **not** as a mismatch |
| STT failure | context evidence absent, not "safe" |
| Persistence failure | logged, analysis continues |
| Silence | `audio_quality` only — no risk update, no evidence |

Missing evidence reaches the Risk Engine as *absent*, producing
`INSUFFICIENT_EVIDENCE`. "No speech" is never converted into "no risk".

---

## 9. Privacy

Persisted at session end: session id, timing, final risk/state/decision,
evidence summaries, detected events, challenge and verification outcomes,
integrity hash, model versions, pipeline mode.

**Not persisted:** raw audio, raw speaker embeddings, unnecessary transcript
content. Logs carry metadata only — never audio, tokens, OTP values or
embeddings. `test_events_never_carry_raw_audio_or_embeddings` asserts that no
event contains an embedding-shaped array or an audio-bearing key.

---

## 10. Platform limitations — read this before demoing

The system supports three input paths, and only these:

- **A. Real-audio test harness** — a WAV/FLAC file streamed as PCM chunks. This
  is what the automated tests and the demo use.
- **B. Authorized VoIP / contact-centre media stream** — architecturally ready;
  not implemented.
- **C. Consented mobile screening** — with explicit user consent and platform
  permissions; not implemented.

**VoiceShield does not record every cellular call on Android, and it does not
capture iOS cellular audio.** Neither platform exposes that to third-party apps
without privileged or private APIs. Any claim otherwise would be false.

---

## 11. Running the real-audio harness

```bash
# in-process, no server required (this is what the tests do)
cd services/api
PIPELINE_MODE=real_ml .venv/bin/python scripts/stream_real_audio.py \
    --file ../../data/external/InTheWild/release_in_the_wild/9489.wav \
    --chunk-ms 100 --json
```

`--chunk-ms` accepts 20, 40, 100 or 250.

**Default 100 ms, and why.** All four sizes produce identical analysis — the
windower is driven by accumulated samples, not by chunk boundaries, and
`test_chunking_covers_every_sample_exactly_once` proves no sample is lost or
duplicated at any size. 100 ms is the default because it balances per-message
overhead (20 ms means 50 messages/second/session, mostly framing) against
responsiveness (250 ms adds up to a quarter-second of avoidable delay before a
hop boundary is crossed). No size is universally optimal; a bandwidth-limited
link may prefer 250 ms.

## 12. Manual demo procedure

1. `cd services/api && PIPELINE_MODE=real_ml .venv/bin/uvicorn main:app --port 8000`
2. Launch the Android app, log in, start a session.
3. Stream a bona-fide file with the harness (§11). The dashboard shows real
   `risk_update` events with `pipeline_mode: "live"`.
4. Stream a spoofed file — authenticity evidence changes.
5. Trigger a Challenge; return FAILED → backend risk rises.
6. Trigger Independent Verification; APPROVE → backend recomputes and risk falls.
7. End the call; confirm the incident persists and appears in history.
8. Start a second session and confirm zero carry-over from the first.

## 13. Known limitations

1. Server p95 exceeds the 1 s hop on this hardware (§7).
2. First evidence is ~5.1 s into a call; this is inherent to the 4.038 s window.
3. Speaker enrolment in the demo path happens from the call's own first window,
   so identity answers "is this consistent?", not "is this the enrolled person?"
4. `evaluation/functional/` is a **FUNCTIONAL_TEST** set of 8 clips. It is far
   too small to be a benchmark and its numbers must never be quoted as accuracy.
   The published benchmarks are in `evaluation/results/` and are unchanged.
5. Real-world detection quality is weak and independently measured: on the
   sealed In-the-Wild set the frozen detector scores ROC-AUC 0.6739. Streaming a
   bona-fide file through this pipeline lands at `suspicious` — the pipeline is
   working correctly and reporting a model limitation, not a bug.
6. No transport or UI-render latency has been measured.
