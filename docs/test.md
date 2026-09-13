# VoiceShield Mobile App — Test Plan

## 1. Objective

Verify that the VoiceShield Android application is functional, secure, real-time, privacy-conscious, accessible, and safe under normal and failure conditions.

**Release rule:** all Critical and High severity tests must pass before an SIH demo/release build.

## 2. Test Environment

### Devices
Test at minimum:
- Android emulator
- One mid-range Android phone
- One lower-end Android phone
- Multiple Android versions supported by the implementation

### Network
- Good Wi-Fi
- Slow network
- High latency
- Packet loss
- Temporary disconnect
- Reconnect

### Audio
- Clean genuine speech
- Synthetic/deepfake test speech
- Background noise
- Music
- Reverberation
- Low volume
- Compression
- Short speech
- Silence
- Hindi/Hinglish
- Other supported Indian languages/accent samples

## 3. Severity

- **P0 Critical:** security/safety failure or app unusable
- **P1 High:** core functionality failure
- **P2 Medium:** important but recoverable
- **P3 Low:** cosmetic/minor

## 4. Functional Test Cases

| ID | Test | Expected Result | Sev |
|---|---|---|---|
| AUTH-001 | Valid login | User enters app | P1 |
| AUTH-002 | Invalid password/token | Login rejected | P1 |
| AUTH-003 | Expired token | Re-authentication requested | P1 |
| AUTH-004 | Logout | Session invalidated | P1 |
| AUTH-005 | Device registration | Device becomes trusted | P1 |
| AUTH-006 | Device revocation | Device can no longer approve | P1 |
| PERM-001 | Grant required permission | Feature becomes available | P1 |
| PERM-002 | Deny optional permission | App remains stable | P1 |
| PERM-003 | Deny required monitoring permission | Clear explanation/fallback | P1 |
| CALL-001 | Start supported session | Monitoring starts | P0 |
| CALL-002 | End session | Monitoring stops cleanly | P1 |
| CALL-003 | Reconnect session | State recovers | P1 |
| CALL-004 | Unsupported call path | App clearly reports limitation | P1 |
| AUDIO-001 | Receive audio stream | Audio status becomes active | P0 |
| AUDIO-002 | Silence | No false high-risk event from silence alone | P1 |
| AUDIO-003 | Audio interruption | Stream status reports failure | P1 |
| AUDIO-004 | Poor-quality audio | Evidence confidence decreases safely | P0 |
| RISK-001 | Low-risk genuine audio | Low/Watch state | P0 |
| RISK-002 | Synthetic test audio | Authenticity signal increases appropriately | P0 |
| RISK-003 | Borderline audio | Does not force an overconfident verdict | P0 |
| RISK-004 | Risk update arrives | UI updates continuously | P1 |
| RISK-005 | Risk falls | UI reflects lower risk | P1 |
| RISK-006 | Context high-risk request | Context risk increases separately | P0 |
| RISK-007 | OTP request | Does not directly change authenticity score | P0 |
| ID-001 | Matching enrolled voice | Identity confidence increases | P1 |
| ID-002 | Mismatching speaker | Identity mismatch shown separately | P1 |
| ID-003 | No enrollment | System continues without false identity certainty | P1 |
| ID-004 | Attempt enrollment during call | Blocked/not permitted | P0 |
| CTX-001 | Detect OTP request | Context event generated | P1 |
| CTX-002 | Detect transfer request | Context event generated | P1 |
| CTX-003 | Detect urgency | Context risk increases | P1 |
| CTX-004 | Normal conversation | No unjustified high consequence risk | P1 |
| ALERT-001 | Suspicious threshold crossed | Warning shown | P1 |
| ALERT-002 | High threshold crossed | Mandatory verification path | P0 |
| ALERT-003 | Critical threshold crossed | Action held | P0 |
| ALERT-004 | Alert explanation | Plain-language reason visible | P1 |
| CHAL-001 | Challenge triggered | Challenge displayed/played | P0 |
| CHAL-002 | Valid response | Challenge evidence recorded | P1 |
| CHAL-003 | Failed response | Risk/policy updates correctly | P1 |
| CHAL-004 | Random challenge | Challenge is not always identical | P2 |
| CHAL-005 | Speech disability/atypical speech | Not automatically labeled fake | P0 |
| OOB-001 | Verification request | Trusted-device approval appears | P0 |
| OOB-002 | Approve verification | Action may proceed if policy allows | P0 |
| OOB-003 | Reject verification | Action blocked/held | P0 |
| OOB-004 | Verification timeout | Action remains protected | P0 |
| OOB-005 | Same-channel verification attempt | Not treated as independent trust | P0 |
| ACT-001 | Low-risk action | Allow | P1 |
| ACT-002 | Suspicious action | Verify/challenge | P1 |
| ACT-003 | High-consequence high-risk action | Hold | P0 |
| ACT-004 | Verified critical action | Allow according to policy | P0 |
| ACT-005 | Failed critical verification | Block/escalate | P0 |
| INC-001 | Incident created | Incident appears in history | P1 |
| INC-002 | Incident detail | Evidence and reasons visible | P1 |
| INC-003 | Evidence hash | Hash generated consistently | P1 |
| INC-004 | Attempt to alter stored evidence | Integrity check detects mismatch | P0 |
| SET-001 | Notification setting | Preference saved | P2 |
| SET-002 | Language setting | Supported UI language changes | P2 |
| SET-003 | Privacy setting | Preference applied | P1 |

## 5. Real-Time Tests

| ID | Test | Expected Result |
|---|---|---|
| RT-001 | Continuous audio stream | No long UI freeze |
| RT-002 | Risk updates every incoming result | UI remains responsive |
| RT-003 | WebSocket disconnect | Reconnect/fallback occurs |
| RT-004 | Backend unavailable | App shows degraded state |
| RT-005 | ML service unavailable | Safe fallback; no fake verdict |
| RT-006 | One evidence stream unavailable | Remaining streams continue; evidence confidence drops |
| RT-007 | High latency | Stale evidence excluded/handled safely |
| RT-008 | Burst of risk events | UI does not crash |
| RT-009 | Long monitored session | Memory remains bounded |
| RT-010 | App background/foreground | Session state recovers according to platform constraints |

## 6. ML/Detection Tests

### Authenticity
- Genuine speech → should not systematically become high-risk.
- Known synthetic speech → detector should produce elevated evidence where expected.
- Multiple generators → test generalization.
- Unseen generator → measure degradation rather than assume success.
- Noise → test robustness.
- Codec compression → test robustness.
- Replay → test separately.
- Silence → no synthetic verdict solely from silence.
- Very short audio → Insufficient Evidence.
- Conflicting detector outputs → fusion remains calibrated/conservative.

### Identity
- Same enrolled speaker → high similarity under supported conditions.
- Different speaker → lower similarity.
- No reference → identity remains unknown.
- Channel distortion → confidence reflects uncertainty.

### Context
- “Send the OTP” → OTP event.
- “Transfer ₹5 lakh immediately” → financial + urgency + consequence signals.
- Ordinary conversation → no artificial high consequence.
- Context events never alter the raw authenticity score directly.

## 7. Risk Engine Tests

Verify boundaries:
- 0–low threshold
- suspicious threshold
- high threshold
- critical threshold
- exact boundary values
- missing signal
- stale signal
- contradictory signals
- consequence escalation

Test:
```text
Low authenticity risk + low consequence → Allow/Watch
Moderate evidence + suspicious context → Challenge
High combined risk + high consequence → Verify
Critical + no independent approval → Hold/Block
Insufficient evidence + high consequence → Verify/Hold
```

## 8. Challenge Tests

- Challenge generated successfully.
- Challenge is randomized.
- Challenge response timeout handled.
- No response handled.
- Natural response handled.
- Noisy response does not automatically become “fake”.
- Repeated challenge cannot become a static credential.
- Challenge result is logged.
- Challenge cannot bypass OOB when policy requires OOB.

## 9. Security Tests

| ID | Test | Expected Result |
|---|---|---|
| SEC-001 | Inspect APK for backend secrets | No secrets/API keys |
| SEC-002 | Inspect logs | No sensitive tokens/audio |
| SEC-003 | Invalid API token | Request rejected |
| SEC-004 | Tampered JWT | Rejected |
| SEC-005 | TLS/network interception test | Secure transport enforced |
| SEC-006 | Local secret storage | Android Keystore/secure storage used |
| SEC-007 | Unauthorized incident access | Access denied |
| SEC-008 | Unauthorized device approval | Rejected |
| SEC-009 | Secret exposure in the mobile bundle | No API key or secret present in the APK |
| SEC-010 | SQL injection payload | Safely rejected/parameterized |
| SEC-011 | Malformed WebSocket message | Connection remains safe |
| SEC-012 | Replay old approval | Rejected/expired |
| SEC-013 | Duplicate approval | Idempotent |
| SEC-014 | Evidence tampering | Integrity failure detected |

## 10. Privacy Tests

- Raw audio is not persisted by default.
- Only required telemetry is stored.
- Sensitive data is not displayed in notifications unnecessarily.
- Logout removes/invalidates local session data.
- Third-party processing is controlled and disclosed.
- User cannot accidentally enable hidden monitoring.
- Permission explanations are clear.
- Incident data follows retention policy.
- Feature-only logging works.

## 11. Network/Fault Tests

- Wi-Fi off.
- Mobile data off.
- Backend unavailable.
- Redis unavailable.
- PostgreSQL unavailable.
- ML service unavailable.
- WebSocket timeout.
- Audio stream interruption.
- App process restart.
- Phone restart.

**Expected principle:** failure must never silently convert to “safe/real” for a consequential action.

## 12. Accessibility Tests

- TalkBack navigation.
- Screen-reader labels.
- Risk state understandable without color.
- Large text.
- High-risk warning readable.
- Challenge instructions understandable.
- Buttons have accessible names.
- No reliance on color alone.
- Atypical speech does not automatically cause a fake classification.

## 13. Performance Tests

Measure:
- App startup time
- memory usage
- CPU usage
- battery impact
- WebSocket latency
- risk-update latency
- ML inference p50/p95
- reconnect time
- long-session stability

Run tests on:
- mid-range device
- lower-end device
- emulator

Do not publish a performance number until measured on the actual implementation.

## 14. Compatibility Tests

Test:
- supported Android versions
- different screen sizes
- portrait/landscape if supported
- different audio hardware
- Wi-Fi/mobile network transitions
- background/foreground lifecycle

## 15. UI Tests

Screens:
1. Splash
2. Login
3. Home
4. Device trust
5. Permission onboarding
6. Monitoring/call
7. Risk alert
8. Challenge
9. OOB verification
10. Action decision
11. Incident history
12. Incident details
13. Settings

Every screen:
- loads
- has no crash
- handles loading state
- handles empty state
- handles error state
- supports back navigation
- preserves required state

## 16. End-to-End Scenarios

### E2E-001 Genuine call
```text
Start session
→ genuine speech
→ low risk
→ no unnecessary challenge
→ continue
→ end session
→ optional low-severity log
```

### E2E-002 Suspicious call
```text
Start
→ suspicious voice evidence
→ context risk
→ Suspicious
→ warning
→ challenge
→ risk recalculated
```

### E2E-003 High-risk transfer
```text
Caller asks for ₹5 lakh transfer
→ authenticity + identity + context
→ risk High/Critical
→ challenge
→ OOB request
→ transaction held
→ approval/rejection
→ final action
→ incident logged
```

### E2E-004 Poor network
```text
Start
→ packet loss/noise
→ insufficient evidence
→ no forced fake verdict
→ independent verification for consequential action
```

### E2E-005 Partial evidence failure
```text
Start
→ one evidence stream stops producing (e.g. no enrolled speaker, STT gap)
→ remaining streams continue
→ risk engine lowers evidence confidence
→ a high-consequence request escalates to VERIFY rather than ALLOW
→ system remains functional
```

### E2E-006 Backend failure
```text
Start
→ backend unavailable
→ app shows degraded state
→ no unsafe approval
→ reconnect
→ session recovers if possible
```

## 17. Regression Checklist

Before every demo/release:
- [ ] Login
- [ ] Device registration
- [ ] Permissions
- [ ] Supported session
- [ ] Live audio
- [ ] Risk update
- [ ] Alert
- [ ] Challenge
- [ ] OOB verification
- [ ] Hold
- [ ] Allow
- [ ] Block
- [ ] Incident log
- [ ] Evidence hash
- [ ] WebSocket reconnect
- [ ] Backend failure
- [ ] ML failure
- [ ] No secret in APK/logs
- [ ] No raw audio retained by default
- [ ] Accessibility smoke test
- [ ] Demo fallback works

## 18. Acceptance Criteria

The mobile MVP can be considered demo-ready only when:
1. Core happy path works end-to-end.
2. Critical security tests pass.
3. High-risk action cannot bypass required verification.
4. Real-time risk state is visible and updates correctly.
5. ML/external-detector failures degrade safely.
6. The app does not claim unsupported cellular-call capabilities.
7. No API secret is embedded in the mobile client.
8. Test audio covers genuine, synthetic, noisy and compressed cases.
9. Incident evidence is tamper-evident.
10. The complete SIH demo can run using a local/controlled fallback if venue network fails.

---

## 19. Automated Test Suite (implemented)

Run with:

```bash
cd services/api && .venv/bin/python -m pytest              # 125 tests
cd apps/mobile/VoiceShieldApp && npm test                  # 58 tests
cd apps/mobile/VoiceShieldApp && npx tsc --noEmit           # 0 type errors
```

### Backend — `services/api/tests/`

| File | Tests | Covers |
|---|---|---|
| `test_risk_engine.py` | 27 | Fusion; the LOW → SUSPICIOUS → HIGH → CRITICAL ladder; threshold boundaries; stale and missing evidence; stream independence; consequence multiplier; challenge and verification deltas; score bounds; configurable weights; trend |
| `test_policy.py` | 11 | LOW→ALLOW, SUSPICIOUS→CHALLENGE, HIGH→VERIFY, CRITICAL→HOLD; insufficient evidence with a high-consequence request; the low-confidence guard; configurability; unknown states |
| `test_events.py` | 21 | Envelope on every event; monotonic per-session sequencing; sequence isolation across sessions; unique event ids; evidence-stream separation; every builder; the required event-type registry |
| `test_ml.py` | 30 | PCM decode and odd-byte tolerance; silence gating; quality metrics; authenticity bands, bounds and monotonic response; identity enrolment, matching and clearing; every context signal; signal stickiness; social-engineering logic; consequence escalation; STT stub behaviour |
| `test_pipeline.py` | 14 | The full mock scenario escalating to CRITICAL; ALLOW→VERIFY→HOLD; all three streams populated and separate; timeline de-duplication; alerts once per severity; policy events on change only; silence and malformed audio; bounded history; peak tracking; clean state for a new session |
| `test_websocket_integration.py` | 8 | A real WebSocket connection end to end: authorised connect and `session_started`; ping/pong; unknown message types and malformed JSON returning errors without dropping the socket; invalid base64 audio; the full demo scenario (score escalation, moving series, trend, all three streams separate, ALLOW→VERIFY→HOLD, alerts, timeline without repeats, mock labelling); envelope on every event with strictly increasing `seq` and unique `event_id`; a client audio chunk running the same pipeline labelled `live` |
| `test_security.py` | 14 | Valid/tampered/forged/expired JWTs; `alg: none` confusion; access vs refresh tokens; password hashing and salting; WebSocket rejection of missing, invalid, forged and refresh tokens; no secrets in the mobile bundle; no third-party detection API; evidence-hash tamper detection and key-order stability |

### Mobile — `apps/mobile/VoiceShieldApp/__tests__/`

| File | Tests | Covers |
|---|---|---|
| `riskStore.test.ts` | 33 | Gauge/state/trend updates; one graph observation per update; bounded history; independent evidence streams and non-destructive partial updates; audio quality; timeline ordering; alerts and dismissal; decision updates including ALLOW→VERIFY→HOLD; challenge and verification lifecycles; session lifecycle and incident id; **duplicate events, out-of-order events, reconnect sequence restart, malformed events, missing fields, unknown event types, pong frames, backend errors, bounded de-duplication**; reset between calls |
| `dashboard.test.tsx` | 24 | Risk gauge renders score/state/trend; sparkline empty state, per-observation bars and windowing; every required field in the authenticity, identity and context panels; stub labelling; stream-separation in the UI; event timeline; decision panel with human-readable reasons; mock/live banner; stat cards |
| `App.test.tsx` | 1 | Root mounts and shows the splash |

### Not yet automated

Stated plainly rather than implied: integration tests against a live PostgreSQL
instance (the WebSocket suite fakes the database layer); on-device testing on
physical Android hardware; performance, latency and accessibility measurement. Sections 1–18 above remain the manual test plan for
those areas.

---

## 20. On-Device Verification (Android emulator)

Performed on a Pixel 7 AVD, Android 16 (API 36), arm64, 1080x2400, against the
FastAPI backend running locally on SQLite.

| Area | Result |
|---|---|
| Splash, Login, Home, Active Call, Challenge, Verification, Incident History, Incident Detail, Device Trust, Settings | All 10 screens render and navigate |
| Live dashboard updates with no manual refresh | Risk 6 to 93; LOW to SUSPICIOUS to HIGH to CRITICAL; ALLOW to VERIFY to HOLD |
| Live risk graph | Grows 1 to 12 observations, bars coloured by risk state |
| Authenticity / Identity / Context panels | All required fields populate and change |
| Detected events timeline | 12 entries, newest first, per-stream tags |
| Alerts | Fire at HIGH and CRITICAL |
| Challenge flow | Real challenge issued; failed outcome reflected on the dashboard |
| Verification flow | Live countdown, real nonce, approval reflected on the dashboard |
| Outcomes drive the authoritative decision | Approval: 93/CRITICAL/HOLD -> 73/HIGH/VERIFY. Failed challenge: 73 -> 93, VERIFY -> HOLD. Reasons, recommended action, risk graph and `GET /risk/{id}` all follow |
| Home overview | Counts, average risk and recent calls match the backend |
| Incident detail | Evidence JSON, SHA-256 hash and model versions render |
| Mock labelling | DEMO banner plus per-panel stub notes visible throughout |

Four runtime defects were found and fixed across the on-device passes: a
WebSocket start race, a stale Home screen on return, a status-bar overlap, and
interactive outcomes reaching the authoritative decision only on the next audio
window. See `implementation_plan.md`.

Not covered on device: real Android audio capture (Phase 9), physical hardware,
and performance/latency measurement.
