# VoiceShield — Implementation Plan

**SIH 2026 · Problem Statement 26104 — AI-Powered Real-Time Detection and
Prevention of Voice Cloning Impersonation Attacks**

This plan records what is built, what is stubbed, and what comes next. It is
kept honest deliberately: a component is only marked complete when it works.

**Resemble AI is not part of this plan.** Authenticity detection is
VoiceShield's own pipeline. No third-party detection API is called.

---

## 1. Product thesis

The threat is not that audio can be faked. It is that a human, mid-conversation,
acts on a consequential instruction because they believe the caller.

So the loop is not `classify(audio) → label`. It is:

```
DETECT → SCORE → CHALLENGE → VERIFY → PROTECT
```

Three independent evidence streams feed a Risk Engine; a configurable Policy
Engine converts risk into an action; and where the risk is elevated, trust is
re-established on a channel independent of the call.

---

## 2. Architecture

```
Android audio  ──►  WebSocket  ──►  FastAPI  ──►  ML pipeline
                                                      │
                              ┌───────────────────────┼───────────────────────┐
                              ▼                       ▼                       ▼
                        Authenticity              Identity                 Context
                              │                       │                       │
                              └───────────────────────┼───────────────────────┘
                                                      ▼
                                                 RISK ENGINE
                                                      ▼
                                                POLICY ENGINE
                                                      ▼
                                    WebSocket ──► Zustand ──► Live Dashboard
```

Invariants:

- The backend owns the risk score. The client never computes one.
- Evidence streams stay structurally separate until fusion.
- Missing evidence produces `INSUFFICIENT_EVIDENCE`, never a clean bill of health.
- Policy thresholds are configuration, not scattered constants.

---

## 3. Phase status

| Phase | Scope | Status |
|---|---|---|
| 0 | Monorepo, FastAPI, PostgreSQL schema, Redis, JWT auth | ✅ Done |
| 1 | Mobile shell: 10 screens, navigation, Zustand, API client | ✅ Done |
| 2 | WebSocket transport, session lifecycle, incident records | ✅ Done |
| 3 | **Real-time dashboard architecture and data flow** | ✅ Done |
| 4 | Challenge + independent verification, wired to the dashboard | ✅ Done |
| 5 | Test suite (backend + mobile) and documentation | ✅ Done |
| 6 | Real ML models — AASIST, ECAPA-TDNN, faster-whisper | ✅ Integrated (unevaluated) |
| 7 | Model evaluation — EER/ROC-AUC/FAR-FRR, unseen generators, codecs | ⬜ Next |
| 8 | Real Android audio capture (consented, permissioned) | ⬜ After 7 |
| 8 | Security hardening, load testing, SIH demo hardening | ⬜ After 7 |
| 9 | Optional: blockchain anchoring for evidence integrity | ⬜ Optional |

---

## 4. What was built in this iteration

### Removed
- The Resemble AI adapter, its config keys, env vars, engine fusion branch, and
  every documentation reference. A test now guards against reintroduction.
- A stale duplicate mobile source tree at `apps/mobile/src`, which shadowed the
  real app at `apps/mobile/VoiceShieldApp/src`.

### Backend
- `websocket/events.py` — the single definition of the wire format. Twelve event
  types; every event carries `event_id` (de-duplication) and `seq` (ordering).
- `websocket/manager.py` — connection registry and per-session live state, with
  a `publish()` other modules use to push into an active dashboard.
- `websocket/pipeline.py` — one audio window in, dashboard events out.
- `websocket/gateway.py` — rewritten: authenticates, authorises session
  ownership, and tears down only when the last dashboard disconnects.
- `risk/engine.py` — rewritten around a `RiskResult` carrying score, state,
  reasons, per-stream contributions and an evidence-confidence figure.
- `risk/policy.py` — decisions, recommended actions, and a low-confidence guard
  that refuses to auto-allow a high-consequence request on thin evidence.
- `simulation/mock_audio.py` — DEVELOPMENT MOCK AUDIO, clearly separated from
  real capture.
- ML modules expanded to emit the sub-signals the dashboard renders.
- `/incidents/stats/overview` for the Home dashboard.
- Challenge and verification routes now publish live events and feed their
  outcomes back into the Risk Engine.

### Mobile
- `store/riskStore.ts` — the live dashboard state, with de-duplication, ordering,
  malformed-event tolerance, bounded history and reset-between-calls.
- `CallScreen` — rebuilt as the Live Security Dashboard.
- `HomeScreen` — rebuilt as the Security Overview dashboard.
- New components: risk sparkline, three evidence panels, event timeline,
  decision panel, pipeline-mode banner, stat card, metric row, panel card.
- `wsService` — connection-state subscribers, backoff reconnect, demo control.

### Fixed along the way
- `email-validator` was missing, so the backend could not import at all.
- `bcrypt` 5.x is incompatible with `passlib` 1.7.4 — password hashing raised at
  runtime, breaking login and registration. Pinned to `bcrypt==4.0.1`.
- The mobile test suite could not run: `react-native-gesture-handler` was not
  transformed by Jest.

### Found only by running the app on a device (Android 16 emulator)

- **WebSocket start race.** `wsService.connect()` resolved as soon as the socket
  was *created*, not when it opened, and `CallScreen` then fired `start_demo` on
  a fixed 400 ms timer. When the socket was slower than that, the message was
  silently dropped and the call produced no analysis at all. `connect()` now
  resolves on `onopen` (and rejects when the connection is abandoned), so the
  send cannot be lost.
- **Home never refreshed on return.** Aggregates were fetched in a mount-only
  effect, but the navigator keeps Home mounted, so finishing a call left stale
  counts. Now refreshed with `useFocusEffect`.
- **Interactive outcomes were fused only lazily.** A challenge or verification
  result was written to the authoritative session state and *was* used by the
  Risk Engine — but only on the next audio window, because `compute_risk` ran
  solely from `analyze_window`. Once the audio stopped (exactly when a held
  transaction awaits verification) no window ever arrived, so the decision never
  moved and only the UI badge changed. `recompute_after_outcome()` now re-fuses
  and re-decides the moment an outcome lands, through the same engine and
  policy, and persists the resulting snapshot so `GET /risk/{id}` cannot
  diverge from the dashboard.
- **Header collided with the status bar.** Home has `headerShown: false` and the
  app is edge-to-edge, so its title overlapped the system clock. Added
  `SafeAreaProvider` at the root and a top inset on Home.
- The Android build failed outright: `react-native-reanimated` 4.x requires
  `react-native-worklets` as a **direct** dependency (RN autolinking only
  registers direct dependencies, and Reanimated's Gradle script looks for a
  `:react-native-worklets` subproject). Added the dependency and its required
  Babel plugin.
- The SQLAlchemy models used PostgreSQL-only `JSONB`/`UUID` types, so the
  backend could not run anywhere without a PostgreSQL server. Made them
  dialect-portable with `with_variant`, which leaves PostgreSQL unchanged and
  lets local runs and the SIH demo fall back to SQLite.

---

## 5. WebSocket event contract

Client → server: `audio_chunk`, `start_demo`, `stop_demo`, `ping`.

Server → client:

| Event | Purpose |
|---|---|
| `session_started` | Session opened; carries `pipeline_mode` and model versions |
| `audio_quality` | Level, SNR, clipping, silence, quality band |
| `risk_update` | Score, state, trend, all three evidence objects, decision |
| `detected_event` | One entry on the live timeline |
| `alert` | Elevated-risk alert with a recommended action |
| `challenge_started` / `challenge_result` | Challenge lifecycle |
| `verification_requested` / `verification_result` | Independent verification |
| `policy_decision` | Emitted when the decision changes |
| `session_ended` | Peak risk and the incident id |
| `error` | Non-fatal problem; the dashboard keeps its state |

Every event: `type`, `event_id`, `seq`, `session_id`, `timestamp`.

---

## 6. Phase 6 — real ML integration

Each stub has a single, well-defined seam.

| Replace | With | Seam |
|---|---|---|
| `AuthenticityDetector.analyze` | AASIST / RawNet2 (PyTorch), optionally WavLM / Wav2Vec2-XLSR | Returns `AuthenticityResult`; set `is_mock=False` |
| `SpeakerIdentity._embed` | ECAPA-TDNN 192-d embeddings | Cosine scoring and consistency logic already exist |
| `Transcriber.transcribe` | faster-whisper streaming | Returns `TranscriptSegment`; set `is_mock=False` |
| `ContextClassifier.classify` | Fine-tuned transformer, rules as fallback | Returns `ContextResult` |

Nothing downstream changes: the pipeline, the Risk Engine, the event contract
and the dashboard already consume these shapes.

Also required in this phase: model versioning in incident records (the field
exists), calibration of thresholds against a labelled dataset, and latency
budgeting for on-line inference.

---

## 7. Phase 7 — real Android audio capture

Current state: **development mock audio only.**

Planned path:

```
Android capture (consented, permissioned)
        ↓
PCM 16 kHz mono frames
        ↓
Kotlin native bridge
        ↓
WebSocket (pipeline_mode = "live")
        ↓
existing FastAPI pipeline
```

Constraints that must be stated plainly in any demo or write-up: Android does
not grant applications unrestricted access to raw cellular call audio. The
prototype therefore uses a controlled streaming path. Any capture must be
explicitly consented to and permissioned, and the retention default stays off.

---

## 8. Testing

| Suite | Count | Covers |
|---|---|---|
| `test_risk_engine.py` | 27 | Fusion, state ladder, stale/missing evidence, stream independence, bounds, trend |
| `test_policy.py` | 11 | Decision mapping, insufficient-evidence handling, confidence guard, configurability |
| `test_events.py` | 21 | Envelope, sequencing, uniqueness, builder coverage |
| `test_ml.py` | 30 | Preprocessing, quality, authenticity bands, identity enrolment, context rules |
| `test_pipeline.py` | 14 | Full mock scenario, escalation, timeline de-duplication, silence, malformed audio, reset |
| `test_security.py` | 14 | JWT tampering/forgery/expiry, WS authorisation, secret exposure, evidence integrity |
| `test_websocket_integration.py` | 8 | A real WebSocket: connection, keepalive, malformed input, the full scenario, envelope/sequencing, client audio |
| `riskStore.test.ts` | 33 | Event handling, duplicates, ordering, malformed events, reset |
| `dashboard.test.tsx` | 24 | Every panel renders its required fields; mock labelling |

Not yet covered, and stated plainly: end-to-end tests against a live PostgreSQL
instance (the WebSocket integration suite fakes the database layer), and
on-device testing on physical Android hardware.

---

## 9. Language discipline

Claims that must never appear: "100% accurate", "perfect deepfake detection",
"impossible to fool", "every cloned voice will be detected", "works with
unrestricted Android cellular call audio".

Defensible framing: multi-signal detection, risk-based decisioning, continuous
analysis, adaptive verification, defense-in-depth.
