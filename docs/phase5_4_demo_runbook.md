# Dhwani AI — Final Demo Runbook (Phase 5.4 Freeze)

This is the definitive, authoritative runbook for the demonstration of **Dhwani AI**. It details the exact system architecture, prerequisites, service startup commands, preflight checks, scenario sequences, live presentation flows, recovery procedures, and scientific claim boundaries.

---

## 1. System Architecture

Dhwani AI is a real-time, hybrid telephony and mobile security platform designed to detect, score, challenge, and protect against synthetic voice attacks (deepfakes) and telephony fraud.

```
                      ┌───────────────────────────────────────┐
                      │            Asterisk 20                │
                      │         (Docker Container)            │
                      │                                       │
Caller / VoIP UAC ───►│ SIP :5060 (Signaling)                 │
                      │ RTP :10000-10020 (20 ms G.711u)       │
                      │ ARI :8088 (REST & WebSocket Events)   │
                      └──────────────────┬────────────────────┘
                                         │ externalMedia (slin16 RTP)
                                         ▼
                      ┌───────────────────────────────────────┐
                      │    Telephony Audio Gateway (Python)   │
                      │    - UDP RTP Receiver (:20000)        │
                      │    - PCM Accumulator (250 ms chunks)  │
                      │    - Asterisk ARI Controller          │
                      │    - Challenge State Machine          │
                      └──────────────────┬────────────────────┘
                                         │ WebSocket (:8000/ws/sessions)
                                         ▼
                      ┌───────────────────────────────────────┐
                      │       FastAPI Real ML Backend         │
                      │    - StreamWindower (4.038s window)   │
                      │    - AASIST-L (Authenticity)          │
                      │    - ECAPA-TDNN (Speaker Identity)    │
                      │    - faster-whisper (Context/ASR)     │
                      │    - Multi-Factor Risk Engine         │
                      │    - Security Policy (ALLOW/VERIFY/   │
                      │      HOLD/BLOCK)                      │
                      │    - SQLite (Tamper-Evident Audit)    │
                      └──────────────────┬────────────────────┘
                                         │ REST & WebSockets
                                         ▼
                      ┌───────────────────────────────────────┐
                      │   Android Mobile App (React Native)   │
                      │    - CallScreeningService (< 5 ms)    │
                      │    - Real-Time Risk Dashboard HUD     │
                      │    - Threat Indicators & Incidents    │
                      └───────────────────────────────────────┘
```

---

## 2. What Dhwani AI Can Demonstrate

1. **Real-time Controlled VoIP Telephony**:
   - Dhwani AI receives live 20ms RTP packets, converts/accumulates them into the configured PCM analysis windows, and performs ML inference on those analysis windows.
   - Jitter-tolerant accumulation into 250 ms network chunks and 4.038-second analysis windows.
2. **Deep Learning Inference in Real Time**:
   - **AASIST-L** (85k parameters, raw waveform graph attention) producing calibrated authenticity scores on 4.038s PCM windows.
   - **ECAPA-TDNN** generating speaker embeddings and calculating cosine similarity against enrolled references.
   - **faster-whisper** generating live transcription and keyword risk signals.
3. **Multi-Factor Risk Scoring & Corroboration**:
   - Mathematical risk synthesis: `Authenticity (0.50) + Identity (0.25) + Context (0.25)`.
   - Gated corroboration: uncorroborated single-signal risk is strictly capped at 38 points to prevent false-positive call blocking.
4. **Interactive Challenge-Response**:
   - Dynamic prompt selection (phrases, digits, sequences).
   - In-call caller muting during prompt playback on Asterisk.
   - Response listening window with strict timeout cutoff.
   - Post-challenge risk deflation upon pass or escalation upon timeout/failure.
5. **Real-Time Telephony Enforcement**:
   - Live Asterisk `HOLD` (media isolation) and `ALLOW` (unhold/resume).
   - Immediate `BLOCK` termination via SIP BYE / Asterisk channel destruction.
6. **Watchdogs & Resilience**:
   - RTP inactivity watchdog terminating dead connections cleanly with normal hangup after configured 5.0s.
   - Backend WebSocket disconnect detection with fail-safe teardown.
   - Selective startup reconciliation ensuring only Dhwani AI-owned resources are reaped while foreign resources are preserved.
7. **Android Call Screening**:
   - Instantaneous (< 5 ms) incoming call metadata evaluation (contacts, blocklist, STIR/SHAKEN).
8. **Cryptographic Incident Persistence**:
   - Automatic creation of audit records with SHA-256 evidence integrity hashing.

---

## 3. What Dhwani AI CANNOT Claim (Scientific Integrity Boundaries)

1. **No 100% Detection Claims**: Dhwani AI does NOT claim 100% deepfake detection accuracy or zero false alarms. Scenario pass rate does not imply deepfake detection accuracy.
2. **No EER/AUC Claims from VoIP Robustness Benchmark**: As established in Phase 5.3, the controlled VoIP network benchmark validates real-time pipeline execution and latency robustness under network degradation, but does NOT establish class-discriminative EER/AUC.
3. **No Raw GSM/Cellular Audio Interception**: Android OS sandboxing strictly prohibits non-system applications from intercepting cellular audio streams. Dhwani AI never claims unrestricted cellular call recording.
4. **No Forced Block on Uncorroborated Spoof**: Under Dhwani AI's defense-in-depth policy, an uncorroborated synthetic voice detection produces a maximum risk score of 38, resulting in `ALLOW` unless accompanied by identity mismatch or social engineering context.

---

## 4. Hardware & Software Prerequisites

- **Host OS**: macOS (Apple Silicon / Intel) or Linux (Ubuntu 22.04+).
- **Docker**: Docker Engine 24+ running `voiceshield_asterisk` (andrius/asterisk:20).
- **Python**: Python 3.10 with virtual environment in `services/api/.venv`.
- **Node.js**: Node 18+ with npm.
- **Port Allocation**:
  - `5060`: Asterisk SIP Signaling (TCP/UDP)
  - `8088`: Asterisk ARI REST & WebSocket
  - `10000-10020`: Asterisk RTP Media (UDP)
  - `20000`: Dhwani AI Gateway ExternalMedia RTP Listener (UDP)
  - `8000`: Dhwani AI FastAPI Backend

---

## 5. Startup Sequence

### Step 1: Start Asterisk 20 (Docker)
```bash
docker start voiceshield_asterisk
```
Verify Asterisk health:
```bash
docker ps --filter "name=voiceshield_asterisk"
curl -s -u "${ARI_USER:-voiceshield}:${ARI_PASSWORD}" http://localhost:8088/ari/asterisk/info
# (Or: curl -s -u voiceshield:<ARI_PASSWORD> http://localhost:8088/ari/asterisk/info)
```

### Step 2: Start Backend with Real ML Pipeline
In a dedicated terminal:
```bash
cd services/api
PIPELINE_MODE=real_ml JWT_SECRET=local-dev-secret-not-for-production-1234567890abcdef .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```
Verify backend health:
```bash
curl -s http://localhost:8000/health
# Expected output: {"status":"ok","service":"dhwani-ai-api"}
```

### Step 3: Run Master Preflight Verification
```bash
PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario preflight
```

---

## 6. Demo Scenario Sequence

### Flow A: Normal Legitimate Call (Bona-Fide Speech)
1. **Action**: Caller establishes VoIP call with genuine human speech (`LJ007-0005.wav`).
2. **Terminal / UI Observation**:
   - RTP packets ingested at 20 ms intervals.
   - AASIST-L computes low spoof probability.
   - Risk score remains in `LOW` band (0–20).
   - Telephony policy maintains `ALLOW`. Call remains connected uninterrupted.
3. **Execution**:
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-01
   ```

### Flow B: Synthetic Voice Detection & Defense-in-Depth Corroboration
1. **Action**: Caller transmits neural-vocoded synthetic speech (`LJ016-0338.wav`).
2. **Terminal / UI Observation**:
   - Real-time AASIST-L inference flags acoustic and spectral anomalies.
   - Uncorroborated single-signal cap engages (Risk strictly capped at 38 points).
   - Demonstrates false-positive mitigation: Dhwani AI avoids premature call termination without multi-factor corroboration.
3. **Execution**:
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-02
   ```

### Flow C: Interactive Challenge-Response Authentication
1. **Action**: Risk elevation triggers active challenge.
2. **Terminal / UI Observation**:
   - Backend dynamically issues prompt (e.g. *"Please say: 'The security of this call matters.'"*).
   - Asterisk immediately mutes caller audio to prevent prompt injection.
   - Asterisk plays prompt WAV audio to caller.
   - Playback finishes -> caller unmuted -> listening window opens.
   - Caller speaks prompt -> Whisper transcribes -> Challenge passes -> Risk deflates.
3. **Execution**:
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-04
   ```

### Flow D: Real-Time Telephony Enforcement (HOLD & BLOCK)
1. **HOLD -> ALLOW**:
   - Asterisk isolates caller media into holding bridge.
   - Call remains active.
   - Unhold restores two-way audio.
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-06
   ```
2. **BLOCK**:
   - High-confidence fraud triggers BLOCK.
   - Gateway issued the configured ARI channel termination action, resulting in SIP BYE and channel destruction.
   - Asterisk transmits SIP BYE to caller; channel is terminated cleanly without leaks.
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-07
   ```

### Flow E: Network Watchdog & Fail-Safe Teardown
1. **Action**: RTP media stops transmitting (simulating network drop or attacker silence).
2. **Terminal / UI Observation**:
   - Watchdog tracks absence of RTP packets.
   - At configured timeout (5.0s default), caller channel is hung up with `normal` after measured elapsed silence.
   - No false fraud alert generated.
3. **Execution**:
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-08
   ```

### Flow F: Android Telecom Call Screening
1. **Action**: Incoming call receives instant metadata screening.
2. **Terminal / UI Observation**:
   - Evaluates caller against contact book and blocklist in < 4 ms via automated unit tests.
   - Grounded in previously established Phase 3.1 Realme 8 physical evidence.
   - Strictly respects Android OS sandbox: cellular audio is never tapped; screening is metadata-only.
   ```bash
   PYTHONPATH=. services/api/.venv/bin/python services/telephony/scripts/validate_phase54_e2e.py --scenario E2E-11
   ```

---

## 7. Demonstration Capabilities & Presentation Guide

1. **True Real-Time Processing**: Dhwani AI receives live 20ms RTP packets, converts/accumulates them into the configured PCM analysis windows, and performs ML inference on those analysis windows with inference under 300 ms on standard CPU.
2. **Multi-Factor Defense-in-Depth**: No single ML model has the authority to block a call. Blocking requires corroborated signals (Authenticity + Identity + Threat Intent).
3. **Interactive Active Defense**: When confidence is ambiguous, the system actively challenges the caller with unpredictable phrases rather than making passive guesses.
4. **Telephony Hardening**: Asterisk integration handles RTP jitter, media isolation, channel hold/unhold, watchdog timeouts, and selective resource reconciliation.
5. **Architectural Honesty**: Dhwani AI respects operating system security boundaries (Android Telecom metadata screening for cellular; Asterisk VoIP gateway for deep audio inspection).

---

## 8. Failure Recovery & Troubleshooting

### Scenario: Stale Asterisk Bridges or Channels
If a previous session crashed and left orphaned resources:
```bash
PYTHONPATH=. services/api/.venv/bin/python -c "
from services.telephony.scripts.validate_phase54_e2e import reconcile_owned_telephony_resources, get_live_bridges, get_live_channels
c, b = reconcile_owned_telephony_resources()
print(f'Reaped {c} channels, {b} bridges. Remaining: {len(get_live_channels())} channels, {len(get_live_bridges())} bridges.')
"
```

### Scenario: Backend WebSocket Returns 403 Forbidden
The backend requires `JWT_SECRET` to match `_make_service_token()`:
Ensure uvicorn is running with:
```bash
JWT_SECRET=local-dev-secret-not-for-production-1234567890abcdef
```

### Scenario: Asterisk Port 5060 Already Bound
Check for conflicting local SIP processes:
```bash
lsof -i :5060
```

---

## 9. Cleanup & Final Verification

To perform complete post-demo cleanup:
```bash
PYTHONPATH=. services/api/.venv/bin/python -c "
from services.telephony.scripts.validate_phase54_e2e import reconcile_owned_telephony_resources
reconcile_owned_telephony_resources()
print('Asterisk resources cleaned.')
"
```

Verify zero orphan channels and bridges:
```bash
curl -s -u "${ARI_USER:-voiceshield}:${ARI_PASSWORD}" http://localhost:8088/ari/channels
curl -s -u "${ARI_USER:-voiceshield}:${ARI_PASSWORD}" http://localhost:8088/ari/bridges
# (Or: curl -s -u voiceshield:<ARI_PASSWORD> http://localhost:8088/ari/channels)
# Both should return empty JSON lists: []
```

---

## 10. Emergency Fallback Demo Path (Mock Pipeline Mode)

If GPUs/CPUs are overloaded or external network conditions prevent real model execution, Dhwani AI provides an instant deterministic mock fallback mode:
```bash
cd services/api
PIPELINE_MODE=mock JWT_SECRET=local-dev-secret-not-for-production-1234567890abcdef .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```
This fallback mode uses deterministic heuristic DSP algorithms while keeping the exact same WebSocket framing, risk scoring mathematics, and Asterisk telephony mechanics intact.
