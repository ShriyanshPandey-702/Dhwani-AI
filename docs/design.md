# Dhwani AI --- UI Design Specification

**File:** `design.md`\
**Product:** Dhwani AI\
**Platform:** React Native Android\
**Purpose:** Complete visual/UI redesign based on the supplied Dhwani AI
light-theme and dark-theme reference templates.

------------------------------------------------------------------------

## 1. Design Objective

Redesign the Dhwani AI mobile application to visually match the supplied
UI reference.

The reference contains two complete visual directions:

1.  **Light Theme**
2.  **Dark Theme**

The implementation must feel like a polished security product, not a
generic AI dashboard.

The design language should communicate:

-   trust
-   real-time protection
-   voice intelligence
-   security
-   clarity
-   calm for low-risk situations
-   urgency for elevated-risk situations

The existing backend, ML pipeline, API contracts, WebSocket streaming,
call-screening service, risk engine, and navigation logic must **not be
rewritten merely for visual redesign**.

This document controls the UI layer.

------------------------------------------------------------------------

# 2. Reference Screens

The supplied reference contains these eight primary screens:

1.  Splash Screen
2.  Login Screen
3.  Home / Dashboard
4.  Live Analysis --- Low Risk
5.  Live Analysis --- High Risk
6.  Live Challenge
7.  Verify Through Trusted Channel
8.  Call History

Both light and dark themes must implement the same information
architecture.

------------------------------------------------------------------------

# 3. Brand

## Product Name

Use exactly:

**Dhwani AI**

The visible product name throughout the application must consistently be **Dhwani AI**.

Internal package/application identifiers may remain unchanged if
required for Android build compatibility.

------------------------------------------------------------------------

# 4. Logo

Replace any old logo with the supplied **Dhwani AI shield
logo**.

The logo should be used consistently in:

-   Splash screen
-   Login screen
-   App header
-   Notification branding where supported
-   About/Settings
-   App icon
-   Android launcher icon
-   Any empty/error state that currently displays the old logo

The logo must retain transparent/background-safe variants.

Do not redraw or distort the logo.

Maintain aspect ratio.

Recommended usage:

-   Splash: large centered logo
-   Login: medium centered logo
-   Header: small logo/icon
-   Launcher: adaptive Android icon using the supplied artwork

Search the repository for existing Dhwani logo assets before creating
another copy.

Prefer one canonical asset.

------------------------------------------------------------------------

# 5. Overall Visual Language

## Design principles

The application should feel:

-   premium
-   minimal
-   technical but understandable
-   security-focused
-   calm
-   spatial
-   responsive

Avoid:

-   generic SaaS dashboards
-   excessive gradients
-   excessive rounded cards
-   emoji-heavy interfaces
-   excessive icons
-   random animated elements
-   excessive technical jargon
-   crowded screens
-   fake data
-   decorative charts with no real data

Use visual hierarchy rather than adding more UI elements.

------------------------------------------------------------------------

# 6. Theme System

Implement a proper theme token system.

Do not hardcode colors individually inside screens.

Create centralized theme tokens such as:

``` text
colors.background
colors.surface
colors.surfaceElevated
colors.textPrimary
colors.textSecondary
colors.textMuted
colors.border
colors.accent
colors.accentSoft
colors.success
colors.warning
colors.danger
colors.critical
colors.orbLow
colors.orbHigh
```

The application must support:

-   Light
-   Dark
-   System/default if the existing Settings architecture supports it

Theme switching must update the entire application consistently.

No screen may remain stuck in the other theme.

------------------------------------------------------------------------

# 7. Light Theme

The supplied light reference uses a warm/off-white background rather
than pure white.

Approximate visual direction:

``` text
Background:
#F8F4F2

Surface:
#FFFFFF

Primary text:
#172536

Secondary text:
#63707D

Muted text:
#89939D

Border:
#E4E7E9

Primary accent:
soft teal / blue-green

Secondary accent:
soft blush pink

Danger:
soft coral/red

High-risk surface:
very light warm red/pink
```

These are design-direction tokens, not mandatory exact RGB values.

The final colors should be tuned against the supplied reference image.

------------------------------------------------------------------------

# 8. Dark Theme

The supplied dark reference uses a deep blue-black background.

Approximate visual direction:

``` text
Background:
#071017

Surface:
#0D171F

Elevated surface:
#111E27

Primary text:
#F4F7F8

Secondary text:
#A9B5BD

Muted text:
#74838D

Border:
#24343E

Teal:
#5FD0C5

Soft blue:
#7FAFC5

Pink:
#F2C1C5

Danger:
#FF747A
```

Do not make the dark theme pure black.

The reference has subtle blue/teal depth.

------------------------------------------------------------------------

# 9. Typography

Use a clean modern sans-serif.

Typography hierarchy:

## Screen title

Large / semibold.

Example:

`Live Analysis`

## Main metric

Very large / bold.

Example:

`78`

## Risk state

Medium / semibold.

Example:

`HIGH RISK`

## Section title

Medium / semibold.

Example:

`Authenticity`

## Supporting text

Regular.

Example:

`Live transcript (partial)`

## Metadata

Small / muted.

Example:

`SIM Call`

Avoid excessive uppercase text.

Use uppercase primarily for compact security labels and states.

------------------------------------------------------------------------

# 10. Global Spacing

Use a consistent spacing scale.

Recommended:

``` text
4
8
12
16
20
24
32
40
48
```

Primary horizontal screen padding:

`16–20dp`

Cards should have enough breathing room.

Do not compress every element into a single viewport.

------------------------------------------------------------------------

# 11. Global Card Style

Cards should have:

-   subtle radius
-   thin border
-   controlled shadow/elevation
-   strong internal spacing

Light:

-   white surfaces
-   subtle warm/gray border
-   very soft shadow

Dark:

-   elevated blue-black surface
-   subtle border
-   minimal shadow

Avoid excessive glassmorphism.

------------------------------------------------------------------------

# 12. Risk State System

The product uses exactly five user-facing risk states:

1.  **INSUFFICIENT EVIDENCE**
2.  **LOW**
3.  **SUSPICIOUS**
4.  **HIGH**
5.  **CRITICAL**

Do not create a sixth risk state called `SAFE`.

For a normal genuine voice demo, the UI should normally communicate:

**LOW RISK**

rather than inventing a separate SAFE risk state.

------------------------------------------------------------------------

# 13. Risk Colors

Risk colors should communicate urgency without making the entire screen
visually aggressive.

## Insufficient Evidence

Neutral blue/gray.

## Low

Teal / green-teal.

## Suspicious

Amber/orange.

## High

Coral/red.

## Critical

Strong red.

The color should primarily affect:

-   risk orb
-   state badge
-   alert indicator
-   relevant evidence highlight
-   CTA when appropriate

Do not recolor the entire screen.

------------------------------------------------------------------------

# 14. Risk Orb / Score Visualization

The central score visualization is one of the most important components.

It should be inspired by the supplied reference.

Structure:

``` text
outer soft glow
     ↓
animated ring / wave
     ↓
large score
     ↓
risk state
```

Example:

``` text
        78
      HIGH RISK
```

The orb must respond to real application state.

It must NOT use random animation to pretend that analysis is happening.

During active analysis:

-   subtle pulse
-   ring movement
-   waveform response
-   score transition

When idle:

-   no continuous fake score changes

When analysis stops:

-   animation settles

The visual should feel similar to a calm Siri-like voice intelligence
visualization, while remaining an original Dhwani AI design.

------------------------------------------------------------------------

# 15. Splash Screen

Reference:

Large Dhwani AI logo.

Text:

**Dhwani AI**

Subtitle:

**Real-Time Voice Protection**

Supporting line:

**A safer tomorrow, for every conversation.**

Bottom:

**Built for a Safer India**

Use the supplied logo.

Light and dark versions must preserve the same composition.

Do not add unnecessary loading information.

------------------------------------------------------------------------

# 16. Login Screen

Structure:

``` text
Dhwani AI logo

Dhwani AI
Secure Calls. Trusted People.

Email or Phone
Password

Remember me        Forgot password?

Sign In

or continue with

Google
Apple
Institution / Enterprise

New to Dhwani AI?
Create an account
```

Visual hierarchy must match the supplied template.

Use compact input fields.

Password visibility control should remain functional.

Do not redesign authentication logic as part of this UI task.

------------------------------------------------------------------------

# 17. Home / Dashboard

The dashboard is the primary product screen.

Header:

``` text
[Dhwani AI logo] Dhwani AI              [notification] [profile]
```

Greeting:

``` text
Good Morning,
Shriyansh 👋
```

Supporting line:

`Your calls are being protected in real time.`

If the greeting already uses a real user name, preserve the existing
user data.

------------------------------------------------------------------------

## Protection Status Card

Reference:

``` text
Protection Active       [toggle]
Monitoring incoming calls
```

Use:

-   shield icon
-   status text
-   toggle

The toggle must reflect the real application state.

It must not be a decorative switch.

------------------------------------------------------------------------

## Summary Metrics

Three compact cards:

``` text
Calls Today
12

Alerts
1

Holds
0
```

These values must come from actual application state.

No hardcoded demo values.

------------------------------------------------------------------------

# 18. Dashboard --- Current Analysis

If an active session exists, show the current risk prominently.

Example:

``` text
Current Analysis

+91 XXXXX XXXXX
Live Analysis

          18
        LOW RISK

Authenticity    Identity    Context
     16            12         24
```

The values must be actual backend results.

If no active analysis exists, show an appropriate empty state.

Do not continuously fluctuate the dashboard when there is no active
session.

------------------------------------------------------------------------

# 19. Dashboard Evidence Cards

The user specifically wants the details to remain visible instead of
flashing briefly.

Implement four persistent evidence cards:

### Authenticity

Show:

-   synthetic/AI evidence
-   confidence
-   model evidence
-   status

Example:

``` text
AUTHENTICITY

16
LOW

Synthetic evidence
Low

Confidence
High
```

------------------------------------------------------------------------

### Identity

Show:

-   reference status
-   speaker similarity
-   identity mode
-   confidence

Example:

``` text
IDENTITY

12
LOW

Reference
Available

Similarity
0.82
```

Never imply identity verification if no reference speaker exists.

------------------------------------------------------------------------

### Active Liveness

Show:

-   current status
-   challenge state
-   response state

States:

``` text
Not Required
Pending
Passed
Failed
Insufficient Evidence
```

------------------------------------------------------------------------

### Consequences / Context

Show:

-   financial request
-   credential request
-   urgency
-   sensitive information
-   recommended action

Example:

``` text
CONTEXT

91
HIGH

Sensitive financial request detected

Recommended:
VERIFY
```

------------------------------------------------------------------------

# 20. Recent Calls

Dashboard section:

``` text
Recent Calls                         See All
```

Each row:

``` text
[icon]
Caller
+91 XXXXX XXXXX

Risk badge                         Time
```

Example states:

``` text
LOW
SUSPICIOUS
HIGH
CRITICAL
INSUFFICIENT EVIDENCE
```

Clicking a row opens the detailed call screen.

Recent calls must update live from actual application state.

No hardcoded sample calls.

------------------------------------------------------------------------

# 21. Incoming Call Behaviour

When an incoming call is detected:

1.  show notification
2.  update dashboard
3.  add/update Recent Activity
4.  allow user to open call details

The notification and dashboard must refer to the same incident ID.

Do not create duplicates.

If only SIM metadata is available, clearly show:

`SIM Call`

and:

`Audio analysis unavailable for raw cellular media`

Do not falsely claim that the application analyzed caller PCM.

------------------------------------------------------------------------

# 22. Live Analysis --- Low Risk

Reference screen:

Header:

`Live Analysis`

Caller:

`+91 91234 56789`

`Unknown Caller`

Source badge:

`SIM Call`

Central orb:

``` text
18
LOW RISK
```

Below:

``` text
Authenticity    Identity    Context
16              12          24
Low             Low         Low
```

Then:

``` text
Live Transcript (partial)

"Hello, I just wanted to inform you..."
```

Context status:

`No sensitive intent detected`

Bottom call controls remain functional.

Important:

The displayed values must come from actual analysis.

------------------------------------------------------------------------

# 23. Live Analysis --- High Risk

Same layout as low-risk screen.

Change only the relevant visual emphasis.

Central:

``` text
78
HIGH RISK
```

Evidence:

``` text
Authenticity    Identity    Context
82              54          91
High            Moderate    High
```

Context:

`Sensitive financial request detected`

Use a strong but controlled red/coral accent.

Do not turn the entire screen red.

------------------------------------------------------------------------

# 24. Live Challenge

Reference:

Title:

`Live Challenge`

Subtitle:

`Verifying the caller with a live challenge`

Explanation:

`Asking an unexpected question helps confirm whether this is a real person or a voice clone.`

Show:

-   microphone/voice visual
-   challenge prompt
-   response listening state
-   progress indicator

Example:

``` text
Question being asked...

"For security, please tell me the
last 4 digits of the project code
we discussed last week."
```

Buttons:

`Continue Monitoring`

`Hold This Request`

These buttons must connect to real existing actions.

Do not add non-functional buttons.

------------------------------------------------------------------------

# 25. Trusted Channel Verification

Reference:

Title:

`Verify Through Trusted Channel`

Explanation:

`This is a high-risk request. We recommend confirming through an independent channel.`

Actions:

### Call Back

`Call the number on file`

### Send Verification Link

`Send to registered email / SMS`

### Notify Trusted Contact

`Alert someone from your organization`

The buttons must only be shown if their underlying integration exists.

If an integration is not configured, show an honest unavailable state
rather than pretending the action completed.

------------------------------------------------------------------------

# 26. Call History

Reference:

Title:

`Call History`

Filters:

``` text
All
Low
Suspicious
High Risk
```

Use horizontal compact chips.

History rows show:

-   caller
-   number
-   timestamp
-   risk state
-   decision

Example:

``` text
Unknown Caller
+91 91234 56789

HIGH RISK
10:24 AM
```

Click opens detailed analysis.

------------------------------------------------------------------------

# 27. Detailed Call Screen

When the user clicks a call, show a persistent security summary.

Top:

``` text
Caller
+91 XXXXX XXXXX

Risk
78
HIGH
```

Then:

``` text
AUTHENTICITY
IDENTITY
ACTIVE LIVENESS
CONSEQUENCES
```

Each section should expand or remain visible depending on screen height.

The evidence must not disappear after a few seconds.

------------------------------------------------------------------------

# 28. Bottom Navigation

Maintain a five-item navigation structure:

``` text
Home
Calls
Analyze
Device
Settings
```

Use simple line icons.

Active tab uses the primary accent.

Inactive tabs use muted text/icons.

Do not use excessive icon labels.

------------------------------------------------------------------------

# 29. Analyze Screen

The Analyze screen should focus on real analysis workflows.

Primary actions:

### Live Microphone Analysis

Start real microphone analysis.

### Analyze Audio File

Select an audio file.

### Compare Reference + Target

Select:

``` text
Reference voice
Target audio
```

Then analyze.

Remove user-facing demo buttons such as:

-   Analyze Deepfake Sample Audio
-   Analyze Benign Human Audio
-   Test Short Audio Gate
-   Run Demo Scenario

Test fixtures can remain in developer/test code but must not appear in
the production UI.

------------------------------------------------------------------------

# 30. Manual Audio Analysis

Show:

``` text
Audio
Duration
Sample rate
Windows analyzed
Processing time
```

Then:

``` text
Risk Score
Risk State
Decision
```

Then evidence:

``` text
Authenticity
Identity
Prosody
Context
```

Window timeline:

``` text
Window 1
Synthetic evidence: 18%

Window 2
Synthetic evidence: 22%

Window 3
Synthetic evidence: 71%
```

Never display:

`NaN%`

If evidence is unavailable:

`Unavailable`

or:

`Insufficient Evidence`

------------------------------------------------------------------------

# 31. Reference / Target Comparison UI

Create a clean comparison card:

``` text
VOICE COMPARISON

REFERENCE
Original / Genuine Voice
[filename]

TARGET
Audio Under Analysis
[filename]
```

Results:

``` text
Speaker Similarity
82%

Synthetic Evidence
91%

Identity Match
High

Authenticity
High synthetic evidence
```

Then:

``` text
Interpretation

The target voice is acoustically similar to the reference
speaker while showing elevated synthetic-voice evidence.
```

Only show this interpretation when supported by actual model results.

------------------------------------------------------------------------

# 32. Device Screen

The existing "Trust this device" interaction must not look like a
meaningless decorative control.

If device trust has real security functionality:

show:

``` text
This device
Realme 8

Device protection
Active

Trusted
Yes
```

If it has no real backend/security effect:

remove the interactive trust control.

Do not keep a button that changes nothing.

------------------------------------------------------------------------

# 33. Settings

Include:

``` text
Appearance
  Light
  Dark
  System

Notifications
  Incoming calls
  Security alerts
  Email alerts

Analysis
  Risk updates
  Live transcript

Privacy
  Audio retention
  Evidence storage

About
  Dhwani AI
  Version
```

Keep technical implementation details out of the normal user-facing
settings.

------------------------------------------------------------------------

# 34. Notifications UI

Notifications should use Dhwani AI branding.

Low-risk informational:

``` text
Dhwani AI

Incoming call detected
+91 XXXXX XXXXX
LOW RISK
```

Elevated:

``` text
Dhwani AI

Voice security alert
High-risk voice activity detected
Risk 78
```

Critical:

``` text
Dhwani AI

Critical voice security alert
Immediate verification required
```

Do not send a notification for every 250ms/audio window.

Use meaningful state transitions.

------------------------------------------------------------------------

# 35. Animation

Animations must communicate system state.

Use:

-   orb pulse
-   ring movement
-   waveform
-   subtle transitions
-   card expansion
-   screen transitions

Do not use:

-   random movement
-   excessive bouncing
-   constant animated backgrounds
-   distracting particles

Animation frequency should reduce when the system is idle.

------------------------------------------------------------------------

# 36. Loading States

Use polished skeleton/loading states.

Examples:

``` text
Analyzing voice...
Processing audio...
Waiting for sufficient speech...
Loading evidence...
```

Do not show fake numerical values while loading.

------------------------------------------------------------------------

# 37. Empty States

Example:

``` text
No active analysis

Start a microphone session or
analyze an audio file.
```

History:

``` text
No calls yet
```

Reference comparison:

``` text
Add a genuine reference voice
to compare speaker identity.
```

------------------------------------------------------------------------

# 38. Error States

Errors must be understandable.

Example:

``` text
Audio analysis unavailable

We could not obtain enough usable speech
for reliable analysis.

Try again with clearer audio.
```

Do not expose raw stack traces.

Developer logs can contain detailed errors.

------------------------------------------------------------------------

# 39. Accessibility

Maintain:

-   readable contrast
-   minimum comfortable touch targets
-   dynamic text compatibility where practical
-   accessible labels for icons
-   screen-reader labels
-   no information conveyed by color alone

For example:

Do not use only red to indicate HIGH.

Also show:

`HIGH RISK`

------------------------------------------------------------------------

# 40. Responsive Behaviour

The application must work on the physical Realme 8.

Do not assume the reference screenshot's exact dimensions.

Use:

-   SafeArea
-   flexible widths
-   ScrollView where required
-   responsive card layout

No clipped content.

No overlapping bottom navigation.

No text truncation for important risk information.

------------------------------------------------------------------------

# 41. Implementation Architecture

Create/reuse:

``` text
theme/
  colors
  typography
  spacing
  shadows
  radii

components/
  DhwaniLogo
  RiskOrb
  RiskBadge
  EvidenceCard
  AuthenticityCard
  IdentityCard
  LivenessCard
  ConsequenceCard
  CallRow
  NotificationBanner
  ThemeToggle
```

Avoid duplicating the same styles across screens.

------------------------------------------------------------------------

# 42. Data Binding Rule

UI must consume actual application state.

Never hardcode:

``` text
78
18
91
12
82
```

Those numbers are visual examples from the reference.

The production application must receive:

``` text
riskScore
riskState
authenticity
identity
liveness
context
decision
caller
timestamp
source
```

from the existing real data layer.

------------------------------------------------------------------------

# 43. Critical Product Rule

The UI must never imply that a normal SIM call's raw caller audio has
been analyzed if Android only supplied call metadata.

Clearly distinguish:

### SIM Metadata

Caller information and screening metadata.

### Device Microphone

Audio captured by the device microphone.

### Authorized VoIP / Call Media

Actual call audio available through the controlled media path.

This distinction must remain visible where relevant.

------------------------------------------------------------------------

# 44. Branding Standards Checklist

Ensure all user-visible branding consistently displays:

``` text
Dhwani AI
```

Do not modify internal technical package identifiers:

``` text
com.voiceshieldapp
```

unless a separate build-safe migration is explicitly verified.

------------------------------------------------------------------------

# 45. Do Not Change Backend Behaviour

This design task must not:

-   rewrite AASIST
-   replace ECAPA
-   replace Whisper
-   alter StreamWindower constants
-   alter ML worker concurrency
-   alter WebSocket contracts
-   remove risk states
-   invent fake scores
-   introduce mock analysis into production UI
-   fake SIM audio capture

The UI should be connected to the existing production pipeline.

------------------------------------------------------------------------

# 46. Acceptance Criteria

The redesign is complete only when:

### Theme

-   Light theme matches reference direction.
-   Dark theme matches reference direction.
-   Theme switch works.
-   No inconsistent screen remains.

### Branding

-   Dhwani AI appears everywhere.
-   Legacy branding is absent from user-visible UI.
-   New Dhwani logo is used consistently.
-   Launcher icon is updated.

### Dashboard

-   Protection status works.
-   Calls/Alerts/Holds use real values.
-   Recent Calls use real data.
-   Active analysis is clearly visible.

### Risk

-   Five states are respected.
-   Risk orb reflects actual score.
-   No fake animation when idle.
-   Evidence remains visible.

### Calls

-   Incoming call updates dashboard.
-   Incoming call updates Recent Activity.
-   Notification appears.
-   Clicking call opens persistent evidence.

### Analysis

-   Microphone analysis screen is polished.
-   Manual analysis is polished.
-   Reference/target comparison has a dedicated workflow.
-   No demo buttons remain.

### Evidence

-   Authenticity
-   Identity
-   Active Liveness
-   Consequences

are all visually persistent and understandable.

### Quality

-   No NaN
-   No undefined
-   No clipped content
-   No broken icons
-   No placeholder text
-   No fake values
-   No non-functional buttons

------------------------------------------------------------------------

# 47. Final Instruction to Antigravity

Implement this design directly in the existing Dhwani AI React Native
application.

Use the supplied reference image as the visual source of truth.

Do not replace the application's working backend.

Do not create mock data.

Do not change functionality just to make the screenshots look correct.

After implementation:

1.  run TypeScript checks
2.  run Jest
3.  build Android
4.  install on Realme 8
5.  inspect every screen in light mode
6.  inspect every screen in dark mode
7.  test navigation
8.  test theme switching
9.  test microphone screen
10. test manual analysis screen
11. test call history
12. test incoming-call UI
13. verify the new Dhwani AI logo
14. verify no legacy branding remains in user-visible UI
15. report files changed
16. report tests passed/failed

Do not commit automatically.

The final result should look like the supplied Dhwani AI design
reference while remaining connected to the real application data and
existing ML pipeline.
