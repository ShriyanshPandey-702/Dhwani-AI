# VoiceShield Mobile App — Product Requirements Document (PRD)

**Project:** VoiceShield
**SIH 2026:** Problem Statement 26104
**Platform:** Android-first mobile security application
**Status:** Product specification for prototype and phased implementation

## 1. Product Summary

VoiceShield is a real-time voice-security client designed to detect possible voice-cloning/AI-generated speech during an authorized live communication session, continuously assess impersonation risk, warn the user, trigger an active challenge when justified, and require independent verification before consequential actions proceed.

The product follows:

**DETECT → SCORE → CHALLENGE → VERIFY → PROTECT**

The mobile application is a **consented screening extension**, not an unrestricted raw cellular-call recorder. The primary production integration path is authorized VoIP/contact-center media APIs.

VoiceShield includes a **real-time in-app Security Dashboard** that visualizes
continuously changing authenticity, identity, context, risk, events and security
decisions during an active monitored call. This is a core product feature, not an
administrative or backend-only view: while a monitored call is active, the mobile
app becomes a live security analysis dashboard.

**Resemble AI is not used.**

## 2. Problem

AI-generated voices can convincingly impersonate trusted people. Caller ID, familiarity with a person's voice, and manual verification are insufficient by themselves in high-pressure situations. VoiceShield addresses the missing real-time security layer that evaluates voice authenticity, identity consistency, conversation context, and consequence before a sensitive action is allowed.

## 3. Product Goals

1. Provide continuous real-time security feedback during supported calls/sessions.
2. Detect acoustic evidence associated with synthetic or manipulated speech.
3. Keep voice authenticity separate from identity and contextual risk.
4. Produce a continuously updating Security Risk Index from 0–100.
5. Explain why risk changed.
6. Trigger adaptive challenge-response only when risk/consequence justify friction.
7. Use an Independent Trust Channel for high-risk/high-consequence verification.
8. Protect sensitive actions by hold/escalation rather than relying on a binary detector.
9. Minimize raw-audio retention and prefer edge/on-device processing where practical.
10. Support Indian languages, accents, noisy channels, compression and poor network conditions through the evaluation strategy.

## 4. Target Users

### 4.1 Individual user
A person receiving a suspicious call who wants immediate protection.

### 4.2 Enterprise user
Executives, finance teams and employees handling sensitive approvals.

### 4.3 Banking/contact-center deployment
A security layer for high-value voice interactions.

### 4.4 Government/organizational deployment
Protection for sensitive telephonic instructions and approvals.

## 5. Product Scope

### MVP
- Account onboarding/authentication
- Trusted-device registration
- Supported live-session connection
- Live call/security status screen
- Audio-analysis status
- Authenticity, identity and context evidence
- Live Security Risk Index
- Five risk states
- Explainable alerts
- Active challenge
- Mock/controlled Independent Trust Channel
- Hold/allow/block decision workflow
- Incident history
- Tamper-evident evidence hash
- Settings/privacy controls
- Offline/network-failure handling

### Roadmap
- Production enterprise/VoIP adapters
- Broader Indian-language coverage
- More on-device models
- Production OOB integrations
- Permissioned multi-party ledger
- CIVIXSHIELD correlation
- Additional provenance/context signals

## 6. Core User Journey

1. User installs VoiceShield.
2. User signs in.
3. User registers the device as trusted.
4. User grants only required permissions.
5. User starts/receives a supported monitored session.
6. VoiceShield shows monitoring status.
7. Audio is processed continuously.
8. Authenticity, identity and context signals are calculated separately.
9. Risk Engine updates the Security Risk Index.
10. Low risk → continue.
11. Suspicious risk → warning and optional challenge.
12. High risk → mandatory challenge and independent verification.
13. Critical + consequential action → hold until verified.
14. Verified safe → allow.
15. Unverified/high-risk → block or escalate.
16. Incident summary is stored with minimal necessary data.

## 7. Functional Requirements

### FR-01 Authentication
- User can sign in/sign out.
- Session tokens are securely stored.
- Expired/invalid tokens force re-authentication.
- Account roles can be represented for future enterprise use.

### FR-02 Trusted Device
- User can register the current device.
- Device identity is stored securely.
- User can revoke a trusted device.
- Sensitive verification must not rely solely on the same suspected call channel.

### FR-03 Permission Management
- Explain why microphone/call-screening/notification permissions are requested.
- Never request unrelated permissions.
- App remains usable in non-monitored mode when optional permissions are denied.

### FR-04 Supported Call/Session Monitoring
- Show whether monitoring is available.
- Show connection state.
- Start/stop monitoring only through an authorized supported path.
- Never claim unrestricted access to cellular call audio.

### FR-05 Real-Time Audio Pipeline
- Receive supported audio stream.
- Convert/normalize audio where required.
- Process rolling windows.
- Maintain timestamps.
- Handle silence and speech-active periods.
- Detect stream interruption.

### FR-06 Authenticity Analysis
The authenticity stage may combine:
- AASIST/RawNet2-family detection
- WavLM/Wav2Vec2-XLSR features
- spectral/DSP analysis
- prosody/pitch/rhythm/pause analysis
- channel/noise robustness features

The app must not present any single detector as infallible.

### FR-07 Identity Analysis
- Generate/receive speaker embedding.
- Compare against an enrolled reference where available.
- Display identity confidence separately from authenticity.
- Never automatically enroll a voice from an ongoing call.

### FR-08 Context Intelligence
Detect contextual risk such as:
- OTP requests
- fund-transfer requests
- confidential-information requests
- urgency
- authority claims
- suspicious transaction context

Context evidence must not directly alter the authenticity score.

### FR-09 Risk Engine
Produce a Security Risk Index from 0–100 and one state:
- Insufficient Evidence
- Low / Watch
- Suspicious
- High
- Critical

Risk updates continuously as new evidence arrives.

### FR-10 Alerting
- In-app warning
- Risk-state change
- Plain-language explanation
- Recommended action
- Optional push notification
- Alert severity must correspond to policy.

### FR-11 Active Challenge
When policy requires:
- Generate randomized challenge.
- Display/play challenge instruction.
- Analyze response timing/continuity/prosodic behavior where supported.
- Treat challenge as additional evidence, not absolute proof.
- Accessibility safeguards must prevent atypical speech or noise from being treated as evidence of synthetic speech.

### FR-12 Independent Trust Channel
Support prototype workflows for:
- trusted-device approval
- push approval
- known-number callback
- supervisor/dual authorization
- MFA

The independent channel must be separate from the suspected voice channel.

### FR-13 Protection Decision
Possible outcomes:
- Allow
- Verify
- Hold
- Block
- Escalate

A consequential action must not be silently allowed when evidence is insufficient.

### FR-14 Incident Management
Store:
- incident ID
- timestamps
- risk states
- model versions
- policy version
- evidence summary
- action taken
- verification outcome
- integrity hash

Raw audio should not be stored by default.

### FR-14A Live Security Dashboard (Active Call)

While a monitored call is active, the app must present a live dashboard that
updates from backend events without any manual refresh. It must show:

- Security Risk Index (0-100), risk state, risk trend and evidence sufficiency
- A live risk time-series graph fed by backend observations, with bounded
  history (approximately the last 60-120 observations). No hardcoded values.
- Voice authenticity: score, spoof probability, acoustic / spectral / prosody
  anomaly bands, and detection confidence
- Speaker identity: match score, identity confidence, consistency, enrollment
  status
- Conversation context: urgency, financial request, OTP request, credential
  request, sensitive-information request, social-engineering risk, transaction
  consequence, and context confidence
- A real-time detected-events timeline
- Active alerts
- The current security decision and the reasons behind it
- Access to Challenge Caller and Independent Verification

The three evidence streams must be presented as separate panels. The UI must not
imply that a contextual signal is evidence of synthesis, or that a speaker
mismatch proves a cloned voice.

The dashboard must reset between calls, and must survive duplicate, malformed,
out-of-order and late events without failing.

### FR-14B Home Security Overview Dashboard

The Home screen must be a security overview, not a generic landing page. It must
show today's activity (calls, alerts, high/critical calls, safe calls), the
average risk, and recent monitored calls with their timestamp, final risk, risk
state and final action. Selecting a recent call must open its Incident Detail.

Figures must come from backend data. Where no backend data exists, the screen
must show an explicit empty state rather than placeholder numbers.

### FR-15 Explainability
For every meaningful intervention, show:
- authenticity evidence
- identity evidence
- context evidence
- consequence level
- challenge result
- verification result
- final reason/action

### FR-16 Privacy
- Data minimization
- Minimal audio retention
- Feature-only logging where possible
- Explicit consent for required processing
- Secure transport
- Secure local storage
- User controls for data/history where applicable

### FR-17 Network Handling
- Detect loss/poor quality.
- Mark stale evidence.
- Never turn missing evidence into a fake/real verdict.
- Fall back to Insufficient Evidence and/or independent verification for consequential actions.

### FR-18 Notifications
- Security alerts
- Verification requests
- Incident status
- Safe completion/hold/block status

### FR-19 Settings
- Monitoring preferences
- Notification preferences
- Trusted devices
- Privacy controls
- Language preference
- Security policy visibility where user role permits

### FR-20 Accessibility
- Large readable risk status
- Screen-reader labels
- Clear text alternatives
- Do not penalize speech disabilities
- Route ambiguous speech to safer verification rather than treating it as synthetic

## 8. Non-Functional Requirements

### Performance
- Continuous processing without freezing UI.
- UI risk updates should feel immediate relative to incoming analysis results.
- Detection latency is measured using p50/p95.
- Call conversational audio must not be placed behind the analysis pipeline.

### Reliability
- App must recover from WebSocket disconnects.
- ML-service failure must degrade safely.
- A failure in any single evidence stream must not stop the security system;
  the remaining streams continue and evidence confidence drops accordingly.
- Local-loopback/demo mode must exist for SIH demonstration reliability.

### Security
- TLS for network communication.
- JWT/session security.
- Android Keystore for sensitive local secrets.
- Backend-only external API keys.
- No API keys in APK/client code.

### Privacy
- No raw audio retention by default.
- Feature-only telemetry where possible.
- Third-party processing must be explicit and controlled.

## 9. Risk Policy

| State | Typical behavior |
|---|---|
| Insufficient Evidence | No forced verdict; independent verification for consequential actions |
| Low / Watch | Continue and monitor |
| Suspicious | Warning; optional challenge |
| High | Mandatory challenge + independent verification |
| Critical | Hold/escalate until independent verification |

Risk and consequence are both considered. A low-risk routine call should not receive the same friction as a high-value transaction.

## 10. Success Criteria

The MVP is successful when:
- A supported live session can be monitored.
- Risk updates continuously.
- Synthetic-voice test audio produces an appropriate elevated signal.
- Genuine test audio does not systematically trigger high-risk decisions.
- Context such as an OTP or large transfer request is detected separately.
- Challenge workflow works.
- Independent verification works.
- Critical action is held until verification.
- All major failures degrade safely.
- Test suite passes with no release-blocking failures.

## 11. Explicit Product Limitations

- VoiceShield does not guarantee perfect detection.
- No challenge can be guaranteed to defeat every future real-time voice converter.
- Mobile cellular-call audio access is platform/permission dependent.
- No third-party detection API is used. Authenticity detection is VoiceShield's
  own pipeline, and no single detector within it is treated as the sole source
  of truth.
- Blockchain is evidence integrity, not AI detection.
- Any production claim requires measured evaluation.

## 12. Out of Scope for MVP

- Unrestricted cellular call recording.
- Guaranteed carrier-level integration.
- Court-admissibility claims.
- Automatic financial transactions controlled directly by VoiceShield.
- Production multi-bank consortium blockchain.
- Fully autonomous blocking without configured policy/authorization.

## 13. Demo Scenario

**Caller:** “Transfer ₹5 lakh immediately. I am the CEO.”

Expected:
1. Audio begins streaming.
2. Authenticity analysis runs.
3. Identity/context analysis runs independently.
4. Context detects high-consequence transfer + urgency.
5. Risk rises.
6. VoiceShield issues a challenge.
7. Risk remains high.
8. Independent Trust Channel requests trusted-device approval.
9. Transaction is held.
10. If approval fails/timeout occurs → Block/Escalate.
11. Incident evidence is recorded with integrity hash.

## 14. Product Principle

VoiceShield is not merely a fake-voice detector. It is a real-time security decision layer that detects, scores, verifies and protects the final consequential action.

---

## 15. Implementation Status

This section is normative for what may be claimed about the product.

**REAL** — FastAPI backend, JWT authentication, sessions and incidents;
WebSocket gateway and event contract; Risk Engine; Policy Engine; challenge and
independent-verification flows; the Live Security Dashboard; the Home Security
Overview dashboard; audio preprocessing and channel-quality measurement;
conversation-context signal rules; SHA-256 evidence integrity.

**MOCK / STUB** — Voice authenticity detection is a heuristic DSP stand-in, not
a trained model. Speaker identity uses a spectral fingerprint, not ECAPA-TDNN.
Speech-to-text is a scripted transcript, not Whisper. Audio originates from a
development mock generator, not from Android capture.

Stubbed results are labelled as such on the wire (`pipeline_mode`, `is_mock`)
and in the UI. They must never be presented as AI detection results.

**PLANNED** — AASIST / RawNet2 authenticity models; ECAPA-TDNN speaker
verification; faster-whisper transcription; a transformer context classifier;
real consented Android audio capture; blockchain evidence anchoring.
