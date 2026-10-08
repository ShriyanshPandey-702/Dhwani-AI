# Dhwani AI --- Mobile UI Design Specification

## 1. Purpose

This document defines the visual design system, screen-by-screen layout,
interaction states, light/dark themes, typography, spacing, colors,
iconography, motion, and implementation constraints for the Dhwani AI
React Native application.

The supplied reference sheet is the primary visual reference.

### Reference screens shown

1.  Splash Screen --- Light + Dark
2.  Login Screen --- Light + Dark
3.  Home / Dashboard --- Light + Dark
4.  Live Call --- Low Risk --- Light + Dark
5.  Live Call --- High Risk --- Light + Dark
6.  Live Challenge --- Light + Dark
7.  Settings --- Light + Dark

The reference sheet does not show a page numbered 7. Do not invent a
page solely because of the numbering.

The existing app may also contain Calls/History, Device, Manual
Analysis, and Call Details/Evidence screens. These must use the same
design system and existing application information architecture.

------------------------------------------------------------------------

## 2. Product Identity

**Brand:** Dhwani AI

Never use the visible spelling `Dhvani AI`.

Product descriptor:

**Real-Time Voice Protection**

Optional supporting phrase:

**Detect. Verify. Prevent.**

Do not add unsupported claims such as guaranteed detection or 100%
accuracy.

------------------------------------------------------------------------

## 3. Overall Visual Direction

The reference uses a premium AI-security/mobile-fintech aesthetic:

-   mobile-first portrait UI
-   premium but uncluttered
-   abstract flowing-wave backgrounds
-   large rounded cards
-   strong hierarchy
-   central risk visualization
-   compact status pills
-   subtle glass/translucent surfaces
-   thin borders
-   soft shadows/glows
-   rounded controls
-   clear risk colors
-   consistent bottom navigation

The product should feel like a real-time security product, not a generic
banking app or chatbot.

------------------------------------------------------------------------

## 4. Theme System

### Light theme

Base: - warm/off-white background - white cards - very light cool-gray
secondary surfaces - deep navy primary text - muted slate secondary
text - subtle blue-gray borders

Suggested tokens:

``` text
Primary Blue:   #2563EB
Deep Indigo:    #3730A3
Cyan:           #06B6D4
Purple:         #7C3AED
Success:        #10B981
Warning:        #F59E0B
Danger:         #EF4444
Text Primary:   #111827
Text Secondary: #64748B
Surface:        #FFFFFF
Background:     #F8FAFC
```

### Dark theme

Base: - near-black/navy background - deep navy cards - elevated
blue-black surfaces - white primary text - muted blue-gray secondary
text - low-opacity blue/white borders

Suggested tokens:

``` text
Background:       #050A13
Surface:           #0B1220
Surface Elevated:  #101A2A
Border:            #23324A
Text Primary:      #F8FAFC
Text Secondary:    #94A3B8
Primary Blue:      #3B82F6
Cyan:              #22D3EE
Purple:            #8B5CF6
Success:           #22C55E
Warning:           #F59E0B
Danger:            #FF4D5A
```

The dark reference uses luminous blue/purple/coral waves.

------------------------------------------------------------------------

## 5. Background System

### Light mode

Use a warm-white base with very low-opacity flowing curves in: - blue -
lavender - pink - cyan

### Dark mode

Use a near-black/navy base with thin luminous flowing curves in: -
blue - indigo - purple - coral

Background artwork must remain secondary to content. Add a readability
overlay when necessary.

No photographs or stock imagery.

------------------------------------------------------------------------

## 6. Typography

Use the platform system font or an available Inter/SF-Pro-like font.

``` text
Risk/display:     32–48 px, bold
Screen title:     22–26 px, semibold/bold
Section title:    16–18 px, semibold
Body:             14–16 px
Secondary:        12–13 px
Micro label:      10–11 px, medium/semibold
```

Keep primary information high contrast.

------------------------------------------------------------------------

## 7. Spacing and Shape

Spacing scale:

``` text
4, 8, 12, 16, 20, 24, 32, 40, 48
```

Radius:

``` text
Chip:       8–10
Input:      12–14
Button:     14–18
Card:       16–22
Risk orb:   circular
```

Interactive controls should generally provide about 44px minimum touch
area.

------------------------------------------------------------------------

## 8. Iconography

Use one consistent rounded/modern line-icon family.

Icons may represent: - microphone - calls - home - device - settings -
notification - security - identity - warning - verification - language -
privacy

Emoji may be used only as small accents. Important controls should use
proper icons.

------------------------------------------------------------------------

# 9. Splash Screen

### Light

Composition: 1. abstract pastel wave background 2. centered Dhwani AI
shield/logo 3. large `Dhwani AI` 4. `Real-Time Voice Protection` 5.
`Detect. Verify. Prevent.` 6. bottom `🇮🇳 Built for a Safer India`

### Dark

Same composition using: - dark navy background - luminous
blue/purple/coral waves - brighter logo - white text - subtle glow

Optional motion: - slow background movement - logo fade/scale - subtle
loading indicator

------------------------------------------------------------------------

# 10. Login Screen

### Layout

-   wave background
-   centered shield/logo
-   Dhwani AI title
-   subtitle
-   Sign In / Create Account segmented control
-   Email or Phone
-   Password
-   Remember Me
-   Forgot Password
-   primary gradient Sign In button
-   divider
-   Google / Apple / institutional options

### Dark

Use dark translucent cards, luminous borders, and blue/purple primary
controls.

Inputs need: - rounded shape - icon/label - focus state - error state -
disabled state - password visibility control

Do not imply social authentication is functional unless the existing
backend supports it.

------------------------------------------------------------------------

# 11. Home / Dashboard

### Header

-   Dhwani AI logo/name
-   notification
-   profile avatar
-   greeting using actual configured user name
-   supporting line: `Your calls are being protected in real time.`

### Protection Card

Show: - shield icon - `Protection Active` -
`Monitoring incoming calls` - actual monitoring status/toggle

### Summary Cards

Three compact cards:

``` text
Calls Today
Alerts
Holds
```

Values must come from real app data.

### Recent Activity

Each row: - caller/contact - number when available - risk/status pill -
timestamp

### Bottom Navigation

``` text
Home
Calls
Live Analysis / central action
Device
Settings
```

Central live-analysis action should be visually prominent.

Never hardcode demo counts.

------------------------------------------------------------------------

# 12. Calls / History

Use the same design language.

Header: `Call History`

Optional search/filter if supported.

Filter examples:

``` text
All
Safe
Suspicious
High Risk
Blocked
```

Call row: - caller/contact - source - timestamp - risk state -
decision - score when available

Empty state: `No call history yet`

Never insert sample calls into production runtime.

------------------------------------------------------------------------

# 13. Live Call --- Low Risk

This is a primary SIH demo screen.

### Header

-   back
-   call duration
-   live indicator

### Caller

Show: - real caller name if available - real number if available -
verification/contact state - actual source: SIM/VoIP/microphone

Never show a fake number in live mode.

### Central Risk Orb

Large animated circular visualization.

Display the actual Risk Engine score:

``` text
[REAL SCORE]
LOW RISK
```

Low-risk styling: - green/teal - subtle pulse - thin waveform/ring
layers

### Audio visualization

Show a waveform/activity visualization only when real audio is active.

### Live metrics

``` text
Authenticity
Identity
Context
```

Use real backend values.

### Live Transcript

Show actual Whisper transcript as it arrives.

Use `NO SPEECH` or `UNAVAILABLE` when appropriate.

### Controls

Reference: - Mute - End Call - Keypad

Only show controls supported by the actual platform.

------------------------------------------------------------------------

# 14. Live Call --- High Risk

Same structure as Low Risk, but with a clear danger state.

### Risk Orb

-   red/coral
-   stronger glow
-   stronger pulse
-   actual score
-   `HIGH RISK` only when actual risk state is HIGH

### Alert

Example visual structure:

`Suspicious patterns detected`

Only render when actual evidence supports it.

### Metrics

``` text
Authenticity
Identity
Context
```

### Detailed evidence

The screen must make these real backend outputs visible:

#### Voice Authenticity

-   AASIST-L result
-   authenticity probability/score
-   acoustic evidence
-   spectral evidence
-   prosody evidence

#### Speaker Identity

-   ECAPA-TDNN
-   match score
-   confidence
-   consistency
-   enrollment status

#### Acoustic

-   RMS
-   SNR
-   clipping
-   energy variation

#### Spectral

-   spectral centroid
-   flatness
-   rolloff
-   ZCR
-   spectral variation

#### Prosody / Behavior

-   F0/pitch
-   F0 variation
-   energy variation
-   voiced/unvoiced structure
-   speech duration
-   pause duration
-   rhythm
-   microvariation

#### Context

-   financial context
-   credential request
-   authority/impersonation
-   urgency
-   detected phrases
-   language

#### Security decision

-   ALLOW
-   VERIFY
-   CHALLENGE
-   HOLD
-   BLOCK
-   ESCALATE
-   reasons
-   recommended action

Never fabricate metrics.

------------------------------------------------------------------------

# 15. Live Challenge

### Header

`Live Challenge`

### Hero

Large microphone icon with flowing blue/purple waves.

### Main text

`Verifying the caller with a live challenge`

Supporting text:
`Asking an unexpected question helps confirm whether this is a real person or a voice clone.`

### Challenge card

Display the actual backend-issued challenge text.

The example shown in the reference is visual only; runtime text must
come from the challenge engine.

### Response state

Show: - listening/recording - response timer - response status

### Action

`Cancel Challenge`

Only show other actions if supported by the real workflow.

Never claim challenge completion until backend confirmation.

------------------------------------------------------------------------

# 16. Device Screen

Use the same bottom navigation and theme.

Show real: - device status - microphone status - call screening status -
backend/WebSocket connection - source capability - Android
call-screening state

Status labels:

``` text
ACTIVE
CONNECTED
NOT CONFIGURED
UNAVAILABLE
UNSUPPORTED
```

Never invent device health values.

------------------------------------------------------------------------

# 17. Manual Analysis

Structure:

-   title
-   audio source selector
-   record/select audio
-   analysis status
-   authenticity
-   speaker identity
-   acoustic/spectral
-   prosody
-   context
-   final risk/decision

If a metric cannot be calculated:

`UNAVAILABLE — insufficient audio`

Never substitute zero.

------------------------------------------------------------------------

# 18. Call Details / Evidence

Detailed incident view:

1.  Call metadata
2.  Risk summary
3.  Voice authenticity
4.  Speaker identity
5.  Acoustic analysis
6.  Spectral analysis
7.  Prosody/behavior
8.  Conversation context
9.  Historical consistency
10. Transaction guard
11. Security decision
12. Event timeline
13. Privacy/retention

Use collapsible cards for density.

------------------------------------------------------------------------

# 19. Settings

Match the reference.

### Profile

-   avatar
-   actual user name
-   actual email
-   arrow

### Protection

-   Live call monitoring
-   Auto challenge on high risk
-   Independent verification

Only show settings actually backed by the app.

### Notifications

-   Risk alerts
-   Email notifications
-   Trusted contacts

Do not imply email delivery is active if no email provider is
configured.

### Appearance

``` text
Light mode
Dark mode
```

Persist selection.

### Language

Show actual configured language.

------------------------------------------------------------------------

# 20. Risk Colors

``` text
INSUFFICIENT EVIDENCE → neutral gray/blue
LOW                  → green/teal
SUSPICIOUS           → amber
HIGH                 → orange/coral
CRITICAL             → red
```

Always pair color with text/icon.

------------------------------------------------------------------------

# 21. Security Decision Colors

``` text
ALLOW      → green
VERIFY     → blue/cyan
CHALLENGE  → purple/blue
HOLD       → amber
BLOCK      → red
ESCALATE   → orange/red
```

Risk state and security decision are separate concepts.

------------------------------------------------------------------------

# 22. Evidence Cards

All evidence cards should share: - 16--20px radius - subtle border -
translucent/elevated surface - consistent padding - section icon -
title - status pill - compact metrics

Metric format:

``` text
Metric name
Actual value
Unit
Status
```

Unavailable format:

``` text
UNAVAILABLE
[reason]
```

Never use fake zeros.

------------------------------------------------------------------------

# 23. Live Data Contract

The UI is a visualization layer over the real backend:

``` text
Real Audio
→ VAD
→ AASIST / ECAPA / Whisper
→ Acoustic / Spectral / Prosody
→ Context
→ Risk Engine
→ Security Policy
→ REST/WebSocket
→ React Native Store
→ UI
```

No UI-only mock data.

No fabricated changing values.

No fake waveform animation.

------------------------------------------------------------------------

# 24. Live Transcript

The transcript must feel genuinely real-time:

``` text
Speech
→ VAD
→ short asynchronous Whisper processing
→ partial/final transcript
→ immediate UI update
→ incremental context detection
```

Sequence protection must prevent stale transcript results from replacing
newer results.

------------------------------------------------------------------------

# 25. Motion

Allowed: - risk-orb pulse - live indicator - wave movement - card
entrance - progress transitions - button feedback - transcript update -
challenge timer

Avoid: - excessive motion - distracting particles - fake waveform
activity - animations that conceal latency

Motion must communicate real system state.

------------------------------------------------------------------------

# 26. Accessibility

-   high contrast
-   practical 44px touch targets
-   do not rely only on color
-   readable status labels
-   understandable dynamic content
-   avoid excessive motion

------------------------------------------------------------------------

# 27. Responsive Rules

Primary target: - Android portrait - approximately 390×844 logical
pixels

Use vertical scrolling.

Keep above-the-fold content focused on: - caller - risk - current
decision - live transcript

Detailed evidence may appear below.

------------------------------------------------------------------------

# 28. SIH Demo Priority

The Live Analysis screen is the most important screen.

The visual story should be:

``` text
Call
→ Voice authenticity
→ Speaker identity
→ Acoustic/spectral evidence
→ Prosody/behavior
→ Live transcript
→ Context/intent
→ Risk
→ Security decision
→ Verify/Challenge/Hold/Block
```

The UI should make this chain obvious.

------------------------------------------------------------------------

# 29. Implementation Constraints

1.  Do not change backend solely for visual design.
2.  Do not replace AASIST-L.
3.  Do not replace ECAPA-TDNN.
4.  Do not change frozen Risk Engine weights/thresholds.
5.  Do not add Resemble AI.
6.  Do not create fake integrations.
7.  Do not create fake SMS/email delivery.
8.  Do not claim cellular raw-audio capture.
9.  Do not fabricate multilingual coverage.
10. Do not hardcode risk scores.
11. Do not hardcode fake transcripts.
12. Preserve existing REST/WebSocket contracts unless extensions are
    backward compatible.
13. Preserve validated navigation and functionality.
14. Visual redesign must not break the real-time pipeline.

------------------------------------------------------------------------

# 30. Reference Matching

The supplied reference image is the primary visual target.

### Light

Match: - warm white - pastel blue/lavender/pink waves - white cards -
navy text - blue/indigo buttons - green/teal safe states - coral/red
high-risk states

### Dark

Match: - deep navy/black - luminous blue/purple/coral waves - dark
translucent cards - white text - electric blue controls - cyan/teal live
state - coral/red high-risk state

Light and dark must look like the same product.

------------------------------------------------------------------------

# 31. Gemini UI Image Generation Requirements

Generate mobile UI reference images in portrait orientation.

For each screen: - produce Light and Dark versions - maintain the exact
same layout between themes - keep logo, typography, spacing and
navigation consistent - use the supplied reference sheet as visual
guidance - use realistic placeholder data only inside the DESIGN IMAGE -
never imply that placeholder values must be hardcoded into the
application - show complete screens, not isolated components - keep all
pages visually consistent

For pages without a direct screenshot reference, use the same design
system and the existing Dhwani AI app information architecture. Do not
invent unsupported product functionality.
