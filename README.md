# Dhwani AI

> A real-time voice security platform for detecting synthetic or cloned speech, analyzing speaker consistency, and generating risk-aware security decisions.

---

## Overview

**Dhwani AI** is an intelligent, multi-layered voice security and fraud-prevention platform designed to safeguard voice interactions against AI-driven impersonation, deepfake synthesis, and voice cloning attacks.

By analyzing live audio streams and recorded voice media across acoustic authenticity, speaker identity verification, and conversational context, Dhwani AI produces dynamic, low-latency risk evaluations and automated security enforcement actions before fraudulent transactions or data breaches can take place.

---

## Core Capabilities

- **Real-Time Voice Authenticity Analysis**: High-speed acoustic feature extraction to identify synthetic speech, voice cloning artifacts, and vocoder signatures.
- **Synthetic & Deepfake Detection**: Graph neural network inference targeting spectral artifacts, temporal inconsistencies, and synthetic phase anomalies.
- **Speaker Identity & Consistency Verification**: Neural speaker embeddings comparing the active voice against enrolled profiles or analyzing intra-call speaker stability.
- **Speech-to-Text Context & Threat Analysis**: Conversational transcription coupled with linguistic threat analysis to flag social engineering tactics, urgency triggers, and financial coercion.
- **Acoustic & Spectral Feature Inspection**: Comprehensive frequency, spectral flux, and energy distribution metrics for deep audio forensics.
- **Prosody & Behavioral Signal Processing**: Evaluation of pitch variations, cadence anomalies, and unnatural synthesis cadences where implemented.
- **Dynamic Risk Scoring**: Multi-stream probabilistic fusion combining acoustic authenticity, identity consistency, and semantic threat into a unified 0–100 risk score.
- **Configurable Security Policy Engine**: Automated policy rules translating risk scores into actionable real-time security postures: `ALLOW`, `VERIFY`, `CHALLENGE`, `HOLD`, `BLOCK`, and `ESCALATE`.
- **Live Microphone Stream Analysis**: Ultra-low-latency bidirectional streaming over WebSockets for live conversations and interactive monitoring.
- **Audio-File Forensic Analysis**: Bounded, multi-window forensic examination for uploaded recordings (WAV, MP3, M4A) with detailed visual breakdown and audit reports.
- **Telephony & VoIP Integration**: Seamless call monitoring with PBX/VoIP platforms via Asterisk ARI, Unicast RTP streaming, and real-time call interception.
- **Android Call-Screening Metadata Integration**: Native Android call-screening service bridging incoming telecom metadata directly with background security analysis.
- **Developer REST & WebSocket Integration**: Clean, modular API contracts and typed WebSocket message formats for enterprise integration.
- **Integration-Ready SDK Layer**: TypeScript/JavaScript and Python client interfaces for embedding Dhwani AI into mobile applications, contact centers, and fintech workflows.

---

## Architecture & Detection Pipeline

Dhwani AI processes audio through an end-to-end, multi-modal pipeline:

```
                      +-----------------------------+
                      |        Audio Source         |
                      | (Microphone / File / VoIP)  |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |     16 kHz Mono PCM Audio   |
                      |   (Bounded Buffer / Chunk)  |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |     Real-Time Streaming     |
                      |   (WebSocket / RTP Frame)   |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |     VAD & Speech Gating     |
                      |        (Silero VAD)         |
                      +-----------------------------+
                                     |
               +---------------------+---------------------+
               |                     |                     |
               v                     v                     v
     +-------------------+ +-------------------+ +-------------------+
     |   Authenticity    | |  Speaker Identity | |  Context / Threat |
     |     Analysis      | |   Verification    | |     Analysis      |
     |   (AASIST-L)      | |   (ECAPA-TDNN)    | | (faster-whisper / |
     |                   | |                   | |     Deepgram)     |
     +-------------------+ +-------------------+ +-------------------+
               |                     |                     |
               +---------------------+---------------------+
                                     |
                                     v
                      +-----------------------------+
                      |     Dynamic Risk Engine     |
                      |  (Multi-Modal Evidence-     |
                      |      Corroborated Fusion)   |
                      +-----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Security Policy Engine    |
                      |   (Configurable Thresholds) |
                      +-----------------------------+
                                     |
                                     v
               +-------------------------------------------+
               |             Security Decision             |
               |                                           |
               |   ALLOW      - Benign voice verified      |
               |   VERIFY     - Secondary check requested  |
               |   CHALLENGE  - Interactive liveness check |
               |   HOLD       - Suspend active transaction |
               |   BLOCK      - Terminate synthetic stream |
               |   ESCALATE   - Alert fraud operations     |
               +-------------------------------------------+
```

---

## Technology Stack

| Domain | Technologies & Libraries | Role |
|--------|--------------------------|------|
| **Backend & API** | Python 3.10+, FastAPI, Uvicorn, WebSockets, Structlog | High-throughput asynchronous REST and WebSocket server |
| **Acoustic Authenticity** | PyTorch, AASIST-L (Graph Attention Network) | Spectral and temporal deepfake voice detection |
| **Speaker Identity** | SpeechBrain, ECAPA-TDNN | Neural speaker embeddings and cosine identity verification |
| **Speech-to-Text & NLP** | faster-whisper, Deepgram Nova-2 | High-speed contextual transcription and linguistic threat classification |
| **Voice Activity Detection** | Silero VAD | Real-time speech gating and silence suppression |
| **Telephony Gateway** | Asterisk PBX, Asterisk REST Interface (ARI), Unicast RTP | In-band call monitoring and carrier-grade VoIP bridging |
| **Mobile Application** | React Native, TypeScript, Reanimated, React Navigation | Cross-platform operator console and real-time fraud monitor |
| **Native Android Layer** | Kotlin, Android Telecom API, AudioRecord | Call screening service and hardware audio capture |
| **Data Persistence** | SQLite (Local Dev via aiosqlite), PostgreSQL (Production), SQLAlchemy | Incident storage, session auditing, and configuration |

---

## Repository Structure

```
Dhwani Ai/
├── README.md                   # Public project documentation & architecture overview
├── .env.example                # Configuration template (keys & credentials placeholder)
├── .gitignore                  # Git exclusions (keystores, credentials, datasets, virtualenvs)
├── docker-compose.yml          # Container configuration for local service deployment
│
├── apps/
│   └── mobile/
│       └── DhwaniAIApp/        # React Native mobile application
│           ├── android/        # Android native source (Kotlin telecom & audio modules)
│           ├── ios/            # iOS native project
│           ├── src/            # React Native components, screens, hooks, stores
│           └── __tests__/      # Mobile Jest unit and integration tests
│
├── services/
│   ├── api/                    # Core backend service
│   │   ├── app/                # FastAPI application (ML core, risk engine, routes)
│   │   │   ├── api/            # API endpoints (analysis, websocket, incidents)
│   │   │   ├── ml/             # Inference pipelines (authenticity, identity, context)
│   │   │   ├── risk/           # Risk calculation and policy rule evaluation
│   │   │   └── models/         # Database schemas and data models
│   │   ├── models/             # Checkpoints directory (AASIST, ECAPA-TDNN, Whisper)
│   │   ├── schema.sql          # Database relational schema definition
│   │   └── tests/              # Pytest backend test suite
│   │
│   └── telephony/              # Asterisk ARI telephony integration service
│       ├── asterisk/           # Asterisk configuration files (ari.conf, extensions.conf)
│       ├── gateway/            # Audio gateway bridging RTP streams to WebSocket
│       └── tests/              # Telephony integration and enforcement tests
│
├── recording_samples/          # Controlled sample audio recordings for testing & demos
│   ├── README.md               # Audio catalog and scenario documentation
│   └── demo/                   # Representative samples (synthetic, ambient, human)
│
├── models/                     # Shared local model checkpoints
├── evaluation/                 # ML evaluation harness, benchmark scripts, and metrics
├── experiments/                # Research scripts and exploration artifacts
├── training/                   # Model training and fine-tuning pipelines
└── docs/                       # Technical architecture, model cards, and documentation
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Java 17+ and Android SDK (for mobile Android development)
- Docker & Docker Compose (optional, for containerized services)

### 2. Clone the Repository

```bash
git clone https://github.com/your-org/dhwani-ai.git
cd "dhwani-ai"
```

### 3. Configure Environment

Create your local `.env` configuration from the provided template:

```bash
cp .env.example .env
```

Review `.env` and configure local parameters. For optional cloud STT transcription (e.g., Deepgram Nova-2), supply your private API key locally.

### 4. Setup Backend Environment

```bash
# Navigate to backend directory
cd services/api

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 5. Launch the Backend API

```bash
# Run FastAPI server with auto-reload
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

The REST API will be available at `http://localhost:8000`, with interactive OpenAPI documentation at `http://localhost:8000/docs`.

### 6. Run the Mobile Application

```bash
# Navigate to mobile project directory
cd apps/mobile/DhwaniAIApp

# Install dependencies
npm install

# Start Metro bundler
npm start

# In a separate terminal, build and run on connected Android device / emulator
npm run android
```

---

## Configuration & Environment Variables

All runtime settings are declared in `.env.example`. Key settings include:

| Variable | Default / Example | Description |
|----------|-------------------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./dhwaniai.db` | Local async database connection string |
| `PIPELINE_MODE` | `real_ml` | Inference mode: `real_ml` (neural models) or `mock` (DSP heuristics) |
| `AASIST_VARIANT` | `AASIST-L` | Authenticity model variant (`AASIST-L` or `AASIST`) |
| `AASIST_CASCADE` | `true` | Enables cascading to larger model for borderline scores |
| `ANALYSIS_WINDOW_MS` | `4038` | Model window length (64,608 samples at 16 kHz) |
| `ANALYSIS_HOP_MS` | `1000` | Sliding window hop step (16,000 samples at 16 kHz) |
| `DEEPGRAM_API_KEY` | *(blank)* | Optional Deepgram Nova-2 API key for cloud STT |
| `ARI_USER` | `voiceshield` | Asterisk REST Interface username |
| `ARI_PASSWORD` | *(local secret)* | Asterisk REST Interface authentication secret |

> **Notice**: Never commit `.env` or files containing live credentials. Store credentials in secure secret managers or local environment variables.

---

## Security Policy & Secrets Handling

- **Zero-Secret Commitment**: Private keys, `.env` files, production database connection strings, and certificates must never be committed to Git.
- **Keystore Protection**: Android signing keystores (`*.keystore`, `*.jks`) are strictly excluded via `.gitignore`. Developers must generate local debug keystores for local builds.
- **Local Runtime Segregation**: Dynamic runtime artifacts (e.g., Asterisk credentials, runtime databases) are gitignored and generated locally during deployment.

---

## Testing

Comprehensive test suites cover each layer of the platform:

### Backend Test Suite
```bash
# Run all backend unit and integration tests
cd services/api
pytest tests/ -v
```

### Telephony Gateway Tests
```bash
# Run Asterisk ARI gateway and call enforcement tests
PYTHONPATH=. pytest services/telephony/tests/ -v
```

### Mobile Application Tests
```bash
cd apps/mobile/DhwaniAIApp

# Run Jest unit and component tests
npm test -- --watchAll=false

# Run TypeScript static type checking
npx tsc --noEmit
```

### Android Native Module Build Verification
```bash
cd apps/mobile/DhwaniAIApp/android
./gradlew compileDebugKotlin
```

---

## Demo & Sample Audio Recordings

The `recording_samples/` directory provides curated, controlled audio recordings intended for:
- Manual forensic upload demonstrations via the mobile app
- Audio processing pipeline verification
- Local development testing

```
recording_samples/
├── README.md
└── demo/
    ├── ElevenLabs_*.mp3                 # High-confidence synthetic speech sample
    ├── hi--my-name-is-priyanshu--and-.wav # Real human reference audio
    └── test.wav                         # Multi-modal evaluation clip
```

> **Note on Sample Recordings**: Sample recordings are provided for local pipeline testing and evaluation. Results depend on the input audio and should not be interpreted as universal production accuracy guarantees.

---

## Disclaimer

**Dhwani AI** provides probabilistic security assessments based on deep learning and acoustic signal analysis. While designed to detect synthetic voice artifacts and anomalies with high sensitivity, no automated voice detection system is 100% infallible against novel or adversarial synthesis techniques. Dhwani AI should be integrated as part of a defense-in-depth security strategy alongside multi-factor verification, operational monitoring, and human review for high-consequence operations.
