# Dhwani AI --- Project Context & Phase Status README

**Purpose:** This README is a handoff/context document for a new AI
agent, teammate, or developer joining the Dhwani AI project.\
**Project:** Smart India Hackathon 2026 --- Problem Statement
**SIH26104**\
**Product:** Dhwani AI --- AI-Powered Real-Time Detection and
Prevention of Voice Cloning Impersonation Attacks

> **Important:** This document describes the current engineering state
> and the intended roadmap. It distinguishes **implemented work**,
> **validated work**, **pending validation**, and **future roadmap
> work**. Do not assume a future/roadmap capability is already
> implemented.

------------------------------------------------------------------------

# 1. Project in One Paragraph

Dhwani AI is intended to be a real-time voice-security layer for
detecting AI-generated/manipulated speech during consequential
interactions and preventing fraud rather than merely flagging an audio
file after the fact.

The core security loop is:

**DETECT → SCORE → CHALLENGE → VERIFY → PROTECT**

The system deliberately separates three evidence streams:

1.  **Authenticity** --- Is the speech synthetic/manipulated?
2.  **Identity** --- Does the speaker match the expected/enrolled
    speaker?
3.  **Context** --- What is being said and how consequential is the
    request?

These streams are kept independent until the Risk Engine performs final
fusion. A genuine human asking for an OTP must not become "synthetic"
merely because the request is suspicious, and an unfamiliar speaker must
not automatically become "fake."

The official SIH problem statement asks for real-time synthetic-voice
detection, dynamic risk scoring, actionable alerts before sensitive
actions, privacy preservation, scalability, and support for multilingual
Indian accents/dialects. The Dhwani AI design extends this with active
challenge-response and an independent verification channel so that
high-risk decisions can actually be protected rather than merely
reported.

------------------------------------------------------------------------

# 2. Current High-Level Architecture

``` text
                    LIVE / TEST AUDIO
                           |
                           v
                  Audio Ingestion Layer
                           |
                           v
                    StreamWindower
                 4.038 s analysis window
                           |
             +-------------+-------------+
             |             |             |
             v             v             v
       AUTHENTICITY     IDENTITY       CONTEXT
          AASIST-L        ECAPA        Whisper
        / AASIST          TDNN           |
             |              |             v
             |              |       NLP / Context
             |              |             |
             +--------------+-------------+
                            |
                            v
                       Risk Engine
                            |
                            v
                     Security Policy
                            |
          +-----------------+-----------------+
          |                 |                 |
        ALLOW             VERIFY            HOLD/BLOCK
          |                 |                 |
          +-----------------+-----------------+
                            |
                            v
                    WebSocket Events
                            |
                            v
                    React Native App
```

The intended production/security architecture is not "one classifier
decides everything."

The architecture is:

``` text
Authenticity evidence
Identity evidence
Context/consequence evidence
        |
        v
   Risk Fusion
        |
        v
 Security Policy
        |
        v
Challenge / Independent Verification / Hold / Allow
```

------------------------------------------------------------------------

# 3. Critical Design Invariants

These must be preserved unless a future phase explicitly changes them
after evidence-based review.

## 3.1 Evidence independence

-   Authenticity, identity, and context are separate evidence streams.
-   Context must not directly contaminate the authenticity score.
-   Identity mismatch must not automatically mean the audio is
    synthetic.
-   A suspicious request must not be treated as proof of a cloned voice.

## 3.2 Backend authority

The backend is authoritative for:

-   risk score
-   risk state
-   security decision
-   challenge outcome
-   verification outcome
-   session state

The mobile application renders backend decisions. It must not calculate
the authoritative Security Risk Index.

## 3.3 AASIST model

Current production authenticity detector is based on the existing frozen
**AASIST-L** checkpoint, with the AASIST/AASIST-L implementation already
integrated.

Pinned AASIST-L checkpoint SHA-256:

`814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a`

Do not silently replace, retrain, fine-tune, or change this checkpoint
during performance/streaming phases.

## 3.4 AASIST windowing

The repository currently contains an acknowledged boundary discrepancy:

-   StreamWindower analysis window: **64,608 samples**
-   sample rate: **16 kHz**
-   hop: **16,000 samples**
-   maximum buffer: **80,608 samples**
-   AASIST `NB_SAMP`: **64,600 samples**
-   `_fit_length()` centre-crops the 64,608-sample window to 64,600
    before AASIST inference

This discrepancy existed before Phase 1.6 and was explicitly protected
from modification during Phase 1.6.

Do not silently reconcile these numbers.

## 3.5 Risk Engine

Current Risk Engine configuration must remain unchanged during
performance optimization:

-   authenticity weight: **0.50**
-   identity weight: **0.25**
-   context weight: **0.25**
-   thresholds: **20, 40, 65, 85**
-   minimum confidence for allow: **0.25**
-   `USE_CALIBRATED_SCORE_FOR_FUSION = False`

Challenge and Independent Verification outcomes are authoritative
backend state and can trigger risk recomputation even when no new audio
window arrives.

## 3.6 Privacy

Do not introduce permanent storage of:

-   raw audio
-   unnecessary voice embeddings
-   sensitive transcripts
-   unnecessary model outputs

Temporary benchmark artifacts must be clearly separated from production
persistence.

------------------------------------------------------------------------

# 4. Engineering Phase Status --- IMPORTANT

There are two roadmap layers in this project.

### Layer A --- Detailed engineering/build phases

These are phases such as:

-   Phase 0
-   Phase 1
-   Phase 2
-   Phase 3
-   Phase 1.5
-   Phase 1.6
-   later engineering phases

### Layer B --- Product/deployment roadmap

The master SIH document separately describes:

-   Product Phase 0 --- Hackathon
-   Product Phase 1 --- Pilot
-   Product Phase 2 --- Scale
-   Product Phase 3 --- Ecosystem

**Do not confuse these numbering systems.**

------------------------------------------------------------------------

# 5. Engineering Phase 0 --- Foundation

## Purpose

Build the basic Dhwani AI backend and application foundation.

## Main work

-   FastAPI backend
-   REST APIs
-   authentication
-   sessions
-   database
-   WebSocket gateway
-   Risk Engine
-   Security Policy
-   incident persistence
-   challenge flow
-   Independent Verification flow
-   device/session security

## Status

**COMPLETED**

This is the base layer used by all later phases.

------------------------------------------------------------------------

# 6. Engineering Phase 1 --- Mobile Application

## Purpose

Build the React Native mobile prototype and security dashboard.

## Main areas

-   authentication screens
-   home/dashboard
-   live monitoring
-   risk visualization
-   alerts
-   challenge UI
-   verification UI
-   incident history
-   device trust/settings
-   WebSocket event consumption
-   Zustand state management

## Status

**COMPLETED**

Current mobile application is React Native + TypeScript.

Important:

-   This is a **native mobile app architecture**, not a PWA.
-   The project is intended to support Android and iOS at the
    application level because React Native is being used.
-   Actual platform-specific audio capture/integration remains a
    separate problem and is not equivalent to having the UI ported.

------------------------------------------------------------------------

# 7. Engineering Phase 2 --- Real-Time Backend Pipeline

## Purpose

Connect incoming audio to the analysis and decision pipeline.

## Flow

``` text
Audio
  ↓
WebSocket
  ↓
decode / validation
  ↓
stream buffering
  ↓
analysis window
  ↓
ML evidence
  ↓
Risk Engine
  ↓
Security Policy
  ↓
WebSocket events
  ↓
Mobile dashboard
```

## Status

**CORE PIPELINE COMPLETED**

The backend WebSocket pipeline, event envelope, sequence handling,
persistence and decision flow exist.

Important limitation:

The project should not claim unrestricted interception of ordinary
cellular-call audio by a normal Android application.

The intended real-world production path is an authorized media source
such as VoIP/contact-center/enterprise integration, with mobile
screening treated as a supported/consented extension where technically
and legally possible.

------------------------------------------------------------------------

# 8. Engineering Phase 3 --- Real ML Integration

## Purpose

Replace placeholder/mock ML behavior with actual ML components.

## Authenticity

**AASIST / AASIST-L**

Used for synthetic/manipulated speech detection.

## Identity

**ECAPA-TDNN**

Current model identity:

`speechbrain/spkrec-ecapa-voxceleb`

Used for speaker embedding/similarity and expected-speaker verification.

## Speech-to-text

**faster-whisper / Whisper**

Used for asynchronous transcription and downstream context analysis.

## Context

Rule-based/NLP processing consumes transcript/context evidence.

## Status

**REAL ML FOUNDATION COMPLETED**

Important distinction:

> Real ML integration does NOT mean production-level accuracy has been
> proven.

The model is real and runs, but cross-dataset/generalization evaluation
exposed limitations. That is why model improvement is a later
evidence-driven phase.

------------------------------------------------------------------------

# 9. Challenge + Independent Verification

This is a major functional component and is already implemented.

## Challenge

When risk/consequence requires it, the system can issue an active
challenge.

The challenge result becomes authoritative backend state.

Example:

``` text
Caller fails challenge
       ↓
risk increases
       ↓
Security Policy may move toward HOLD
```

## Independent Verification

A verification result is also authoritative backend state.

Example:

``` text
High-risk call
       ↓
Independent verification approved
       ↓
risk is recomputed
       ↓
decision can move away from HOLD
```

## Important bug that was fixed

Originally, outcome fusion was lazy: if verification arrived after audio
had stopped, no new audio window existed to trigger risk recomputation.

The minimum fix added authoritative recomputation from the
challenge-result and verification-resolution paths.

This was empirically tested and regression-tested.

------------------------------------------------------------------------

# 10. Engineering Phase 1.5 --- Async Whisper / STT

## Problem

Whisper was blocking the critical real-time processing path.

## Solution

Whisper was moved to an asynchronous bounded queue/worker architecture.

Conceptually:

``` text
Audio window
    |
    +----> AASIST / ECAPA critical path
    |
    +----> STT Queue
              |
              v
        ThreadPoolExecutor
              |
              v
        Whisper result
              |
              v
        Context update
```

## Preserved protections

-   bounded queue
-   worker configuration
-   drop-oldest behavior
-   `window_seq`
-   `last_context_seq`
-   stale result protection
-   duplicate protection
-   session-aware result handling
-   teardown handling

## Validation

Phase 1.5 was validated with tests and latency measurements.

The reported critical-path result was within the intended sub-second
target for the measured benchmark.

## Status

**COMPLETED / PASS**

------------------------------------------------------------------------

# 11. ML Evaluation Phase

This phase answers:

> "How well does the existing AASIST-based detector actually
> generalize?"

It is separate from integration.

## Evaluated areas

The completed evaluation included protocols/conditions involving:

-   ASVspoof 2019 LA
-   ASVspoof speaker-disjoint evaluation
-   MLAAD-tiny subset
-   WaveFake/LJSpeech subset
-   robustness conditions
-   cross-generator/domain generalization
-   FAR / FRR
-   EER
-   ROC-AUC
-   operating-point analysis
-   latency
-   calibration-related measurements

## Important scope labels

The results must be described accurately:

-   **ASVspoof 2019 LA full evaluation** where applicable
-   **MLAAD-tiny subset**, not full MLAAD
-   **WaveFake/LJSpeech subset**, not general real-world telephony
    performance

## Important conclusion

The evaluation showed meaningful cross-domain/generalization
limitations.

The most important finding was:

> Threshold tuning alone cannot solve the detector's domain sensitivity.

Therefore, future model improvement should be based on better training
data, augmentation, generator diversity, and scientifically separated
validation/test sets rather than simply moving Risk Engine thresholds
until the numbers look better.

## Status

**COMPLETED**

------------------------------------------------------------------------

# 12. Phase 1.6 --- Async AASIST + ECAPA

## Purpose

Phase 1.5 removed Whisper from the blocking path.

The next bottleneck was:

-   AASIST inference
-   ECAPA inference

Both were originally synchronous CPU-heavy calls executed from the
asyncio/WebSocket path.

## Objective

Move heavy AASIST/ECAPA inference off the FastAPI asyncio event loop
using controlled asynchronous execution.

Target:

``` text
WebSocket event loop
       |
       +---- audio ingestion
       |
       +---- bounded ML execution
                  |
                  +---- AASIST
                  |
                  +---- ECAPA
```

## Implementation already performed

The Phase 1.6 implementation made four main changes:

1.  Added configurable ML pool worker count in `config.py`
2.  Added per-session `processing_lock` in `manager.py`
3.  Added ML executor lifecycle and `_process` integration in
    `gateway.py`
4.  Added executor shutdown to application lifespan in `main.py`

The existing:

-   `pipeline.py`
-   AASIST implementation
-   ECAPA implementation
-   STT queue
-   Risk Engine
-   Security Policy
-   windowing

were intended to remain unchanged.

## Current runtime idea

``` text
audio chunk
   ↓
asyncio task
   ↓
session processing lock
   ↓
real_ml
   ↓
run_in_executor(...)
   ↓
AASIST + ECAPA
   ↓
return to event loop
   ↓
publish / persist
```

## IMPORTANT CURRENT STATUS

**Implementation: COMPLETED**

**Validation/acceptance: PENDING**

The implementation passed targeted/core tests, but Phase 1.6 is not
considered fully accepted until the dedicated validation requirements
have been executed.

The required validation must prove:

-   actual event-loop responsiveness
-   worker-count performance
-   one-session cadence
-   two-session concurrency
-   three-session behavior if hardware permits
-   60-second stream
-   120-second soak
-   queue/backpressure behavior
-   stale/out-of-order protection
-   disconnect during inference
-   AASIST failure handling
-   ECAPA failure handling
-   model integrity
-   windowing integrity
-   Risk Engine integrity
-   Phase 1.5 STT regression
-   mock regression
-   full regression
-   real measured BEFORE/AFTER evidence

## Critical issue to investigate

The implementation uses:

``` python
asyncio.create_task(_process(...))
```

and:

``` python
async with state.processing_lock:
```

A lock serializes work for a session, but a lock by itself does **not
necessarily provide bounded backpressure**.

If audio arrives faster than the session can process it, `_process()`
tasks could potentially accumulate while waiting for the lock.

This must be measured before changing the architecture.

------------------------------------------------------------------------

# 13. Phase 1.6 Acceptance Rule

Do NOT mark Phase 1.6 PASS merely because unit tests pass.

A valid PASS requires performance evidence.

Minimum evidence includes:

### Architecture

-   AASIST no longer blocks the event loop
-   ECAPA no longer blocks the event loop
-   Whisper remains asynchronous
-   ML execution is controlled/bounded
-   session isolation remains intact
-   stale results cannot overwrite newer results
-   duplicate results cannot corrupt state

### Performance

-   one-session cadence measured
-   ≥95% cadence target evaluated honestly
-   two-session behavior measured
-   three-session behavior measured if possible
-   critical p50/p95 measured
-   heartbeat/event-loop responsiveness measured
-   120-second soak completed
-   RSS behavior measured

### Correctness

-   AASIST checkpoint unchanged
-   checkpoint SHA-256 verified
-   ECAPA identity unchanged
-   windowing unchanged
-   Risk Engine unchanged
-   Security Policy unchanged
-   STT unchanged
-   mock mode preserved

### Failure handling

-   AASIST failure
-   ECAPA failure
-   executor saturation
-   disconnect during inference
-   stale result
-   out-of-order result
-   duplicate result

If required measurements cannot be run:

**Overall Phase 1.6 status must be PARTIAL, not PASS.**

------------------------------------------------------------------------

# 14. Phase 1.7 --- Next Engineering Step

## Current status

**NOT STARTED / NOT YET LOCKED**

Do not assume an exact implementation scope for Phase 1.7 until Phase
1.6 validation is complete.

The likely purpose is to take the measured Phase 1.6 system and harden
the real-ML pipeline further, but the exact work should be selected from
actual benchmark findings rather than invented in advance.

Potential areas can include:

-   remaining real-time bottlenecks
-   bounded backpressure
-   reliability
-   real-audio ingestion
-   deterministic session behavior
-   observability
-   soak stability
-   pipeline hardening

The next phase must be defined from Phase 1.6 evidence.

------------------------------------------------------------------------

# 15. Real Audio Integration

## Current status

**NOT FULLY COMPLETED**

There is an important distinction:

### Already possible

The backend can work with:

-   PCM/WAV test audio
-   controlled streaming fixtures
-   mock/generated streams
-   real ML processing

### Not yet claimed

Unrestricted Android interception of ordinary cellular calls.

That is not a safe/accurate claim for the prototype.

## Intended real-world architecture

``` text
Authorized VoIP / Contact Center / Media API
                    |
                    v
                Dhwani AI
                    |
        +-----------+-----------+
        |           |           |
      AASIST      ECAPA      Whisper
        |           |           |
        +-----------+-----------+
                    |
                Risk Engine
                    |
              Security Policy
                    |
           Verify / Hold / Allow
```

A mobile application can be a consented screening extension where
supported, but actual audio-source access must be treated as a separate
platform/integration problem.

------------------------------------------------------------------------

# 16. AASIST Model Improvement / Fine-Tuning

## Current status

**NOT STARTED**

This is deliberately postponed.

The existing AASIST-L model is currently being used as the frozen
production/prototype detector.

## Why not retrain immediately?

Because the completed evaluation first established where the model
fails.

Training without a proper split and evaluation protocol risks producing
impressive in-domain numbers while worsening generalization.

## Planned scientific approach

A future training phase should:

1.  Identify training-eligible datasets.
2.  Establish licenses/provenance.
3.  Keep generator/speaker separation.
4.  Define train/validation/unseen-test splits.
5.  Add realistic augmentation.
6.  Include codec/channel/noise/replay conditions where appropriate.
7.  Include multilingual/Indian-English data where legally and
    technically available.
8.  Fine-tune AASIST carefully.
9.  Preserve an untouched unseen test set.
10. Compare the fine-tuned model against the frozen baseline.
11. Evaluate:

-   EER
-   ROC-AUC
-   FAR
-   FRR
-   TPR
-   TNR
-   calibration
-   unseen-generator degradation
-   robustness degradation
-   streaming latency

12. Only then decide whether the new checkpoint should replace the
    existing one.

## ASVspoof 5 / cloud data

The current project deliberately postpones acquisition/training work
that requires additional cloud/storage resources.

The project should continue using the existing AASIST-L model rather
than blocking engineering progress while waiting for storage/cloud
resources.

------------------------------------------------------------------------

# 17. Why Training Data Is Needed

AASIST learns patterns associated with genuine and spoofed speech.

If training data contains only a limited distribution of attacks, the
detector can learn:

``` text
known training generators
        ↓
good performance
```

but fail on:

``` text
unseen generator
new vocoder
new language
codec-transformed audio
noise/replay
new recording conditions
```

Therefore the goal is not:

> "Get the highest accuracy on the dataset."

The goal is:

> **Improve generalization to attacks and conditions that were not used
> to train the model.**

This is why unseen-generator evaluation is especially important.

------------------------------------------------------------------------

# 18. Data Strategy --- Future

Future training should ideally contain a mixture of:

### Bonafide

-   multiple speakers
-   multiple languages
-   Indian-English
-   different recording devices
-   different acoustic conditions

### Spoof

-   TTS
-   voice conversion
-   neural vocoders
-   multiple generators
-   multiple languages
-   multiple speaker identities

### Robustness transforms

-   telephone codecs
-   VoIP compression
-   noise
-   reverberation
-   replay-like transformations
-   packet-loss/channel artifacts

The exact dataset list must be decided after checking:

-   license
-   availability
-   storage requirements
-   train/test overlap
-   speaker overlap
-   generator overlap
-   language coverage

Do not claim full dataset coverage when only a subset was actually
obtained.

------------------------------------------------------------------------

# 19. ECAPA Future Work

ECAPA is already integrated.

Future work may include:

-   threshold calibration
-   speaker-disjoint evaluation
-   enrollment robustness
-   noisy-channel evaluation
-   multilingual evaluation
-   false-match / false-non-match analysis

But ECAPA must remain logically separate from authenticity.

------------------------------------------------------------------------

# 20. Whisper / Context Future Work

Whisper is already asynchronous.

Future work can improve:

-   transcript quality
-   context classification
-   multilingual recognition
-   Indian accents
-   transaction/consequence extraction
-   confidence handling
-   semantic latency

But context should remain a separate evidence stream.

Example:

``` text
"I need an OTP"
```

can be suspicious context.

It must not become:

``` text
voice = synthetic
```

automatically.

------------------------------------------------------------------------

# 21. Android and iOS Status

## Application framework

React Native allows the application layer to target:

-   Android
-   iOS

## Current reality

The existing project should be described as:

**cross-platform mobile application architecture with Android/iOS
potential**, not as a completed production-grade dual-platform call
interception product.

### Android

The UI/prototype exists.

Actual unrestricted cellular-call audio capture is not claimed.

### iOS

The React Native application architecture can support iOS, but
production-grade audio/call integration still requires platform-specific
implementation and supported media access.

## Therefore

Do not tell judges:

> "We can intercept every normal Android/iPhone call."

Instead say:

> "The prototype uses controlled/authorized audio streaming. Production
> deployment is designed around supported VoIP, contact-center, or
> enterprise media integrations, with mobile screening as a consented
> extension where platform capabilities permit."

------------------------------------------------------------------------

# 22. Privacy and Security Work

## Already implemented at architecture level

-   authentication
-   WebSocket authorization
-   session ownership
-   device trust
-   evidence separation
-   backend-authoritative decisions
-   incident persistence
-   tamper-evident integrity mechanisms
-   minimal-retention design principles

## Further work later

-   production compliance review
-   retention policy enforcement
-   enterprise consent flows
-   deployment-specific privacy controls
-   full security audit
-   production threat modeling
-   operational key management
-   production infrastructure security

------------------------------------------------------------------------

# 23. Blockchain / Evidence Integrity

Blockchain/evidence integrity is **not the core ML detector**.

The purpose is to provide tamper-evident evidence/integrity for records
where required.

Do not claim:

-   blockchain makes evidence automatically court-admissible
-   blockchain proves the voice is fake
-   blockchain improves AASIST accuracy

The ML and security decision layers remain the important parts of the
core prototype.

------------------------------------------------------------------------

# 24. Product Roadmap From the Master SIH Document

The master design separately defines the long-term product roadmap.

## Product Phase 0 --- Hackathon

Scope:

-   live-stream demo
-   three-stage detection
-   active challenge
-   protective workflow
-   explainability trail

### Status

The prototype is being built around this target.

------------------------------------------------------------------------

## Product Phase 1 --- Pilot

Scope:

-   one enterprise/contact-center integration
-   authorized VoIP media APIs
-   calibration against production traffic

### Status

**Future**

Not completed.

------------------------------------------------------------------------

## Product Phase 2 --- Scale

Scope:

-   telecom-grade integration
-   broader Indian-language/dialect coverage
-   optional CNAP contextual signal where available
-   C2PA provenance as supporting evidence

### Status

**Future**

------------------------------------------------------------------------

## Product Phase 3 --- Ecosystem

Scope:

Connect Dhwani AI with other security modalities so a voice-cloning
event can correlate with:

-   phishing messages
-   fake documents
-   spoofed accounts
-   other campaign signals

### Status

**Future**

------------------------------------------------------------------------

# 25. Current Repository/Technical Structure

The current project has the following broad structure:

``` text
voiceshield/
│
├── apps/
│   └── mobile/
│       └── VoiceShieldApp/
│
├── services/
│   └── api/
│       ├── app/
│       │   ├── api/
│       │   ├── core/
│       │   ├── ml/
│       │   │   ├── authenticity/
│       │   │   ├── identity/
│       │   │   ├── context/
│       │   │   └── preprocessing/
│       │   ├── risk/
│       │   ├── websocket/
│       │   ├── simulation/
│       │   └── models/
│       ├── tests/
│       ├── scripts/
│       ├── evaluation/
│       ├── training/
│       ├── models/
│       ├── vendor/
│       ├── requirements.txt
│       └── voiceshield.db
│
├── data/
├── docs/
├── evaluation/
├── experiments/
├── training/
├── README.md
└── implementation_plan.md
```

Important source areas:

  Component                      Main responsibility
  ------------------------------ -----------------------------------
  `app/ml/authenticity/`         AASIST/authenticity detection
  `app/ml/identity/`             ECAPA/speaker identity
  `app/ml/context/`              Whisper/transcript/context
  `app/ml/preprocessing/`        audio preprocessing
  `app/risk/engine.py`           risk fusion
  `app/risk/policy.py`           security decision
  `app/websocket/gateway.py`     WebSocket/session processing
  `app/websocket/pipeline.py`    analysis pipeline
  `app/websocket/manager.py`     session state
  `app/websocket/stt_queue.py`   async STT
  `app/websocket/events.py`      event schema/sequence
  `app/challenge.py`             challenge flow
  `app/verification.py`          independent verification
  `tests/`                       backend unit/integration tests
  `evaluation/`                  ML evaluation harness/results
  `training/`                    AASIST fine-tuning infrastructure

------------------------------------------------------------------------

# 26. What Is Definitely Completed

At the current project stage, the following are established:

-   [x] Core Dhwani AI architecture
-   [x] FastAPI backend foundation
-   [x] REST APIs
-   [x] Authentication/session infrastructure
-   [x] WebSocket streaming infrastructure
-   [x] Mobile React Native application
-   [x] Risk Engine
-   [x] Security Policy
-   [x] Challenge workflow
-   [x] Independent Verification workflow
-   [x] Authoritative backend recomputation after challenge/verification
    outcomes
-   [x] Incident persistence
-   [x] Real AASIST/AASIST-L integration
-   [x] Real ECAPA-TDNN integration
-   [x] Real Whisper/faster-whisper integration
-   [x] Async STT queue
-   [x] ML evaluation infrastructure
-   [x] ASVspoof/WaveFake/MLAAD evaluation work as disclosed
    subsets/protocols
-   [x] FAR/FRR/EER/ROC-AUC evaluation work
-   [x] Initial robustness/generalization evaluation
-   [x] Phase 1.5 async STT optimization
-   [x] Phase 1.6 AASIST/ECAPA executor implementation

------------------------------------------------------------------------

# 27. What Is Currently Pending

## Immediate

### Phase 1.6 validation

This is the immediate next task.

Pending evidence:

-   event-loop heartbeat
-   worker-count benchmark
-   single-session streaming
-   120-second soak
-   concurrent sessions
-   backpressure
-   out-of-order result
-   disconnect during inference
-   AASIST failure
-   ECAPA failure
-   model integrity
-   full regression

**Do not move to model retraining before this validation is finished.**

------------------------------------------------------------------------

# 28. What Remains After Phase 1.6

The exact order should be evidence-driven, but the broad remaining work
is:

### Engineering

1.  Phase 1.6 validation
2.  Phase 1.7 reliability/real-audio hardening
3.  controlled real-audio integration
4.  end-to-end demo hardening
5.  platform-specific mobile audio integration where supported

### ML

6.  dataset expansion
7.  scientifically correct train/validation/test design
8.  augmentation
9.  AASIST fine-tuning
10. cross-dataset evaluation
11. calibration
12. robustness testing
13. possible checkpoint replacement only after evidence

### Product/production

14. authorized VoIP/contact-center integration
15. enterprise pilot
16. security/privacy audit
17. monitoring/observability
18. deployment infrastructure
19. broader Indian-language/dialect support
20. ecosystem integration

------------------------------------------------------------------------

# 29. Things We Must NOT Do Prematurely

Until the relevant phase explicitly begins:

-   Do not claim 99% accuracy.
-   Do not claim nearly-perfect detection.
-   Do not claim production-ready AI detection.
-   Do not claim unrestricted Android cellular-call interception.
-   Do not claim full MLAAD if only MLAAD-tiny was evaluated.
-   Do not claim WaveFake subset results are general real-world
    performance.
-   Do not use threshold tuning to hide model weaknesses.
-   Do not retrain using the test set.
-   Do not allow speaker/generator leakage between train and test.
-   Do not silently alter AASIST windowing.
-   Do not replace AASIST-L during performance work.
-   Do not add another detector simply because the current detector has
    weaknesses.
-   Do not introduce commercial voice-deepfake APIs.
-   Do not use Resemble AI as a detection service.
-   Do not start ASVspoof-5/cloud training while the current engineering
    phase is unfinished.
-   Do not modify the Risk Engine just to improve benchmark numbers.
-   Do not change the dashboard merely to hide a backend limitation.

------------------------------------------------------------------------

# 30. Recommended Working Method for Any New AI Agent

A new AI agent must follow this sequence:

## Step 1 --- Read this README

Understand:

-   architecture
-   current state
-   invariants
-   completed phases
-   pending phases

## Step 2 --- Inspect the actual repository

Never assume this README is more authoritative than the code.

Verify:

-   current source
-   current configuration
-   current tests
-   current model files
-   current documentation
-   current benchmark results

## Step 3 --- Identify the active phase

At the time this README was created:

> **Phase 1.6 implementation is complete; Phase 1.6 validation is the
> active task.**

## Step 4 --- Do not jump phases

Do not begin retraining, cloud setup, Android call capture, or
production deployment while Phase 1.6 validation is incomplete unless
explicitly instructed.

## Step 5 --- Preserve invariants

Especially:

-   AASIST checkpoint
-   AASIST windowing
-   Risk Engine
-   Security Policy
-   evidence independence
-   Phase 1.5 STT behavior
-   session isolation
-   backend authority
-   privacy behavior

## Step 6 --- Measure before changing

If a problem is suspected:

1.  reproduce it
2.  measure it
3.  identify the bottleneck
4.  propose the smallest change
5.  implement only after approval/scope allows it
6.  rerun regression tests

------------------------------------------------------------------------

# 31. How to Explain the Project to a New Teammate

Use this short explanation:

> "Dhwani AI is a real-time voice-security system for SIH26104. We
> have already built the backend, mobile app, WebSocket pipeline, Risk
> Engine, challenge/verification workflow, and integrated real AASIST-L,
> ECAPA-TDNN and Whisper. We also evaluated the detector across
> ASVspoof, MLAAD-tiny and WaveFake subsets and found cross-dataset
> generalization limitations. Whisper was made asynchronous in Phase
> 1.5, and AASIST/ECAPA were moved off the FastAPI event loop in Phase
> 1.6. Right now Phase 1.6 implementation is done, but its full
> performance/concurrency validation is still pending. After that, we
> will harden the real-audio pipeline, and only then work on
> scientifically justified model improvement/fine-tuning and production
> integrations."

------------------------------------------------------------------------

# 32. Current Status at a Glance

``` text
FOUNDATION
████████████████████  DONE

MOBILE APP
████████████████████  DONE

REAL-TIME BACKEND
████████████████████  DONE

REAL AASIST / ECAPA / WHISPER
████████████████████  DONE

CHALLENGE + VERIFICATION
████████████████████  DONE

PHASE 1.5 ASYNC STT
████████████████████  PASS

ML EVALUATION
████████████████████  DONE

PHASE 1.6 IMPLEMENTATION
████████████████████  DONE

PHASE 1.6 VALIDATION
████████░░░░░░░░░░░░  CURRENT

PHASE 1.7
░░░░░░░░░░░░░░░░░░░░  NOT STARTED

REAL AUDIO SOURCE
░░░░░░░░░░░░░░░░░░░░  PENDING

AASIST FINE-TUNING
░░░░░░░░░░░░░░░░░░░░  LATER

ENTERPRISE / VOIP PILOT
░░░░░░░░░░░░░░░░░░░░  FUTURE

TELECOM SCALE
░░░░░░░░░░░░░░░░░░░░  FUTURE

ECOSYSTEM INTEGRATION
░░░░░░░░░░░░░░░░░░░░  FUTURE
```

------------------------------------------------------------------------

# 33. Final Current-State Statement

**Dhwani AI is no longer just a UI prototype or mock concept.**

The project has a functioning backend architecture, mobile application,
real-time WebSocket pipeline, real AASIST/ECAPA/Whisper ML components,
Risk Engine, Security Policy, challenge/verification workflow,
persistence, evaluation infrastructure, and asynchronous STT.

The current bottleneck is no longer "build the basic application."

The immediate engineering question is:

> **Can the existing real-ML pipeline sustain real-time/concurrent
> processing reliably after moving AASIST and ECAPA off the asyncio
> event loop?**

That is what **Phase 1.6 validation** must answer.

After that, the project should proceed from measured evidence toward:

**reliability → controlled real audio → model improvement → robustness →
authorized production integration.**

Do not skip directly from "the model runs" to "the model is production
accurate."

------------------------------------------------------------------------

# 34. Source / Reference Documents

The project context is grounded primarily in:

-   `SIH26104_VoiceShield_MASTER_v18_Final.md` --- master SIH
    architecture, roadmap, claim-safety, research and presentation
    reference.
-   `PS26104_VoiceShield_Explained.pdf` --- official problem statement
    and plain-language mapping.
-   `Final SIH Winning Strategy Guide.pdf` --- SIH strategy/presentation
    guidance.
-   `Conducting Internal Hackathon for Smart India Hackathon 2026.pdf`
    --- internal SIH/hackathon process context.
-   Current Dhwani AI repository source, tests, evaluation results and
    implementation plans.
-   Phase 1.5 and Phase 1.6 engineering validation reports.

The **actual repository remains the primary source of truth for
implementation details**. This README is a handoff/context layer, not a
substitute for inspecting code.

------------------------------------------------------------------------

# 35. Rule for Future AI Sessions

Before making any implementation change, the AI should state:

1.  Which phase the task belongs to.
2.  Which existing files/components it will touch.
3.  Which invariants it will preserve.
4.  What evidence/tests will prove the change works.
5.  Whether the change affects model behavior, Risk Engine behavior,
    security behavior, or only performance.

If the requested change belongs to a later phase, do not implement it
early without explicit instruction.
