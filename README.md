# Dhwani AI 🛡

**Real-time voice-impersonation defence — SIH 2026, Problem Statement 26104**

> DETECT → SCORE → CHALLENGE → VERIFY → PROTECT

Dhwani AI is not a deepfake classifier. It is a security system for the moment
that actually matters: a human is on a live call and is about to make a
consequential decision because they believe the caller is genuine.

It combines three **independent** evidence streams — voice authenticity, speaker
identity and conversation context — fuses them in a Risk Engine, and lets a
configurable Policy Engine decide whether the action may proceed, needs
verification, or must be held.

Dhwani AI includes a **real-time in-app Security Dashboard** that visualises
continuously changing authenticity, identity, context, risk, events and security
decisions during an active monitored call.

**Resemble AI is not used.** Authenticity detection is Dhwani AI's own
pipeline; no third-party detection API is called.

---

## Architecture

```
                     MOBILE APP (React Native)
                              │
                 ┌────────────┴────────────┐
                 │                         │
            Call Audio            Live Security Dashboard
                 │                         │
                 └────────────┬────────────┘
                              │
                          WebSocket
                              │
                              ▼
                      FASTAPI BACKEND
                              │
                              ▼
                        ML PIPELINE
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
    Authenticity          Identity             Context
    (DSP stub →          (stub →            (rules, live;
     AASIST/RawNet2)      ECAPA-TDNN)        STT stub → Whisper)
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                        RISK ENGINE  (0–100 Security Risk Index)
                              ▼
                       POLICY ENGINE  (ALLOW / VERIFY / HOLD / BLOCK)
                              ▼
                          WebSocket
                              │
                              ▼
                       ZUSTAND STORE
                              │
                              ▼
                  LIVE SECURITY DASHBOARD
```

The backend is **authoritative**. The mobile app never computes a risk score; it
receives events and visualises them.

---

## Implementation status

Nothing below is described as complete unless it actually is.

| Component | Status | Notes |
|---|---|---|
| FastAPI backend, auth, sessions, incidents | **Real** | JWT, PostgreSQL, Redis client |
| WebSocket gateway + event contract | **Real** | 12 event types, seq + event_id per event |
| Risk Engine (fusion, states, trend) | **Real** | Deterministic, 27 unit tests |
| Policy Engine (decisions, thresholds) | **Real** | Config-driven, 11 unit tests |
| Challenge + independent verification flow | **Real** | REST + live dashboard events |
| Live Security Dashboard (mobile) | **Real** | Driven end-to-end by WebSocket events |
| Home Security Overview dashboard | **Real** | Backed by `/incidents/stats/overview` |
| Evidence integrity (SHA-256) | **Real** | Hash over the incident evidence summary |
| Audio preprocessing + quality metrics | **Real** | Decode, silence gating, SNR/level/clipping |
| Conversation-context signal rules | **Real** | Deterministic lexical rules, unit tested |
| Voice authenticity model | **REAL (pretrained)** | AASIST / AASIST-L, MIT. Pretrained on ASVspoof 2019 LA by its authors; **not evaluated by us** |
| Speaker identity model | **REAL (pretrained)** | ECAPA-TDNN (`spkrec-ecapa-voxceleb`), Apache-2.0. Thresholds **uncalibrated** for our channel |
| Speech-to-text | **REAL (pretrained)** | faster-whisper, MIT. Chunked-window transcription; multilingual accuracy **unmeasured** |
| Heuristic/demo backends | **REAL (deterministic)** | Retained for the SIH demonstration; always labelled, never presented as ML |
| Audio source | **MOCK** | Synthetic PCM. Android capture planned |
| Blockchain evidence anchoring | **PLANNED** | Not implemented |

**Two independent switches, never conflated:** `risk_update.pipeline_mode` is the
audio *source* (`mock`/`live`); each evidence object carries its own
`pipeline_mode` for the *inference backend* (`real_ml` / `heuristic_demo` /
`heuristic_fallback`). A fallback is never presented as real ML — on the wire
(`is_mock`) or in the UI (banner plus per-panel provenance notes).

Set `PIPELINE_MODE=real_ml` and run `python scripts/fetch_models.py` to use the
real models. The default stays `mock` so the demonstration is deterministic.

**No accuracy claim is made.** Dhwani AI has run no evaluation of these
checkpoints on its own data. See `docs/models.md`.

---

## Quick start

### Prerequisites

- Python 3.10+
- Node.js ≥ 22.11
- Docker Desktop
- Android Studio + SDK, JDK 17+

### 1. Environment

```bash
cp .env.example .env
# Set JWT_SECRET to a long random string.
```

### 2. Database

Full setup uses PostgreSQL:

```bash
docker compose up -d postgres redis
```

For a local run or the SIH demo no database server is needed — the models are
dialect-portable, so SQLite works out of the box. Put this in `.env` instead:

```bash
DATABASE_URL=sqlite+aiosqlite:///./voiceshield.db
```

Redis is configured but not yet used at runtime, so it is optional either way.

### 3. Backend

```bash
cd services/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

The schema is created on startup. From the Android emulator the app reaches
the backend at `http://10.0.2.2:8000` (see `src/config/api.ts`).

### 4. Mobile app

```bash
cd apps/mobile/VoiceShieldApp
npm install
npx react-native start
# In another terminal:
npx react-native run-android
```

### 5. Tests

```bash
# Backend  — 125 tests
cd services/api &&.venv/bin/python -m pytest

# Mobile   — 57 tests
cd apps/mobile/VoiceShieldApp && npm test

# Types
cd apps/mobile/VoiceShieldApp && npx tsc --noEmit
```

---

## Screens

Ten screens: one rendered before the navigator, nine navigator routes.

| Screen | Route | Purpose |
|---|---|---|
| Splash | pre-navigator (`App.tsx`) | Branding while the session is restored |
| Login | `Login` | Authentication |
| Home | `Home` | **Security Overview dashboard** — today's activity, recent calls |
| Active Call | `Call` | **Live Security Dashboard** |
| Challenge | `Challenge` | Issue a challenge, record the outcome |
| Verification | `Verification` | Independent out-of-band approval |
| Incident History | `Incidents` | Past incidents |
| Incident Detail | `IncidentDetail` | Evidence summary + integrity hash |
| Device Trust | `Devices` | Trusted devices |
| Settings | `Settings` | Privacy, pipeline status, security posture |

---

## The two dashboards

**Home — Security Overview** (historical/aggregate): calls today, alerts,
high/critical count, safe count, average risk, and recent monitored calls that
open into Incident Detail.

**Active Call — Live Security Dashboard** (continuously changing): Security Risk
Index and trend, live risk graph, the three evidence panels, the detected-events
timeline, alerts, the current security decision with its reasons, and the
Challenge / Independent Verification actions.

Both update from backend data. Neither requires a manual refresh.

---

## Project structure

```
voiceshield/
├── apps/mobile/VoiceShieldApp/    # React Native + TypeScript
│   ├── src/
│   │   ├── screens/               # 10 screens
│   │   ├── components/            # Gauge, sparkline, evidence panels, timeline…
│   │   ├── navigation/            # AppNavigator
│   │   ├── store/                 # Zustand: auth, session, risk (live dashboard)
│   │   ├── services/              # API client, WebSocket, auth
│   │   ├── hooks/                 # useRiskStream
│   │   ├── types/                 # Event contract + view models
│   │   └── utils/                 # Theme tokens
│   └── __tests__/                 # Store + dashboard tests
├── services/api/                  # FastAPI backend
│   ├── main.py
│   ├── app/
│   │   ├── api/                   # auth, users, devices, sessions, risk,
│   │   │                          # incidents, challenge, verification
│   │   ├── core/                  # config, security, database, redis
│   │   ├── models/                # SQLAlchemy ORM
│   │   ├── risk/                  # engine, policy
│   │   ├── websocket/             # gateway, events, manager, pipeline
│   │   ├── ml/                    # authenticity, identity, context, preprocessing
│   │   └── simulation/            # DEVELOPMENT MOCK AUDIO
│   ├── tests/                     # pytest suite
│   └── requirements.txt
├── database/schema.sql
├── docs/                          # prd.md, tech.md, test.md
├── implementation_plan.md
├── docker-compose.yml
└──.env.example
```

---

## Key design decisions

1. **Authenticity ≠ Identity ≠ Context.** Three independent streams, fused only
   in the Risk Engine. A speaker mismatch is evidence about identity, not proof
   of synthesis. An OTP request is evidence about the ask, not about the voice.
2. **Missing evidence is never a verdict.** Silence, a dropped stream or an
   unenrolled speaker yields `INSUFFICIENT_EVIDENCE`, and a high-consequence
   request under thin evidence escalates to VERIFY rather than ALLOW.
3. **The backend is authoritative.** The dashboard renders what it is told.
4. **Policy is configuration, not code.** Thresholds and weights live in a
   versioned policy record.
5. **The voice channel is never the only source of trust.** Consequential
   actions require an independent verification channel.
6. **No secrets in the APK.** The mobile app holds no API keys.
7. **Mock is labelled mock.** Demo data flows through the same pipeline real
   audio will use, and says so on screen.

---

## Demo scenario

The scripted scenario a monitored call runs through, driven by mock audio
through the real pipeline:

| Step | Risk | State | Decision | What appears |
|---|---|---|---|---|
| 1 | 6 | Insufficient evidence | ALLOW | Monitoring begins |
| 2 | 14 | Insufficient evidence | ALLOW | Authority claim detected |
| 3 | 21 | Low | ALLOW | Urgency detected |
| 4 | 35 | Low | ALLOW | Financial request, social-engineering pattern |
| 5 | 40 | Suspicious | VERIFY | Suspicious threshold crossed |
| 6 | 47 | Suspicious | VERIFY | Prosody anomaly increased |
| 7 | 68 | High | VERIFY | OTP request detected, high threshold crossed |
| 8 | 79 | High | VERIFY | Sensitive information requested |
| 9 | 85 | Critical | HOLD | Acoustic anomaly, critical threshold crossed |
| 10–12 | 87→93 | Critical | HOLD | Held pending independent verification |

The call ends with an incident recorded and a SHA-256 integrity hash over the
evidence summary.

---

## Scope and limitations

Dhwani AI performs **multi-signal detection** and **risk-based decisioning**
with **continuous analysis**, **adaptive verification** and **defense in depth**.

It does not claim perfect detection. Its authenticity detector has now been
measured, and the result is deliberately reported in full rather than
summarised favourably:

| Protocol | Scope | ROC-AUC | EER |
|---|---|---|---|
| ASVspoof 2019 LA (the corpus AASIST was trained on) | full corpus | 0.9987 | 1.07% |
| MLAAD-**tiny** subset, unseen modern TTS | subset, not full MLAAD | **0.6055** | **43.40%** |
| WaveFake subset, unseen vocoders on LJSpeech | subset, single speaker | **0.5970** | **41.60%** |

The out-of-domain rows are **subsets**, and the WaveFake row is single-speaker
read speech — diagnostic, not a real-world performance claim. Dhwani AI has
measured **no** real-world or telephony performance.

**The in-domain number is not the deployment number.** On both out-of-domain
corpora the detector is close to a coin flip, and 7 of 22 unseen MLAAD
generators score below chance. A threshold chosen to admit ≤ 1% of spoofs
admitted 16.93% one split later. There is therefore no operating point we can
honestly advertise, and no accuracy claim is made for live calls.

The cause is not simply that modern TTS is good. On WaveFake the detector gave
*genuine human speech* a mean spoof probability of **0.906**, and did no better
on unseen vocoders than on the ones its threshold was tuned on. The model
generalises poorly to unfamiliar recording conditions in **both** classes.

This is *why* the architecture keeps three independent evidence streams. In a
measured simulation of total authenticity failure — an unseen generator scored
as bona fide — the identity and context streams still escalate a
critical-consequence call to VERIFY. That property does not depend on which TTS
the attacker uses.

Robustness, calibration, streaming stability, the full threshold-transfer
analysis and the Risk Engine tuning decisions are in
**[`docs/ml_evaluation.md`](docs/ml_evaluation.md)**, with raw scores and
leakage audits under `evaluation/results/`.

Dhwani AI has not been measured on telephony codecs, Indian-English, or live
call audio. The deterministic heuristic backends remain available and are always
labelled; a fallback is never presented as real ML.

Dhwani AI also does not claim access to unrestricted Android cellular call
audio. The prototype uses a controlled streaming path, and real on-device
capture is a later phase with its own consent and permission requirements.
