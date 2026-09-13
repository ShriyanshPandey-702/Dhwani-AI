# VoiceShield Phase 1.7 — Real-Time Prototype Architecture & Validation

## 1. Executive Summary

VoiceShield Phase 1.7 operationalizes the end-to-end real-time AI-powered voice cloning detection and prevention pipeline on top of the frozen Phase 1.6 asynchronous concurrency baseline.

The pipeline ingests raw 16 kHz mono 16-bit PCM audio from live microphones or audio files, packetizes audio into 250ms chunks over WebSockets, buffers and hops through a streaming windower (64,608 samples window, 16,000 samples hop), concurrently runs deepfake authenticity detection (AASIST-L with AASIST cascade) and speaker identity verification (ECAPA-TDNN) in a dedicated thread-pool executor, performs asynchronous transcription and contextual threat analysis (faster-whisper), fuses multimodal signals in the Risk Engine, enforces Security Policy (ALLOW, CHALLENGE, HOLD, BLOCK), issues interactive cryptographic/semantic challenges, and broadcasts real-time threat telemetry to client applications.

All 15 automated validation targets passed with 100% success rate, including the complete 382-test backend regression suite with zero exclusions, 61/61 mobile tests with 0 TypeScript errors, continuous 120-second soak testing across 116 windows, multi-session concurrency, and fault tolerance against model/network failures.

---

## 2. Architecture & Pipeline Invariants

The real-time streaming pipeline strictly preserves all Phase 1.6 invariants:

```
                  ┌─────────────────────────────────────────┐
                  │ Real Audio (Mic / File, 16kHz mono PCM) │
                  └───────────────────┬─────────────────────┘
                                      │ 250ms chunks (4 chunks/sec)
                                      ▼
                        ┌───────────────────────────┐
                        │ WebSocket Ingress Gateway │
                        │  (MAX_PENDING_CHUNKS = 4) │
                        └─────────────┬─────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │ StreamWindower Buffer     │
                        │ Window: 64,608 (4.038s)   │
                        │ Hop:    16,000 (1.000s)   │
                        │ MaxBuf: 80,608 (5.038s)   │
                        └─────────────┬─────────────┘
                                      ▼ (Triggered every 1.0s hop)
                        ┌───────────────────────────┐
                        │ Async Thread Pool Worker  │
                        └──────┬─────────────┬──────┘
                               │             │
              ┌────────────────┴─┐         ┌─┴────────────────┐
              ▼                  │         │                  ▼
   ┌───────────────────────┐     │         │       ┌───────────────────────┐
   │ Authenticity Detector │     │         │       │ ECAPA-TDNN Speaker ID │
   │ - AASIST-L (85k par)  │     │         │       │ - VoxCeleb Pretrained │
   │ - AASIST Cascade      │     │         │       │ - Cosine Similarity   │
   │ - NB_SAMP = 64,600    │     │         │       │ - Enrollment Vector   │
   │ - Fit: center crop    │     │         │       └───────────┬───────────┘
   └──────────┬────────────┘     │         │                   │
              │                  ▼         ▼                   │
              │         ┌─────────────────────────┐            │
              │         │ Async STT Queue         │            │
              │         │ faster-whisper (tiny)   │            │
              │         │ Keyword / Urgency Scan  │            │
              │         └────────────┬────────────┘            │
              │                      │                         │
              └────────────────┐     │     ┌───────────────────┘
                               ▼     ▼     ▼
                        ┌───────────────────────────┐
                        │ Risk Engine Fusion        │
                        │ Weights: 0.50 / 0.25 / 0.25│
                        │ Raw score (no calibration)│
                        │ Min Confidence: 0.25      │
                        └─────────────┬─────────────┘
                                      ▼
                        ┌───────────────────────────┐
                        │ Security Policy Evaluator │
                        │ Thresholds: 20, 40, 65, 85│
                        │ ALLOW / CHALLENGE /       │
                        │ HOLD / BLOCK              │
                        └─────────────┬─────────────┘
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
   ┌───────────────────────┐                       ┌───────────────────────┐
   │ Real-time WebSocket   │                       │ Dynamic Challenge API │
   │ Broadcast to UI/Mobile│                       │ /api/v1/challenge     │
   └───────────────────────┘                       └───────────────────────┘
```

### Frozen Pipeline Parameters
- **AASIST-L Checkpoint**: `services/api/models/aasist/AASIST-L.pth` (SHA-256: `814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a`).
- **AASIST Architecture**: `NB_SAMP = 64,600`, center crop `_fit_length` converts 64,608 -> 64,600 samples.
- **Identity Model**: `speechbrain/spkrec-ecapa-voxceleb` (192-dim embeddings).
- **STT Engine**: `faster-whisper` (`tiny`, int8 compute on CPU).
- **Risk Weights**: $w_{\text{authenticity}} = 0.50$, $w_{\text{identity}} = 0.25$, $w_{\text{context}} = 0.25$.
- **ML Thread Pool**: `ML_POOL_WORKERS = 2` (ThreadPoolExecutor in `gateway.py` strictly preserved from Phase 1.6 baseline).
- **Policy Thresholds**: `low`: 20, `suspicious`: 40, `high`: 65, `critical`: 85.
- **Admission Queue**: `MAX_PENDING_AUDIO_CHUNKS = 4` per session to prevent coroutine pileup under flood conditions.

---

## 3. Real-Time Streaming CLI Client

The demonstration client `services/api/scripts/demo_realtime_stream.py` provides an interactive terminal interface for streaming audio into VoiceShield.

### Capabilities:
1. **Live Microphone Mode**: Captures audio directly from default system microphone using `ffmpeg` (`-f avfoundation -i :0` on macOS or `pulse`/`alsa` on Linux) at 16,000 Hz, 16-bit signed PCM mono, chunked into 250ms packets.
2. **Audio File Mode**: Reads WAV/FLAC audio files, with presets for `spoof` (`data/external/InTheWild/release_in_the_wild/1.wav`) and `bonafide` (`45.wav`).
3. **Paced WebSocket Streaming**: Paces transmissions at 250ms per chunk (4 chunks/second) to emulate realistic real-time telemetry.
4. **Dynamic Challenge Flow**: Detects `challenge_required` WebSocket events, issues interactive verification prompts, accepts user spoken or keypad responses, and posts outcomes back to `/api/v1/challenge/{session_id}/{challenge_id}/result`.
5. **Rich Colored Telemetry**: Displays real-time status banners with VAD, Authenticity Score, Speaker Similarity, Transcripts, Context Threats, Risk Level, and Policy Decision.

### Usage:
```bash
# Stream spoof sample file
python services/api/scripts/demo_realtime_stream.py --preset spoof

# Stream bona-fide sample file
python services/api/scripts/demo_realtime_stream.py --preset bonafide

# Stream from live microphone (macOS MacBook Air Microphone)
python services/api/scripts/demo_realtime_stream.py --mic --max-seconds 6.0
```

---

## 4. Master Validation Suite Results

The comprehensive validation suite (`services/api/scripts/phase17_validate.py`) executed all 16 automated validation targets with zero exclusions.

| # | Test Case | Target / Specification | Result | Details |
|---|:---|:---|:---:|:---|
| 01 | **Backend Regression** | Complete pytest suite (382 tests, zero `-k` exclusions) | **PASS** | 382/382 passed in 146.4s with 0 failures |
| 02 | **Mobile Regression** | React Native Jest suite + TypeScript type checking | **PASS** | 61/61 Jest tests passed, 0 TypeScript errors |
| 03 | **Real Audio Single Session** | 6.0s real audio stream over WebSocket | **PASS** | 46 events received, 20 risk updates, 4 real ML windows |
| 04 | **Continuous 120s Soak** | 120.0s stream (116 expected windows) + memory stability | **PASS** | 116/116 windows analyzed. Post-stabilization RSS growth: 29.45 MB |
| 05 | **2 Concurrent Sessions** | Parallel real-audio streaming across 2 sessions | **PASS** | 2 sessions executed concurrently without cross-talk or lock contention |
| 06 | **3 Concurrent Sessions** | Parallel real-audio streaming across 3 sessions | **PASS** | 3 sessions executed concurrently without deadlocks |
| 07 | **Disconnect During Inference** | WebSocket drop mid-inference | **PASS** | Clean disconnect handling, zero orphan tasks or server crashes |
| 08 | **AASIST Fault Recovery** | Synthesized crash inside AASIST forward pass | **PASS** | Exception caught cleanly; degraded gracefully to heuristic fallback |
| 09 | **ECAPA Fault Recovery** | Synthesized crash inside speaker embedding extraction | **PASS** | ECAPA error handled without crashing session or disconnecting WS |
| 10 | **STT Failure Recovery** | Synthesized crash inside faster-whisper transcriber | **PASS** | Whisper failure isolated; acoustic authenticity & identity continued |
| 11 | **Malformed Audio Rejection** | Invalid base64, truncated payloads, wrong types | **PASS** | 4 structured error events returned; connection preserved |
| 12 | **Ingress Backpressure** | 40 unpaced audio chunks flooded into connection | **PASS** | `MAX_PENDING_AUDIO_CHUNKS=4` enforced: 29 excess chunks dropped |
| 13 | **Frontend Reconnection** | Client disconnects and reconnects with same session | **PASS** | Session state preserved across connection boundary |
| 14 | **Dynamic Challenge Flow** | Challenge generation, WebSocket broadcast, result post | **PASS** | Challenge `3253dadf` created, passed, and triggered re-scoring |
| 15 | **Full Prototype Demo** | Complete end-to-end pipeline run with spoof audio | **PASS** | 44 events, 19 risk updates, spoof prob: 0.9829, decision: VERIFY |
| 16 | **Live Microphone Stream** | Live hardware mic capture (`:0`, 16kHz mono) + real ML | **PASS** | 21 chunks (5.25s), 46 events, 21 risk updates, 0 drops |

**Total Score: 16/16 tests passed (100.0%)**

---

## 5. Security & Risk Engine Policy Matrix

The prototype maps the fused 0–100 risk score to states via `classify_state(score, thresholds)` in `services/api/app/risk/engine.py` using active thresholds `{"low": 20, "suspicious": 40, "high": 65, "critical": 85}`, and maps state to policy action via `evaluate()` in `policy.py`:

| Risk Score Range | Evaluated Risk State | Mandatory Action | Dashboard Decision | Action Description |
|:---:|:---:|:---:|:---:|:---|
| $0 \le \text{Score} < 20$ | `insufficient_evidence` | `allow`* | `ALLOW`* | Initial stream baseline; *escalates to VERIFY if high-consequence request. |
| $20 \le \text{Score} < 40$ | `low` | `allow` | `ALLOW` | Stream continues normally with green telemetry. |
| $40 \le \text{Score} < 65$ | `suspicious` (e.g. 49, 50) | `challenge` | `VERIFY` | Issues interactive voice/keypad challenge to verify caller. |
| $65 \le \text{Score} < 85$ | `high` | `verify` | `VERIFY` | Enforces mandatory out-of-band (OOB) independent verification. |
| $85 \le \text{Score} \le 100$ | `critical` | `hold` | `HOLD` / `BLOCK` | Immediately halts consequential actions; creates tamper-evident incident. |

---

## 6. Known Trade-Offs & Roadmap

1. **CPU vs GPU Latency**: In CPU-only environments, full-window inference (AASIST-L + ECAPA-TDNN) takes ~350-500ms per 1.0s hop. With a 4-core CPU or Apple Silicon MPS / CUDA acceleration, latency drops to < 100ms per window.
2. **First-Window Warm-Up**: The pipeline requires 64,608 samples (4.038s) before emitting the first ML authenticity score. Sub-second preliminary VAD and STT events bridge the initial warm-up interval.
3. **Bounded Backpressure**: When client push rate exceeds processing capacity, chunks beyond the 4-chunk admission queue are dropped to protect event-loop responsiveness, preserving real-time freshness over stale buffering.
