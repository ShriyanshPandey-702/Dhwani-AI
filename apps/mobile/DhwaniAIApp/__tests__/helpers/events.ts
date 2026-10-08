import {
  AlertEvent, AudioQualityEvent, ChallengeResultEvent, ChallengeStartedEvent,
  DetectedEvent, PolicyDecisionEvent, RiskUpdateEvent, SessionStartedEvent,
  VerificationRequestedEvent, VerificationResultEvent,
} from '../../src/types';

let seq = 0;
let id = 0;

export const resetEventCounters = () => {
  seq = 0;
  id = 0;
};

const envelope = (overrides: { seq?: number; event_id?: string } = {}) => {
  const nextSeq = overrides.seq ?? ++seq;
  return {
    event_id: overrides.event_id ?? `evt-${++id}`,
    seq: nextSeq,
    session_id: 'sess-test',
    timestamp: new Date(1_700_000_000_000 + nextSeq * 1000).toISOString(),
  };
};

export const sessionStarted = (
  overrides: Partial<SessionStartedEvent> = {},
): SessionStartedEvent => ({
  type: 'session_started',
  ...envelope(overrides),
  pipeline_mode: 'mock',
  model_versions: { authenticity: 'stub-v0.2' },
  ...overrides,
});

export const riskUpdate = (
  overrides: Partial<RiskUpdateEvent> = {},
): RiskUpdateEvent => ({
  type: 'risk_update',
  ...envelope(overrides),
  risk_score: 42,
  risk_state: 'suspicious',
  risk_trend: 'rising',
  evidence_confidence: 0.6,
  authenticity: {
    score: 40, spoof_probability: 0.4, confidence: 0.6,
    acoustic_anomaly: 'MEDIUM', spectral_anomaly: 'LOW', prosody_anomaly: 'MEDIUM',
    model_version: 'stub-v0.2', is_mock: true,
  },
  identity: {
    match_score: 82, confidence: 0.7, consistency: 'GOOD',
    enrollment_status: 'VERIFIED', model_version: 'stub-v0.2', is_mock: true,
  },
  context: {
    score: 30, confidence: 0.5, urgency: true, financial_request: false,
    otp_request: false, credential_request: false,
    sensitive_information_request: false, social_engineering: false,
    authority_claim: true, consequence: 'medium', transcript: 'hello',
    detected_phrases: ['urgent'], model_version: 'rules-v0.2',
    is_mock: false, transcript_is_mock: true,
  },
  decision: 'VERIFY',
  reasons: ['suspicious_conversation_context'],
  consequence: 'medium',
  contributions: { authenticity: 20, identity: 4.5, context: 7.5 },
  pipeline_mode: 'mock',
  ...overrides,
});

export const detectedEvent = (
  overrides: Partial<DetectedEvent> = {},
): DetectedEvent => ({
  type: 'detected_event',
  ...envelope(overrides),
  code: 'otp_request',
  label: 'OTP request detected',
  stream: 'context',
  severity: 'critical',
  ...overrides,
});

export const alertEvent = (overrides: Partial<AlertEvent> = {}): AlertEvent => ({
  type: 'alert',
  ...envelope(overrides),
  severity: 'high',
  message: 'Elevated risk detected on this call.',
  recommended_action: 'Independent verification',
  ...overrides,
});

export const audioQuality = (
  overrides: Partial<AudioQualityEvent> = {},
): AudioQualityEvent => ({
  type: 'audio_quality',
  ...envelope(overrides),
  active: true,
  audio: {
    level_db: -18, estimated_snr_db: 30, clipping_ratio: 0,
    is_silent: false, quality: 'GOOD', sample_rate: 16000, duration_ms: 1000,
  },
  ...overrides,
});

export const policyDecision = (
  overrides: Partial<PolicyDecisionEvent> = {},
): PolicyDecisionEvent => ({
  type: 'policy_decision',
  ...envelope(overrides),
  decision: 'HOLD',
  action: 'hold',
  reasons: ['high_consequence_request'],
  recommended_action: 'Hold the transaction and verify out-of-band',
  risk_state: 'critical',
  risk_score: 90,
  ...overrides,
});

export const challengeStarted = (
  overrides: Partial<ChallengeStartedEvent> = {},
): ChallengeStartedEvent => ({
  type: 'challenge_started',
  ...envelope(overrides),
  challenge_id: 'ch-1',
  challenge_text: 'Please say your full name clearly.',
  challenge_type: 'phrase',
  ...overrides,
});

export const challengeResult = (
  overrides: Partial<ChallengeResultEvent> = {},
): ChallengeResultEvent => ({
  type: 'challenge_result',
  ...envelope(overrides),
  challenge_id: 'ch-1',
  outcome: 'failed',
  detail: '',
  ...overrides,
});

export const verificationRequested = (
  overrides: Partial<VerificationRequestedEvent> = {},
): VerificationRequestedEvent => ({
  type: 'verification_requested',
  ...envelope(overrides),
  verification_id: 'v-1',
  method: 'trusted_device',
  expires_at: new Date(1_700_000_120_000).toISOString(),
  ...overrides,
});

export const verificationResult = (
  overrides: Partial<VerificationResultEvent> = {},
): VerificationResultEvent => ({
  type: 'verification_result',
  ...envelope(overrides),
  verification_id: 'v-1',
  outcome: 'approved',
  method: 'trusted_device',
  ...overrides,
});
