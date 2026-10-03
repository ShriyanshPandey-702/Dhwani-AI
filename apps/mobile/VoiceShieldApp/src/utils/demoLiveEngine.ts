/**
 * Dhwani AI — Live Analysis Demo Mode Engine
 * ==========================================
 * Isolated deterministic presentation simulation for SIH demonstration.
 *
 * CRITICAL DEMO CONSTRAINTS:
 *   - Labeled clearly as DEMO MODE / SIMULATION (Not real measured ML accuracy).
 *   - Audio playback position (`audio.currentTime`) is the single source of truth.
 *   - Total duration: 45.632 seconds (matches final_audio.mp3).
 *   - Phase timeline:
 *       0s  – 13s: REAL HUMAN VOICE (Hindi speech)
 *       13s – 16s: SILENCE (Clean flat waveform, "No speech detected", score -> 0)
 *       16s – 33s: AI CLONED VOICE (Score gradually rises to ~80, HOLD/VERIFY)
 *       33s – 36s: SILENCE (Clean flat waveform, score -> 0)
 *       36s – 45.632s: AI-GENERATED VOICE (Score escalates to 99-100, CRITICAL, BLOCKED)
 *   - Waveform is driven by acoustic spectral data from the actual audio signal.
 *   - Fully isolated from production detection pipeline.
 */

import { DEMO_WAVEFORM_DATA } from './demoWaveformData';
import { RiskState, Decision, TimelineEntry } from '../types';

export const LIVE_DEMO_MODE = true;
export const DEMO_AUDIO_DURATION = 45.632; // actual audio playback duration
export const DEMO_DECAY_DURATION = 2.5; // post-playback smooth decay duration
export const DEMO_TOTAL_DURATION = DEMO_AUDIO_DURATION + DEMO_DECAY_DURATION; // 48.132s

export type DemoPhase = 'HUMAN' | 'SILENCE' | 'AI_CLONED' | 'AI_GENERATED' | 'POST_AUDIO_ENDED';

export interface DemoTranscriptState {
  transcript: string;
  isSilence: boolean;
  model: string;
}

export interface DemoRiskState {
  targetScore: number;
  riskState: RiskState;
  riskTrend: 'stable' | 'rising' | 'falling';
  sublabel: string; // 'LIVE RISK' or 'NO VOICE'
}

export interface DemoMultimodalState {
  authenticity: {
    score: number;
    spoof_probability: number;
    acoustic_anomaly: string;
    spectral_anomaly?: 'LOW' | 'MEDIUM' | 'HIGH';
    prosody_anomaly?: 'LOW' | 'MEDIUM' | 'HIGH';
    label: string;
    model_version: string;
    confidence: number;
    spectral_score?: number;
    prosody_score?: number;
  };
  identity: {
    match_score: number | null;
    enrollment_status: 'NOT_ENROLLED' | 'ENROLLED' | 'MISMATCH';
    consistency: 'GOOD' | 'VARIABLE' | 'POOR' | 'UNKNOWN';
    confidence: number;
  };
  context: {
    score: number;
    transcript: string;
    transcript_model: string;
    consequence: 'low' | 'medium' | 'high' | 'critical';
    financial_request: boolean;
    otp_request: boolean;
    credential_request: boolean;
    sensitive_information_request: boolean;
    urgency: boolean;
    social_engineering: boolean;
    authority_claim: boolean;
  };
  warningBanner: {
    message: string;
    subMessage: string;
    icon: string;
    severity: 'safe' | 'info' | 'warning' | 'critical';
  };
  decision: Decision;
  decisionReasons: string[];
  recommendedAction: string;
  evidenceConfidence: number;
  challengeState: 'idle' | 'recommended' | 'active' | 'passed';
  verificationState: 'idle' | 'recommended' | 'pending' | 'verified';
  consequenceLevel: 'low' | 'medium' | 'high' | 'critical';
  threatSignals: string[];
  detectedEvents: TimelineEntry[];
}

// ── 1. Phase State Machine ───────────────────────────────────────────────────

export function getDemoPhase(currentTime: number): DemoPhase {
  if (currentTime < 13.0) return 'HUMAN';
  if (currentTime < 16.0) return 'SILENCE';
  if (currentTime < 33.0) return 'AI_CLONED';
  if (currentTime < 36.0) return 'SILENCE';
  if (currentTime < DEMO_AUDIO_DURATION) return 'AI_GENERATED';
  return 'POST_AUDIO_ENDED';
}

// ── 2. Progressive Transcript Engine ─────────────────────────────────────────

const HINDI_WORDS = [
  'एक', 'लड़का', 'जिसका', 'नाम', 'प्रियांशु', 'प्रसाद', 'है',
  'वह', 'आर्टिफिशियल', 'इंटेलिजेंस', 'और', 'मशीन', 'लर्निंग',
  'डिपार्टमेंट', 'ऑफ', 'ठाकुर', 'कॉलेज', 'ऑफ', 'इंजीनियरिंग', 'टेक्नोलॉजी',
  'से', 'पढ़ाई', 'कर', 'रहा', 'है',
  'वह', 'क्वेश्चन', 'बैंक', 'की', 'सूची', 'मांग', 'रहा', 'है',
  'क्योंकि', 'उसको', 'प्रिपेयर', 'करना', 'है',
];

const CLONED_WORDS = [
  'Hi', 'I', 'am', 'your', 'favorite', 'CR,', 'And', 'this', 'is', 'a',
  'simple', 'test', 'of', 'my', 'voice.', 'I', 'am', 'speaking', 'slowly',
  'and', 'naturally', 'using', 'normal', 'words', 'and', 'a', 'comfortable',
  'tone.', 'I', 'am', 'just', 'talking', 'about', 'my', 'day,', 'what', 'I',
  'am', 'doing', 'right', 'now', 'and', 'a', 'few', 'simple', 'things',
  'that', 'I', 'usually', 'do.',
];

const AI_WORDS = [
  'This', 'is', 'a', 'sample', 'of', 'an', 'AI', 'generated', 'voice.',
  'The', 'system', 'can', 'analyze', 'speech,', 'identify', 'suspicious',
  'patterns,', 'and', 'help', 'detect', 'potential', 'digital', 'threats',
  'in', 'real', 'time.',
];

function sliceWords(words: string[], progress: number): string {
  if (progress <= 0) return '';
  const count = Math.max(1, Math.min(words.length, Math.ceil(words.length * progress)));
  return words.slice(0, count).join(' ');
}

export function getDemoTranscript(currentTime: number): DemoTranscriptState {
  const t = Math.max(0, currentTime);

  // 0s – 13s: REAL HUMAN VOICE (Hindi Speech)
  if (t < 13.0) {
    const progress = Math.min(1.0, Math.max(0.04, t / 12.2));
    return {
      transcript: sliceWords(HINDI_WORDS, progress),
      isSilence: false,
      model: 'Deepgram Nova-2 · Hindi (hi-IN)',
    };
  }

  // 13s – 16s: SILENCE
  if (t < 16.0) {
    return {
      transcript: 'No speech detected',
      isSilence: true,
      model: 'Voice Activity Detection (Silence)',
    };
  }

  // 16s – 33s: AI CLONED VOICE
  if (t < 33.0) {
    const progress = Math.min(1.0, Math.max(0.04, (t - 16.0) / 16.2));
    return {
      transcript: sliceWords(CLONED_WORDS, progress),
      isSilence: false,
      model: 'Deepgram Nova-2 · English (en-US)',
    };
  }

  // 33s – 36s: SILENCE
  if (t < 36.0) {
    return {
      transcript: 'No speech detected',
      isSilence: true,
      model: 'Voice Activity Detection (Silence)',
    };
  }

  // 36s – 45.632s: AI-GENERATED VOICE
  if (t < DEMO_AUDIO_DURATION) {
    const progress = Math.min(1.0, Math.max(0.04, (t - 36.0) / 8.8));
    return {
      transcript: sliceWords(AI_WORDS, progress),
      isSilence: false,
      model: 'Deepgram Nova-2 · English (en-US)',
    };
  }

  // 45.632s+: POST-AUDIO COMPLETED
  return {
    transcript: sliceWords(AI_WORDS, 1.0),
    isSilence: true,
    model: 'Voice Activity Detection (Completed)',
  };
}

// ── 3. Smooth Risk Score Engine ──────────────────────────────────────────────

export function getDemoTargetRisk(currentTime: number): DemoRiskState {
  const t = Math.max(0, currentTime);

  // 0s – 13s: REAL HUMAN VOICE (Target: 0 – 4)
  // Progression: 0 → 1 → 2 → 3 → 2 → 4
  if (t < 13.0) {
    let score = 0;
    if (t < 2.5) score = 0;
    else if (t < 5.0) score = 1;
    else if (t < 7.5) score = 2;
    else if (t < 10.0) score = 3;
    else if (t < 12.0) score = 2;
    else score = 4;

    return {
      targetScore: score,
      riskState: 'low',
      riskTrend: 'stable',
      sublabel: 'LIVE RISK',
    };
  }

  // 13s – 16s: FIRST SILENCE (Target: 0 – 1, Smooth decay)
  if (t < 16.0) {
    const decayT = (t - 13.0) / 3.0; // 0 to 1
    const score = Math.max(0, Math.round(4 * (1.0 - decayT)));
    return {
      targetScore: score,
      riskState: 'low',
      riskTrend: 'stable',
      sublabel: 'NO VOICE',
    };
  }

  // 16s – 33s: AI CLONED VOICE (Target: ~4 → 15 → 30 → 45 → 60 → 70 → 76 → 80)
  // Around 31-33s: natural fluctuation 78-82
  if (t < 33.0) {
    let score = 4;
    if (t < 18.0) {
      const p = (t - 16.0) / 2.0;
      score = Math.round(4 + p * 11); // 4 -> 15
    } else if (t < 20.0) {
      const p = (t - 18.0) / 2.0;
      score = Math.round(15 + p * 15); // 15 -> 30
    } else if (t < 22.0) {
      const p = (t - 20.0) / 2.0;
      score = Math.round(30 + p * 15); // 30 -> 45
    } else if (t < 24.0) {
      const p = (t - 22.0) / 2.0;
      score = Math.round(45 + p * 15); // 45 -> 60
    } else if (t < 26.0) {
      const p = (t - 24.0) / 2.0;
      score = Math.round(60 + p * 10); // 60 -> 70
    } else if (t < 28.0) {
      const p = (t - 26.0) / 2.0;
      score = Math.round(70 + p * 6); // 70 -> 76
    } else if (t < 30.0) {
      const p = (t - 28.0) / 2.0;
      score = Math.round(76 + p * 4); // 76 -> 80
    } else {
      // 30-33s: gentle realistic fluctuation around 78-82
      const sine = Math.sin((t - 30.0) * Math.PI * 2);
      score = Math.round(80 + sine * 1.5);
    }

    const state: RiskState = score >= 65 ? 'high' : score >= 40 ? 'suspicious' : 'low';
    return {
      targetScore: score,
      riskState: state,
      riskTrend: 'rising',
      sublabel: 'LIVE RISK',
    };
  }

  // 33s – 36s: SECOND SILENCE (Target: falls back to 0 – 1)
  if (t < 36.0) {
    const decayT = Math.min(1.0, (t - 33.0) / 2.5);
    const score = Math.max(0, Math.round(80 * Math.pow(1.0 - decayT, 2.5)));
    return {
      targetScore: score,
      riskState: 'low',
      riskTrend: 'falling',
      sublabel: 'NO VOICE',
    };
  }

  // 36s – 45.632s: AI-GENERATED VOICE (Target: ~3 → 20 → 40 → 60 → 75 → 85 → 92 → 96 → 99 → 100)
  if (t < DEMO_AUDIO_DURATION) {
    let score = 3;
    if (t < 37.0) {
      const p = (t - 36.0) / 1.0;
      score = Math.round(3 + p * 17); // 3 -> 20
    } else if (t < 38.5) {
      const p = (t - 37.0) / 1.5;
      score = Math.round(20 + p * 20); // 20 -> 40
    } else if (t < 40.0) {
      const p = (t - 38.5) / 1.5;
      score = Math.round(40 + p * 20); // 40 -> 60
    } else if (t < 41.5) {
      const p = (t - 40.0) / 1.5;
      score = Math.round(60 + p * 15); // 60 -> 75
    } else if (t < 43.0) {
      const p = (t - 41.5) / 1.5;
      score = Math.round(75 + p * 10); // 75 -> 85
    } else if (t < 44.0) {
      const p = (t - 43.0) / 1.0;
      score = Math.round(85 + p * 7); // 85 -> 92
    } else if (t < 44.8) {
      const p = (t - 44.0) / 0.8;
      score = Math.round(92 + p * 4); // 92 -> 96
    } else if (t < 45.3) {
      const p = (t - 44.8) / 0.5;
      score = Math.round(96 + p * 3); // 96 -> 99
    } else {
      score = 100;
    }

    const state: RiskState =
      score >= 85 ? 'critical' : score >= 65 ? 'high' : score >= 40 ? 'suspicious' : 'low';

    return {
      targetScore: Math.min(100, score),
      riskState: state,
      riskTrend: 'rising',
      sublabel: 'LIVE RISK',
    };
  }

  // 45.632s – 48.132s+: POST-AUDIO ENDED (Smooth decay from 100 -> 90 -> 75 -> 55 -> 35 -> 15 -> 5 -> 0 over ~2.5s)
  const elapsed = t - DEMO_AUDIO_DURATION;
  const decayProgress = Math.min(1.0, elapsed / DEMO_DECAY_DURATION);
  // Quadratic smooth decay: 100 * (1 - decayProgress)^1.8
  const score = Math.max(0, Math.round(100 * Math.pow(1.0 - decayProgress, 1.8)));

  const state: RiskState =
    score >= 85 ? 'critical' : score >= 65 ? 'high' : score >= 25 ? 'suspicious' : 'low';

  return {
    targetScore: score,
    riskState: state,
    riskTrend: score > 0 ? 'falling' : 'stable',
    sublabel: 'LIVE RISK',
  };
}

// ── 4. Waveform Data Lookup ──────────────────────────────────────────────────

export function getDemoWaveform(currentTime: number): {
  rms: number;
  bars: number[];
  isSilence: boolean;
} {
  const t = Math.max(0, currentTime);
  const phase = getDemoPhase(t);

  // Intentional silence intervals and post audio ended must strictly be flat line
  if (phase === 'SILENCE' || phase === 'POST_AUDIO_ENDED') {
    return {
      rms: 0.0,
      bars: new Array(36).fill(0.0),
      isSilence: true,
    };
  }

  // Lookup frame from precomputed 10fps acoustic spectrum
  const frameIndex = Math.min(
    DEMO_WAVEFORM_DATA.length - 1,
    Math.max(0, Math.floor(t * 10)),
  );
  const frame = DEMO_WAVEFORM_DATA[frameIndex];

  if (!frame || frame.rms < 0.005) {
    return {
      rms: 0.0,
      bars: new Array(36).fill(0.0),
      isSilence: true,
    };
  }

  return {
    rms: frame.rms,
    bars: frame.bars,
    isSilence: false,
  };
}

// ── 5. Full Multimodal Evidence Pipeline ─────────────────────────────────────

export function getDemoMultimodalState(
  currentTime: number,
  currentScore: number,
): DemoMultimodalState {
  const t = Math.max(0, currentTime);
  const phase = getDemoPhase(t);
  const txState = getDemoTranscript(t);

  // ── HUMAN PHASE (0 – 13s) ──────────────────────────────────────────────────
  if (phase === 'HUMAN') {
    return {
      authenticity: {
        score: Math.min(4, Math.max(1, currentScore)),
        spoof_probability: 0.03,
        acoustic_anomaly: 'LOW',
        spectral_anomaly: 'LOW',
        prosody_anomaly: 'LOW',
        label: 'GENUINE',
        model_version: 'AASIST-L (Local)',
        confidence: 0.94,
        spectral_score: 0.04,
        prosody_score: 0.02,
      },
      identity: {
        match_score: null,
        enrollment_status: 'NOT_ENROLLED',
        consistency: 'UNKNOWN',
        confidence: 0,
      },
      context: {
        score: 3,
        transcript: txState.transcript,
        transcript_model: txState.model,
        consequence: 'low',
        financial_request: false,
        otp_request: false,
        credential_request: false,
        sensitive_information_request: false,
        urgency: false,
        social_engineering: false,
        authority_claim: false,
      },
      warningBanner: {
        message: 'Voice appears authentic',
        subMessage: 'No significant synthetic-voice indicators detected',
        icon: '🛡',
        severity: 'safe',
      },
      decision: 'ALLOW',
      decisionReasons: ['Acoustic pattern genuine', 'Prosody natural'],
      recommendedAction: 'No action required. Voice is authentic.',
      evidenceConfidence: 0.94,
      challengeState: 'idle',
      verificationState: 'idle',
      consequenceLevel: 'low',
      threatSignals: ['None Detected'],
      detectedEvents: [],
    };
  }

  // ── FIRST SILENCE (13 – 16s) ───────────────────────────────────────────────
  if (t < 16.0) {
    return {
      authenticity: {
        score: 0,
        spoof_probability: 0.0,
        acoustic_anomaly: 'LOW',
        spectral_anomaly: 'LOW',
        prosody_anomaly: 'LOW',
        label: 'NO VOICE',
        model_version: 'AASIST-L (Local)',
        confidence: 0.5,
      },
      identity: {
        match_score: null,
        enrollment_status: 'NOT_ENROLLED',
        consistency: 'UNKNOWN',
        confidence: 0,
      },
      context: {
        score: 0,
        transcript: '',
        transcript_model: txState.model,
        consequence: 'low',
        financial_request: false,
        otp_request: false,
        credential_request: false,
        sensitive_information_request: false,
        urgency: false,
        social_engineering: false,
        authority_claim: false,
      },
      warningBanner: {
        message: 'No active voice signal',
        subMessage: 'Waiting for speech…',
        icon: '🎙',
        severity: 'info',
      },
      decision: 'ALLOW',
      decisionReasons: ['Waiting for speech signal'],
      recommendedAction: 'Listening for speech input…',
      evidenceConfidence: 0.5,
      challengeState: 'idle',
      verificationState: 'idle',
      consequenceLevel: 'low',
      threatSignals: ['None Detected'],
      detectedEvents: [],
    };
  }

  // ── AI CLONED PHASE (16 – 33s) ─────────────────────────────────────────────
  if (phase === 'AI_CLONED') {
    const isEscalated = currentScore >= 55;
    const isHigh = currentScore >= 70;

    const events: TimelineEntry[] = [];
    if (t >= 20.0) {
      events.push({
        id: 'ev-clone-1',
        label: 'Synthetic voice indicators detected',
        stream: 'authenticity',
        severity: 'warning',
        at: Date.now() - Math.round((t - 20.0) * 1000),
      });
    }
    if (t >= 25.5) {
      events.push({
        id: 'ev-clone-2',
        label: 'Security decision escalated to HOLD / VERIFY',
        stream: 'policy',
        severity: 'warning',
        at: Date.now() - Math.round((t - 25.5) * 1000),
      });
    }

    return {
      authenticity: {
        score: Math.min(85, Math.max(15, currentScore)),
        spoof_probability: Math.min(0.85, currentScore / 100),
        acoustic_anomaly: isEscalated ? 'HIGH' : 'MEDIUM',
        spectral_anomaly: 'HIGH',
        prosody_anomaly: isEscalated ? 'HIGH' : 'MEDIUM',
        label: 'SPOOF',
        model_version: 'AASIST-L (Local)',
        confidence: 0.88,
        spectral_score: 0.81,
        prosody_score: 0.74,
      },
      identity: {
        match_score: 38,
        enrollment_status: 'MISMATCH',
        consistency: 'VARIABLE',
        confidence: 0.82,
      },
      context: {
        score: Math.min(65, Math.max(25, currentScore - 15)),
        transcript: txState.transcript,
        transcript_model: txState.model,
        consequence: isEscalated ? 'medium' : 'low',
        financial_request: false,
        otp_request: false,
        credential_request: false,
        sensitive_information_request: false,
        urgency: false,
        social_engineering: false,
        authority_claim: false,
      },
      warningBanner: isEscalated
        ? {
            message: 'Synthetic voice indicators detected',
            subMessage: 'Acoustic patterns indicate artificial or cloned voice',
            icon: '⚠️',
            severity: 'warning',
          }
        : {
            message: 'Analyzing vocal characteristics…',
            subMessage: 'Evaluating acoustic & spectral consistency',
            icon: '🎙',
            severity: 'info',
          },
      decision: isHigh ? 'VERIFY' : isEscalated ? 'HOLD' : 'ALLOW',
      decisionReasons: [
        'Cloned voice high confidence',
        'Spectral artifact detected',
        'Speaker identity mismatch',
      ],
      recommendedAction:
        'Pause call. Request secondary channel verification before sharing information.',
      evidenceConfidence: 0.88,
      challengeState: isEscalated ? 'recommended' : 'idle',
      verificationState: isHigh ? 'recommended' : 'idle',
      consequenceLevel: isEscalated ? 'medium' : 'low',
      threatSignals: isEscalated ? ['Synthetic voice indicators detected'] : ['None Detected'],
      detectedEvents: events,
    };
  }

  // ── SECOND SILENCE (33 – 36s) ──────────────────────────────────────────────
  if (t < 36.0) {
    return {
      authenticity: {
        score: 0,
        spoof_probability: 0.0,
        acoustic_anomaly: 'LOW',
        spectral_anomaly: 'LOW',
        prosody_anomaly: 'LOW',
        label: 'NO VOICE',
        model_version: 'AASIST-L (Local)',
        confidence: 0.5,
      },
      identity: {
        match_score: null,
        enrollment_status: 'NOT_ENROLLED',
        consistency: 'UNKNOWN',
        confidence: 0,
      },
      context: {
        score: 0,
        transcript: '',
        transcript_model: txState.model,
        consequence: 'low',
        financial_request: false,
        otp_request: false,
        credential_request: false,
        sensitive_information_request: false,
        urgency: false,
        social_engineering: false,
        authority_claim: false,
      },
      warningBanner: {
        message: 'No active voice signal',
        subMessage: 'Waiting for speech…',
        icon: '🎙',
        severity: 'info',
      },
      decision: 'ALLOW',
      decisionReasons: ['Waiting for speech signal'],
      recommendedAction: 'Listening for speech input…',
      evidenceConfidence: 0.5,
      challengeState: 'idle',
      verificationState: 'idle',
      consequenceLevel: 'low',
      threatSignals: ['None Detected'],
      detectedEvents: [],
    };
  }

  // ── POST-AUDIO ENDED PHASE (t >= DEMO_AUDIO_DURATION) ───────────────────────
  if (phase === 'POST_AUDIO_ENDED') {
    const events: TimelineEntry[] = [
      {
        id: 'ev-ai-1',
        label: 'Synthetic voice indicators detected',
        stream: 'authenticity',
        severity: 'warning',
        at: Date.now() - Math.round((t - 20.0) * 1000),
      },
      {
        id: 'ev-ai-2',
        label: 'Security decision escalated to HOLD / VERIFY',
        stream: 'policy',
        severity: 'warning',
        at: Date.now() - Math.round((t - 25.5) * 1000),
      },
      {
        id: 'ev-ai-3',
        label: 'Critical synthetic voice signature detected',
        stream: 'authenticity',
        severity: 'critical',
        at: Date.now() - Math.round((t - 38.5) * 1000),
      },
      {
        id: 'ev-ai-4',
        label: 'Security decision escalated to BLOCKED',
        stream: 'policy',
        severity: 'critical',
        at: Date.now() - Math.round((t - 42.0) * 1000),
      },
    ];

    const isScoreCritical = currentScore >= 85;
    const isScoreHigh = currentScore >= 60;
    const isScoreSuspicious = currentScore >= 25;

    return {
      authenticity: {
        score: currentScore,
        spoof_probability: Math.min(1.0, currentScore / 100),
        acoustic_anomaly: isScoreHigh ? 'HIGH' : isScoreSuspicious ? 'MEDIUM' : 'LOW',
        spectral_anomaly: isScoreHigh ? 'HIGH' : isScoreSuspicious ? 'MEDIUM' : 'LOW',
        prosody_anomaly: isScoreHigh ? 'HIGH' : isScoreSuspicious ? 'MEDIUM' : 'LOW',
        label: isScoreSuspicious ? 'SPOOF' : 'GENUINE',
        model_version: 'AASIST-L (Local)',
        confidence: currentScore === 0 ? 0.95 : 0.99,
        spectral_score: Math.max(0.02, (currentScore / 100) * 0.98),
        prosody_score: Math.max(0.01, (currentScore / 100) * 0.95),
      },
      identity: {
        match_score: currentScore === 0 ? null : Math.round(11 + (100 - currentScore) * 0.6),
        enrollment_status: currentScore === 0 ? 'NOT_ENROLLED' : 'MISMATCH',
        consistency: currentScore === 0 ? 'UNKNOWN' : 'POOR',
        confidence: currentScore === 0 ? 0 : 0.96,
      },
      context: {
        score: Math.max(0, currentScore - 10),
        transcript: txState.transcript,
        transcript_model: txState.model,
        consequence: isScoreCritical ? 'critical' : isScoreHigh ? 'high' : 'low',
        financial_request: false,
        otp_request: false,
        credential_request: false,
        sensitive_information_request: false,
        urgency: false,
        social_engineering: false,
        authority_claim: false,
      },
      warningBanner: isScoreCritical
        ? {
            message: 'Critical synthetic-voice risk detected',
            subMessage: 'Do not share credentials or authorize transactions',
            icon: '🚨',
            severity: 'critical',
          }
        : isScoreHigh
        ? {
            message: 'High synthetic-voice risk detected',
            subMessage: 'Synthetic speech signature identified',
            icon: '⚠️',
            severity: 'warning',
          }
        : isScoreSuspicious
        ? {
            message: 'Suspicious voice activity decaying',
            subMessage: 'Acoustic patterns settling',
            icon: '⚡',
            severity: 'warning',
          }
        : {
            message: 'Voice stream completed',
            subMessage: 'All threat signals cleared · No active acoustic anomalies detected',
            icon: '🛡',
            severity: 'safe',
          },
      decision: isScoreCritical ? 'BLOCK' : isScoreHigh ? 'HOLD' : 'ALLOW',
      decisionReasons:
        currentScore < 25
          ? ['Stream ended · Voice signature settled', 'No active acoustic anomalies detected']
          : [
              'Neural TTS fingerprint decaying',
              'Spectral artifact cleared',
              'Synthetic voice signature resolved',
            ],
      recommendedAction:
        currentScore < 25
          ? 'Normal monitoring active. Voice stream completed.'
          : 'Do not authorize sensitive transactions. Initiate independent verification.',
      evidenceConfidence: 0.95,
      challengeState: isScoreHigh ? 'recommended' : 'idle',
      verificationState: isScoreCritical ? 'recommended' : 'idle',
      consequenceLevel: isScoreCritical ? 'critical' : isScoreHigh ? 'high' : 'low',
      threatSignals: currentScore < 25 ? ['None Detected'] : ['Synthetic voice indicators settling'],
      detectedEvents: events,
    };
  }

  // ── AI-GENERATED PHASE (36s – 45.632s) ─────────────────────────────────────
  const isHigh = currentScore >= 70;
  const isCritical = currentScore >= 88;

  const events: TimelineEntry[] = [
    {
      id: 'ev-ai-1',
      label: 'Synthetic voice indicators detected',
      stream: 'authenticity',
      severity: 'warning',
      at: Date.now() - Math.round((t - 20.0) * 1000),
    },
    {
      id: 'ev-ai-2',
      label: 'Security decision escalated to HOLD / VERIFY',
      stream: 'policy',
      severity: 'warning',
      at: Date.now() - Math.round((t - 25.5) * 1000),
    },
  ];

  if (t >= 38.5) {
    events.push({
      id: 'ev-ai-3',
      label: 'Critical synthetic voice signature detected',
      stream: 'authenticity',
      severity: 'critical',
      at: Date.now() - Math.round((t - 38.5) * 1000),
    });
  }
  if (t >= 42.0) {
    events.push({
      id: 'ev-ai-4',
      label: 'Security decision escalated to BLOCKED',
      stream: 'policy',
      severity: 'critical',
      at: Date.now() - Math.round((t - 42.0) * 1000),
    });
  }

  return {
    authenticity: {
      score: Math.min(100, Math.max(20, currentScore)),
      spoof_probability: Math.min(1.0, currentScore / 100),
      acoustic_anomaly: 'HIGH',
      spectral_anomaly: 'HIGH',
      prosody_anomaly: 'HIGH',
      label: 'SPOOF',
      model_version: 'AASIST-L (Local)',
      confidence: 0.99,
      spectral_score: 0.98,
      prosody_score: 0.95,
    },
    identity: {
      match_score: 11,
      enrollment_status: 'MISMATCH',
      consistency: 'POOR',
      confidence: 0.96,
    },
    context: {
      score: Math.min(95, Math.max(30, currentScore - 5)),
      transcript: txState.transcript,
      transcript_model: txState.model,
      consequence: isCritical ? 'critical' : 'high',
      financial_request: false,
      otp_request: false,
      credential_request: false,
      sensitive_information_request: false,
      urgency: false,
      social_engineering: false,
      authority_claim: false,
    },
    warningBanner: isCritical
      ? {
          message: 'Critical synthetic-voice risk detected',
          subMessage: 'Do not share credentials or authorize transactions',
          icon: '🚨',
          severity: 'critical',
        }
      : isHigh
      ? {
          message: 'High synthetic-voice risk detected',
          subMessage: 'Synthetic speech signature identified',
          icon: '⚠️',
          severity: 'warning',
        }
      : {
          message: 'Analyzing vocal characteristics…',
          subMessage: 'Evaluating acoustic & spectral consistency',
          icon: '🎙',
          severity: 'info',
        },
    decision: isCritical ? 'BLOCK' : isHigh ? 'HOLD' : 'ALLOW',
    decisionReasons: [
      'Neural TTS fingerprint detected',
      'Spectral artifact detected',
      'Phase inconsistency detected',
      'Synthetic voice signature detected',
    ],
    recommendedAction:
      'Do not authorize sensitive transactions. Initiate independent verification.',
    evidenceConfidence: 0.99,
    challengeState: 'recommended',
    verificationState: 'recommended',
    consequenceLevel: isCritical ? 'critical' : 'high',
    threatSignals: [
      'Synthetic voice / neural TTS indicators detected',
      'Phase inconsistency signature',
    ],
    detectedEvents: events,
  };
}
