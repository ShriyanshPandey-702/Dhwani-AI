# Dhwani AI Mobile App — Technical Specification

## 1. Final Technology Stack

| Layer | Technology |
|---|---|
| Mobile | React Native + TypeScript |
| Styling | NativeWind / Tailwind CSS |
| Native Android | Kotlin |
| IDE | VS Code |
| Android tooling | Android Studio SDK/Gradle/emulator |
| Prototype audio transport | WebSocket (LiveKit is not used) |
| Realtime control | WebSocket |
| Backend | Python + FastAPI |
| ML | PyTorch |
| Deepfake detection | AASIST / RawNet2 family |
| Speech representation | WavLM / Wav2Vec2-XLSR |
| Speaker identity | ECAPA-TDNN |
| STT | Whisper / faster-whisper |
| NLP | Hugging Face Transformers |
| Audio processing | torchaudio + DSP |
| Cache/session state | Redis |
| Database | PostgreSQL |
| Auth | JWT + secure Android storage |
| Push | Firebase Cloud Messaging |
| On-device inference | ONNX Runtime Mobile / TensorFlow Lite |
| Evidence integrity | SHA-256 + digital signatures |
| Blockchain roadmap | Hyperledger Fabric |
| Containers | Docker |
| Monitoring roadmap | Prometheus + Grafana |

The source architecture requires real-time analysis, APIs/SDKs, privacy-preserving handling, multilingual support and a mobile extension that is permission-dependent rather than unrestricted cellular-audio access.

## 2. Architecture

```text
┌──────────────────────────────────────┐
│          React Native Android App    │
│ TypeScript + NativeWind + Kotlin     │
│                                      │
│ Call/Session UI                       │
│ Risk Gauge                            │
│ Alerts                                │
│ Challenge                             │
│ Verification                         │
└───────────────┬──────────────────────┘
                │
       WebSocket audio + control/events
                │
                ▼
┌──────────────────────────────────────┐
│             FastAPI Backend           │
│                                      │
│ Auth / Users / Sessions              │
│ WebSocket Gateway                    │
│ Risk Engine                          │
│ Security Policy                      │
│ Challenge Service                   │
│ Verification Service                │
│ Incident Service                    │
└──────────────┬───────────────┬───────┘
               │               │
               ▼               ▼
       ┌─────────────┐   ┌───────────────┐
       │ Redis       │   │ PostgreSQL    │
       │ sessions    │   │ users         │
       │ pub/sub     │   │ incidents     │
       │ realtime    │   │ policies      │
       └─────────────┘   │ evidence      │
                         └───────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│             ML Pipeline              │
│ Python + PyTorch + torchaudio        │
│                                      │
│ Authenticity                          │
│  AASIST / RawNet2                   │
│  WavLM/Wav2Vec2-XLSR                │
│  DSP / Spectral / Prosody           │
│                                      │
│ Identity                             │
│  ECAPA-TDNN                          │
│                                      │
│ Context                              │
│  Whisper + Transformers              │
└──────────────────┬───────────────────┘
                   ▼
              Risk Fusion
                   ▼
       Allow / Verify / Hold / Block
```

## 3. Core Data Flow

```text
Supported live session
      ↓
Audio frames
      ↓
Preprocessing
      ↓
Rolling analysis windows
      ↓
┌────────────┬────────────┬─────────────┐
│Authenticity│ Identity   │ Context     │
│            │            │             │
│AASIST      │ ECAPA      │ Whisper     │
│RawNet2     │ Embedding  │ NLP         │
│DSP         │ Similarity │ Transaction │
│Prosody     │            │ risk        │
└──────┬─────┴──────┬─────┴──────┬──────┘
       └────────────┼─────────────┘
                    ↓
              Risk Engine
                    ↓
             Security Policy
                    ↓
      ┌─────────────┼─────────────┐
      ↓             ↓             ↓
    Allow         Verify       Hold/Block
                    ↓
              Challenge
                    ↓
             OOB Verification
```

Authenticity and context are deliberately kept separate until final policy fusion so a request such as an OTP does not become evidence that the voice itself is synthetic.

## 4. Mobile Architecture

```text
apps/mobile/VoiceShieldApp/
├── App.tsx                      # Root: splash, then the navigator
├── src/
│   ├── screens/                 # Splash, Login, Home, Call, Challenge,
│   │                            # Verification, Incidents, IncidentDetail,
│   │                            # Devices, Settings
│   ├── components/              # RiskGauge, RiskSparkline, AuthenticityPanel,
│   │                            # IdentityPanel, ContextPanel, EventTimeline,
│   │                            # DecisionPanel, AlertCard, PipelineModeBanner,
│   │                            # StatCard, MetricRow, PanelCard, RiskStateBadge
│   ├── navigation/              # AppNavigator (9 routes)
│   ├── hooks/                   # useRiskStream
│   ├── services/
│   │   ├── api/                 # Axios client with token refresh
│   │   ├── websocket/           # wsService (transport only)
│   │   └── auth/                # authService
│   ├── store/                   # Zustand: authStore, sessionStore, riskStore
│   ├── types/                   # Event contract + view models
│   ├── utils/                   # Theme tokens
│   └── config/                  # API base URLs
├── __tests__/                   # riskStore, dashboard, App
└── android/
```

PLANNED for real audio capture (Phase 9):
```text
android/app/src/main/java/com/voiceshieldapp/
├── audio/                       # Consented capture → PCM frames
├── security/                    # Keystore-backed storage
└── bridges/                     # Native module exposed to JS
```

## 5. Monorepo Layout

Actual structure. Directories that do not exist yet are marked PLANNED.

```text
Dhwani Ai/
├── apps/
│   └── mobile/
│       └── VoiceShieldApp/      # React Native app (see section 4)
│
├── services/
│   └── api/
│       ├── main.py
│       ├── schema.sql            # DB schema (migrations/ PLANNED via Alembic)
│       ├── app/
│       │   ├── api/             # auth, users, devices, sessions, risk,
│       │   │                    # incidents, challenge, verification
│       │   ├── core/            # config, security, database, redis
│       │   ├── models/          # SQLAlchemy ORM
│       │   ├── risk/            # engine, policy
│       │   ├── websocket/       # gateway, events, manager, pipeline
│       │   ├── ml/              # authenticity, identity, context, preprocessing
│       │   └── simulation/      # DEVELOPMENT MOCK AUDIO
│       ├── tests/               # pytest suite
│       ├── pytest.ini
│       └── requirements.txt
│
├── training/                    # AASIST model training scripts
├── evaluation/                  # Multi-domain ML evaluation harness
├── experiments/                 # Phase-specific experiment scripts
├── models/                      # Local model weights (ecapa/, whisper/)
│
├── docs/                        # Technical documentation
│   ├── prd.md
│   ├── tech.md
│   ├── test.md
│   ├── models.md
│   ├── DhwaniAI_Project_Context_README.md
│   └── ...
│
├── recording_samples/           # Demo/manual-test audio assets
│   └── demo/
│
├── docker-compose.yml           # Orchestrates all services
├── .env.example
└── README.md
```

PLANNED, not yet present: `proto/` (gRPC definitions, currently at `services/api/proto/`),
`infra/` (Docker, Redis and Postgres configuration beyond docker-compose),
`blockchain/evidence/` (evidence anchoring).

## 6. Setup Prerequisites

Install:
- Node.js LTS
- npm/pnpm
- Python 3.11+
- JDK required by the React Native Android toolchain
- Android Studio
- Android SDK + platform tools
- Android emulator or USB-debuggable Android phone
- Git
- Docker Desktop
- PostgreSQL/Redis locally or via Docker

## 7. Start Mobile App

Example React Native setup:

```bash
git clone <repository>
cd voiceshield

npm install

cd android
./gradlew clean
cd..

npx react-native start
```

In another terminal:

```bash
npx react-native run-android
```

For a physical device:
1. Enable Developer Options.
2. Enable USB debugging.
3. Connect device.
4. Verify with `adb devices`.
5. Run `npx react-native run-android`.

Use Android Studio mainly for SDK/device/Gradle/native Android work; day-to-day React Native development can be done in VS Code.

## 8. Start FastAPI

```bash
cd services/api

python -m venv .venv
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API:
```text
http://localhost:8000
```

Docs:
```text
http://localhost:8000/docs
```

## 9. Start Redis/PostgreSQL

Preferred prototype:

```bash
docker compose up -d postgres redis
```

Set environment variables in `.env`:

```text
DATABASE_URL=postgresql://...
REDIS_URL=redis://localhost:6379
JWT_SECRET=...
FCM_PROJECT_ID=...
```

Never commit real secrets.

## 10. Backend API Groups

The complete route table, verified against the running application.

```text
GET    /health

POST   /auth/register
POST   /auth/login
POST   /auth/refresh
GET    /users/me

GET    /devices
POST   /devices/register
DELETE /devices/{device_id}

POST   /sessions
GET    /sessions
GET    /sessions/{session_id}
POST   /sessions/{session_id}/start
POST   /sessions/{session_id}/stop

WS     /ws/sessions/{session_id}?token=<JWT>

GET    /risk/{session_id}

GET    /incidents
GET    /incidents/stats/overview          # Home security-overview aggregates
GET    /incidents/{incident_id}

POST   /challenge/{session_id}                        # issue a challenge
POST   /challenge/{session_id}/{challenge_id}/result  # record the outcome

POST   /verification/{session_id}/request
POST   /verification/{session_id}/approve
POST   /verification/{session_id}/reject
```

The challenge-result and verification routes publish events into the live
dashboard and feed their outcomes back into the Risk Engine, so an action taken
on the Challenge or Verification screen is reflected on the Live Security
Dashboard without a refresh.

## 11. WebSocket Event Contract

`WS /ws/sessions/{session_id}?token=<JWT access token>`

Authentication is mandatory and checked before the socket is accepted. The
token's user must own the session, and the session must be active.

**Client → server**

| Message | Purpose |
|---|---|
| `{"type": "audio_chunk", "data": "<base64 int16 PCM>"}` | Stream audio |
| `{"type": "start_demo"}` | Run the DEVELOPMENT MOCK AUDIO scenario |
| `{"type": "stop_demo"}` | Stop it |
| `{"type": "ping"}` | Keepalive |

**Server → client envelope**

Every event carries `type`, `event_id`, `seq`, `session_id` and `timestamp`
(ISO-8601 UTC). `event_id` lets the client drop duplicates after a reconnect;
`seq` is monotonic per session and lets it drop stale, out-of-order events.

**`risk_update` — the primary dashboard event**

```json
{
  "type": "risk_update",
  "event_id": "0b9c...",
  "seq": 17,
  "session_id": "sess_123",
  "timestamp": "2026-09-09T09:41:39.204Z",

  "risk_score": 74,
  "risk_state": "high",
  "risk_trend": "rising",
  "evidence_confidence": 0.73,

  "authenticity": {
    "score": 68,
    "spoof_probability": 0.68,
    "confidence": 0.91,
    "acoustic_anomaly": "HIGH",
    "spectral_anomaly": "MEDIUM",
    "prosody_anomaly": "HIGH",
    "model_version": "heuristic-dsp-stub-v0.2",
    "is_mock": true
  },

  "identity": {
    "match_score": 82,
    "confidence": 0.87,
    "consistency": "GOOD",
    "enrollment_status": "VERIFIED",
    "model_version": "ecapa-stub-v0.2",
    "is_mock": true
  },

  "context": {
    "score": 81,
    "confidence": 0.89,
    "urgency": true,
    "financial_request": true,
    "otp_request": true,
    "credential_request": false,
    "sensitive_information_request": false,
    "social_engineering": true,
    "authority_claim": true,
    "consequence": "critical",
    "transcript": "Just confirm the OTP and I will complete the transfer.",
    "model_version": "rules-v0.2",
    "is_mock": false,
    "transcript_is_mock": true
  },

  "decision": "VERIFY",
  "reasons": ["voice_authenticity_anomaly", "high_consequence_request"],
  "consequence": "critical",
  "contributions": {"authenticity": 34.0, "identity": 4.5, "context": 20.25},
  "pipeline_mode": "mock"
}
```

The three evidence streams are separate objects and are never merged. Note
`pipeline_mode` and the per-stream `is_mock` flags: these are how the dashboard
knows to label results as demo data rather than AI detection.

**All server event types**

| Event | Purpose |
|---|---|
| `session_started` | Session opened; carries `pipeline_mode` and model versions |
| `audio_quality` | Level, SNR, clipping, silence flag, quality band |
| `risk_update` | The full risk picture, as above |
| `detected_event` | One entry on the live timeline (`code`, `label`, `stream`, `severity`) |
| `alert` | Elevated-risk alert with a recommended action |
| `challenge_started` | A challenge was issued to the caller |
| `challenge_result` | `passed` / `failed` / `timeout` |
| `verification_requested` | Independent verification raised |
| `verification_result` | `approved` / `rejected` / `timeout` |
| `policy_decision` | Emitted when the security decision changes |
| `session_ended` | Peak risk and the incident id |
| `error` | Non-fatal problem; the dashboard keeps its current state |
| `pong` | Keepalive response (no envelope) |

**Client-side handling requirements**

Duplicate, malformed, out-of-order and unknown events must all be tolerated. A
single bad event must never break the dashboard, and the dashboard must reset
between calls.

## 12. Voice Authenticity Pipeline

Dhwani AI performs authenticity detection with its own pipeline. **No
third-party detection API is called**, and no external detection vendor is a
dependency.

```text
Live audio
    ↓
Audio preprocessing          (decode, normalise, silence gating, quality)
    ↓
Acoustic / spectral analysis
    ↓
Prosody / temporal analysis
    ↓
AASIST / RawNet2 family      ← PLANNED (currently a heuristic DSP stub)
    ↓
Voice authenticity / spoof score
```

SSL representations (WavLM, Wav2Vec2-XLSR) may be used as features where
technically appropriate.

**Current status.** Preprocessing and the acoustic / spectral / prosodic feature
extraction are real computations over the audio buffer. The *model* that would
turn those features into a calibrated spoof probability is not yet trained:
`AuthenticityDetector` is a heuristic stand-in that reports `is_mock=True` on
every result, and the backend propagates that flag to the dashboard.

Rules:
- No single detector is treated as infallible.
- A failure in one evidence stream lowers evidence confidence; it does not stop
  the security system.
- Evidence streams stay independent until the Risk Engine fuses them. A context
  signal never alters the authenticity score.

## 13. Risk Engine

Prototype concept:

```text
Authenticity evidence
Identity evidence
Context evidence
Consequence
Challenge evidence
        ↓
   calibrated fusion
        ↓
Security Risk Index 0–100
        ↓
Security Policy
```

Do not claim a fixed production weight before validation. Start with configurable weights and calibrate against a validation set.

## 14. Five-State Policy

```text
Insufficient Evidence
        ↓
Low / Watch
        ↓
Suspicious
        ↓
High
        ↓
Critical
```

Recommended behavior:
- Low → continue
- Suspicious → warning/challenge
- High → challenge + OOB
- Critical → hold + OOB/escalation

## 15. Development Phases

### Phase 0 — Foundation
- Repository
- React Native app
- FastAPI server
- Auth
- PostgreSQL
- Redis
- WebSocket

### Phase 1 — Mobile UX
- Login
- Home/dashboard
- Call/session screen
- Risk gauge
- Alerts
- Incident screen
- Settings

### Phase 2 — Real-Time Pipeline  ✅ Done
- WebSocket transport (no LiveKit; plain WebSocket is sufficient for the prototype)
- Audio streaming and rolling windows
- Structured risk events
- Development mock audio, clearly labelled

### Phase 3 — Real-Time Dashboard  ✅ Done
- Event contract with de-duplication and ordering
- Zustand live session store
- Live Security Dashboard (gauge, graph, evidence panels, timeline, decision)
- Home Security Overview dashboard

### Phase 4 — Prevention  ✅ Done
- Challenge issue and outcome
- Independent out-of-band verification
- Hold/block workflow driven by the Policy Engine
- Explainability (decision reasons, per-stream contributions)

### Phase 5 — ML  ✅ Done (models + evaluation)
- AASIST / AASIST-L authenticity model ✅
- ECAPA-TDNN speaker verification ✅
- faster-whisper transcription ✅
- Conversation context — rules, not a transformer classifier (unchanged)
- Threshold calibration against labelled datasets ✅ — **measured, and the
  measurement says thresholds do not transfer across attack families**, so no
  Risk Engine threshold was changed. See `docs/ml_evaluation.md` §8.

Evaluated on ASVspoof 2019 LA (full) and MLAAD-tiny: ROC-AUC 0.9987 in-domain,
**0.6055 on unseen modern TTS**. Robustness (19 conditions), calibration and
streaming stability are all measured and reported.

### Phase 6 — Security/Privacy
- Secure storage
- TLS
- consent
- minimal retention
- evidence hashing
- audit logs

### Phase 7 — Testing  ◐ Partial
Done: unit tests for the Risk Engine, Policy Engine, event contract, ML modules
and the full mock pipeline; mobile store and dashboard tests; security tests for
JWT handling, WebSocket authorisation, secret exposure and evidence integrity.

Outstanding: integration tests against live PostgreSQL, WebSocket tests with a
real authorised session, on-device testing, performance and accessibility
testing.

### Phase 9 — Real Android Audio Capture  ⬜ After Phase 5
- Consented, permissioned capture
- Kotlin native bridge producing 16 kHz mono PCM frames
- `pipeline_mode = "live"` through the identical backend pipeline

### Phase 8 — SIH Demo Hardening
- Local-loopback fallback
- Preloaded test scenarios
- Mock OOB service
- Demo data
- Code freeze
- Backup video

The core MVP is controlled live streaming, a three-stream risk engine, active
challenge-response, a protective workflow and explainability. Production telecom
adapters and ledger integrations are roadmap items.

## 16. User Flow

```text
Install
 ↓
Login
 ↓
Register trusted device
 ↓
Permissions
 ↓
Home
 ↓
Supported monitored call/session
 ↓
Monitoring active
 ↓
Continuous analysis
 ↓
Low ─────────────→ Continue
 ↓
Suspicious ──────→ Warning/Challenge
 ↓
High ────────────→ Challenge + OOB
 ↓
Critical ────────→ Hold
                       ↓
                  OOB approval
                  ↙         ↘
              Approved     Rejected
                 ↓             ↓
               Allow        Block/Escalate
```

## 17. Folder/Module Ownership

- Mobile: `apps/mobile/VoiceShieldApp/src`
- Backend: `services/api/app` (`api/`, `core/`, `models/`, `risk/`, `websocket/`)
- ML: `services/api/app/ml` and `services/api/app/simulation`
- Database: `services/api/schema.sql`
- DevOps: `docker-compose.yml` (an `infra/` tree is PLANNED)
- Security/evidence: `app/core/security.py` and the incident integrity hash
  (a `blockchain/evidence/` tree is PLANNED)
- QA: `services/api/tests`, `apps/mobile/VoiceShieldApp/__tests__`, `docs/test.md`

## 18. Architecture Principles

1. Mobile is a client, not the entire security platform.
2. Backend uses FastAPI for the prototype.
3. ML remains Python-native.
4. Real-time audio and control traffic are logically separate.
5. Authenticity ≠ identity ≠ context.
6. Risk fusion happens only at the policy layer.
7. Detection failure must degrade safely.
8. No single evidence stream is a point of failure; losing one lowers
   evidence confidence rather than stopping the system.
9. No raw audio retention by default.
10. High-consequence actions require independent verification when policy says so.

---

## 19. Real-Time Dashboard Data Flow

Dhwani AI includes a real-time in-app Security Dashboard that visualizes
continuously changing authenticity, identity, context, risk, events and security
decisions during an active monitored call.

```text
Backend analysis window
        ↓
Risk Engine → Policy Engine
        ↓
events (app/websocket/events.py)
        ↓
WebSocket
        ↓
wsService                 (transport only: connect, keepalive, reconnect)
        ↓
useRiskStream             (subscription bridge)
        ↓
riskStore.applyEvent      (validation, de-duplication, ordering)
        ↓
Live Security Dashboard   (gauge · graph · panels · timeline · decision)
```

The backend is authoritative. The client computes no risk value of its own; it
records what arrived and renders it.

**Store responsibilities.** `riskStore` holds `riskScore`, `riskState`,
`riskTrend`, `riskHistory` (bounded to 120 observations), `evidenceConfidence`,
the three evidence objects, `audioQuality`, `detectedEvents`, `alerts`,
`decision` with `decisionReasons`, `challengeState`, `verificationState`,
`sessionStatus`, `pipelineMode` and `lastUpdated`. An update never overwrites an
evidence stream the event did not carry.

**Edge cases handled.** Duplicate events (by `event_id`), out-of-order and stale
events (by `seq`, tolerating a reconnect's sequence restart), malformed events
and missing fields, unknown event types, reconnects with backoff, session
termination, dashboard reset between calls, backend unavailability and temporary
network loss. One malformed event never breaks the dashboard.

---

## 20. Implementation Status

| Component | Status |
|---|---|
| FastAPI backend, auth, sessions, incidents | REAL |
| WebSocket gateway and event contract | REAL |
| Risk Engine, Policy Engine | REAL |
| Challenge and independent verification | REAL |
| Live Security Dashboard, Home Overview dashboard | REAL |
| Audio preprocessing and quality measurement | REAL |
| Conversation-context signal rules | REAL |
| Evidence integrity (SHA-256) | REAL |
| Voice authenticity model | REAL — AASIST/AASIST-L pretrained checkpoint, **evaluated**: ROC-AUC 0.9987 in-domain / **0.6055 unseen TTS** |
| Speaker identity model | REAL — ECAPA-TDNN pretrained checkpoint (not independently evaluated) |
| Speech-to-text | REAL — faster-whisper, chunked windows (WER unmeasured) |
| Demo backends | REAL — deterministic heuristics retained for the SIH demonstration |
| Audio source | MOCK — development mock audio; Android capture planned |
| Blockchain evidence anchoring | PLANNED |

Selected by `PIPELINE_MODE` (`mock` default, or `real_ml`). Each stream falls
back independently and labels the fallback; a fallback is never presented as
real ML. Model provenance, licences, preprocessing and measured latency are documented
in `docs/models.md`; the full evaluation, robustness, calibration and Risk
Engine tuning analysis is in `docs/ml_evaluation.md`.

**Resemble AI is not used.** No third-party detection API is called.
