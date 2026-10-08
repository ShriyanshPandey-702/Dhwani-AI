// Dhwani AI type definitions.
//
// The WebSocket section mirrors services/api/app/websocket/events.py exactly.
// Every server event carries type/event_id/seq/session_id/timestamp; the store
// uses `event_id` for de-duplication and `seq` for ordering.

// ── Risk & policy ─────────────────────────────────────────────────────────────

export type RiskState =
  | 'insufficient_evidence'
  | 'low'
  | 'suspicious'
  | 'high'
  | 'critical';

export type RiskTrend = 'rising' | 'falling' | 'stable';

export type PolicyAction =
  | 'allow'
  | 'challenge'
  | 'verify'
  | 'hold'
  | 'block'
  | 'escalate';

export type Decision = 'ALLOW' | 'VERIFY' | 'HOLD' | 'BLOCK' | 'ESCALATE';

export type ConsequenceLevel = 'low' | 'medium' | 'high' | 'critical';

export type AnomalyBand = 'LOW' | 'MEDIUM' | 'HIGH';

/**
 * Which code produced an evidence observation. Distinct from the session-level
 * `PipelineMode` below, which describes the audio *source*.
 *   real_ml            - a trained model ran
 *   heuristic_demo     - deterministic demo backend, deliberately selected
 *   heuristic_fallback - real ML was requested but unavailable
 */
export type InferenceMode = 'real_ml' | 'heuristic_demo' | 'heuristic_fallback';

/** "mock" = synthetic demo audio; "live" = audio streamed from the device. */
export type PipelineMode = 'mock' | 'live';

// ── Evidence streams (kept structurally separate on purpose) ──────────────────

export interface PitchEvidence {
  mean_f0_hz?: number | null;
  f0_std_hz?: number | null;
  f0_variance?: number | null;
  f0_min_hz?: number | null;
  f0_max_hz?: number | null;
  voiced_frame_ratio?: number | null;
}

export interface ProsodyEvidence {
  mean_f0_hz?: number | null;
  f0_std_hz?: number | null;
  f0_min_hz?: number | null;
  f0_max_hz?: number | null;
  pitch_variability?: number | null;
  energy_variability?: number | null;
  voiced_ratio?: number | null;
  speech_segment_count?: number | null;
  average_speech_duration_ms?: number | null;
  average_pause_duration_ms?: number | null;
  longest_pause_duration_ms?: number | null;
  pause_ratio?: number | null;
  note?: string;
}

export interface RhythmEvidence {
  speech_segment_count?: number | null;
  total_speech_duration_ms?: number | null;
  average_speech_duration_ms?: number | null;
  speech_to_pause_ratio?: number | null;
}

export interface PauseEvidence {
  pause_count?: number | null;
  total_pause_duration_ms?: number | null;
  average_pause_duration_ms?: number | null;
  longest_pause_duration_ms?: number | null;
  pause_to_speech_ratio?: number | null;
}

export interface MicrovariationEvidence {
  energy_variability?: number | null;
  zcr_variability?: number | null;
  spectral_variability?: number | null;
  f0_variability?: number | null;
  jitter_shimmer_status?: string;
}

export interface SpectralDetailsEvidence {
  centroid_hz?: number | null;
  flatness?: number | null;
  spectral_anomaly?: AnomalyBand;
}

export interface AuthenticityEvidence {
  score: number;                 // 0–100
  spoof_probability: number;     // 0.0–1.0
  confidence: number;            // 0.0–1.0
  acoustic_anomaly: AnomalyBand;
  spectral_anomaly: AnomalyBand;
  prosody_anomaly: AnomalyBand;
  model_version: string;
  is_mock: boolean;
  model_name?: string;
  pipeline_mode?: InferenceMode;
  inference_ms?: number;
  device?: string;
  calibrated_spoof_probability?: number | null;
  calibration_method?: string | null;
  calibration_version?: string | null;
  pitch?: PitchEvidence | null;
  prosody?: ProsodyEvidence | null;
  rhythm?: RhythmEvidence | null;
  pause_analysis?: PauseEvidence | null;
  microvariation?: MicrovariationEvidence | null;
  spectral_details?: SpectralDetailsEvidence | null;
}

export interface IdentityEvidence {
  match_score: number;           // 0–100
  confidence: number;
  consistency: 'GOOD' | 'VARIABLE' | 'POOR' | 'UNKNOWN';
  enrollment_status: 'NOT_ENROLLED' | 'ENROLLED' | 'VERIFIED' | 'MISMATCH' | 'SELF_CONSISTENCY';
  model_version: string;
  is_mock: boolean;
  model_name?: string;
  pipeline_mode?: InferenceMode;
  /** Raw cosine similarity. The embedding itself is never sent to the client. */
  similarity?: number;
  inference_ms?: number;
  reference_available?: boolean;
  comparison_available?: boolean;
}


export interface ContextEvidence {
  score: number;                 // 0–100
  confidence: number;
  urgency: boolean;
  financial_request: boolean;
  otp_request: boolean;
  credential_request: boolean;
  sensitive_information_request: boolean;
  social_engineering: boolean;
  authority_claim: boolean;
  consequence: ConsequenceLevel;
  transcript: string;
  detected_phrases: string[];
  categories?: string[];
  pre_transaction_warning?: boolean;
  recommended_actions?: string[];
  model_version: string;
  is_mock: boolean;
  transcript_is_mock: boolean;
  transcript_model?: string;
  transcript_pipeline_mode?: InferenceMode;
  transcript_language?: string;
  transcript_confidence?: number;
}

export interface AudioQualityEvidence {
  level_db: number;
  estimated_snr_db: number;
  clipping_ratio: number;
  is_silent: boolean;
  quality: 'GOOD' | 'FAIR' | 'POOR';
  sample_rate: number;
  duration_ms: number;
  rms?: number;
  energy_variance?: number;
  zcr?: number;
}

export interface SystemCapabilities {
  telephony: {
    cellular_metadata: string;
    cellular_audio: string;
    voip_media: string;
  };
  api: {
    rest: string;
    websocket: string;
  };
  alerts: {
    in_app: string;
    push: string;
    email: string;
    sms: string;
  };
  language: {
    transcription: string;
    threat_semantics: string;
  };
  enterprise: {
    api_ready: boolean;
    multi_tenant: boolean;
    sso: boolean;
  };
  privacy: {
    raw_audio_retained: boolean;
    features_logged_only: boolean;
    embeddings_protected: boolean;
    processing_location: string;
  };
}

// ── WebSocket events ──────────────────────────────────────────────────────────

export interface EventEnvelope {
  event_id: string;
  seq: number;
  session_id: string;
  timestamp: string;             // ISO-8601 UTC
}

export interface SessionStartedEvent extends EventEnvelope {
  type: 'session_started';
  pipeline_mode: PipelineMode;
  model_versions: Record<string, string>;
}

export interface AudioQualityEvent extends EventEnvelope {
  type: 'audio_quality';
  active: boolean;
  audio: AudioQualityEvidence;
}

export interface RiskUpdateEvent extends EventEnvelope {
  type: 'risk_update';
  risk_score: number;            // 0–100
  risk_state: RiskState;
  risk_trend: RiskTrend;
  evidence_confidence: number;
  authenticity: AuthenticityEvidence | null;
  identity: IdentityEvidence | null;
  context: ContextEvidence | null;
  decision: Decision;
  reasons: string[];
  consequence: ConsequenceLevel;
  contributions: Record<string, number>;
  pipeline_mode: PipelineMode;
  evidence?: Record<string, any> | null;
  pre_transaction_warning?: boolean;
  recommended_actions?: string[];
  call_source?: string;
}

export type EventStream =
  | 'authenticity'
  | 'identity'
  | 'context'
  | 'risk'
  | 'policy'
  | 'session';

export type EventSeverity = 'info' | 'warning' | 'critical';

export interface DetectedEvent extends EventEnvelope {
  type: 'detected_event';
  code: string;
  label: string;
  stream: EventStream;
  severity: EventSeverity;
}

export interface AlertEvent extends EventEnvelope {
  type: 'alert';
  severity: 'suspicious' | 'high' | 'critical';
  message: string;
  recommended_action: string;
}

export interface ChallengeStartedEvent extends EventEnvelope {
  type: 'challenge_started';
  challenge_id: string;
  challenge_text: string;
  challenge_type: string;
}

export interface ChallengeResultEvent extends EventEnvelope {
  type: 'challenge_result';
  challenge_id: string;
  outcome: 'passed' | 'failed' | 'timeout';
  detail: string;
}

export interface VerificationRequestedEvent extends EventEnvelope {
  type: 'verification_requested';
  verification_id: string;
  method: string;
  expires_at: string;
}

export interface VerificationResultEvent extends EventEnvelope {
  type: 'verification_result';
  verification_id: string;
  outcome: 'approved' | 'rejected' | 'timeout';
  method: string;
}

export interface PolicyDecisionEvent extends EventEnvelope {
  type: 'policy_decision';
  decision: Decision;
  action: PolicyAction;
  reasons: string[];
  recommended_action: string;
  risk_state: RiskState;
  risk_score: number;
}

export interface SessionEndedEvent extends EventEnvelope {
  type: 'session_ended';
  reason: string;
  peak_risk_score: number;
  peak_risk_state: RiskState;
  incident_id: string | null;
}

export interface ErrorEvent extends EventEnvelope {
  type: 'error';
  detail: string;
  code: string;
}

export interface TranscriptUpdateEvent extends EventEnvelope {
  type: 'transcript_update';
  transcript: string;
  is_final: boolean;
  speech_final?: boolean;
  confidence?: number;
  provider?: string;
  transcript_model?: string;
  language?: string;
}

export interface PongEvent {
  type: 'pong';
  timestamp: number;
}

export type WSEvent =
  | SessionStartedEvent
  | AudioQualityEvent
  | RiskUpdateEvent
  | DetectedEvent
  | AlertEvent
  | ChallengeStartedEvent
  | ChallengeResultEvent
  | VerificationRequestedEvent
  | VerificationResultEvent
  | PolicyDecisionEvent
  | SessionEndedEvent
  | TranscriptUpdateEvent
  | ErrorEvent
  | PongEvent;

// ── Local dashboard view models ───────────────────────────────────────────────

export interface RiskObservation {
  score: number;
  state: RiskState;
  /** Milliseconds since epoch, parsed from the event timestamp. */
  at: number;
}

export interface TimelineEntry {
  id: string;
  label: string;
  stream: EventStream;
  severity: EventSeverity;
  at: number;
}

export interface DashboardAlert {
  id: string;
  severity: 'suspicious' | 'high' | 'critical';
  message: string;
  recommendedAction: string;
  at: number;
}

export type ChallengeState =
  | 'idle'
  | 'started'
  | 'passed'
  | 'failed'
  | 'timeout';

export type VerificationState =
  | 'idle'
  | 'requested'
  | 'approved'
  | 'rejected'
  | 'timeout';

export type SessionStatus =
  | 'idle'
  | 'connecting'
  | 'monitoring'
  | 'reconnecting'
  | 'ended'
  | 'error';

// ── REST API types ────────────────────────────────────────────────────────────

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
}

export interface SessionData {
  id: string;
  state: 'created' | 'active' | 'ended' | 'error';
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
}

export interface IncidentSummary {
  id: string;
  session_id: string;
  final_state: string;
  peak_risk_score: number | null;
  peak_risk_state: string | null;
  action_taken: string | null;
  created_at: string;
  source?: string | null;
  caller_name?: string | null;
  caller_number?: string | null;
  contact_status?: string | null;
  filename?: string | null;
}

export interface IncidentDetail extends IncidentSummary {
  verification_outcome: string | null;
  evidence_summary: Record<string, unknown>;
  integrity_hash: string;
  policy_version: string;
  model_versions: Record<string, string>;
}

export interface OverviewStats {
  total_calls_today: number;
  safe_calls: number;
  suspicious_calls: number;
  high_critical_calls: number;
  hold_calls?: number;
  active_alerts: number;
  average_risk: number;
  recent: IncidentSummary[];
  has_data: boolean;
}

export interface DeviceData {
  id: string;
  device_name: string;
  platform: string;
  is_active: boolean;
  registered_at: string;
}

export interface ChallengeData {
  id: string;
  session_id: string;
  challenge_text: string;
  challenge_type: string;
  state: string;
  created_at: string;
}

export interface VerificationData {
  id: string;
  session_id: string;
  method: string;
  state: string;
  expires_at: string;
  nonce: string;
}
