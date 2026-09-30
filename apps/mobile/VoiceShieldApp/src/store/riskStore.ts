import { create } from 'zustand';
import {
  AudioQualityEvidence,
  AuthenticityEvidence,
  ChallengeState,
  ContextEvidence,
  DashboardAlert,
  Decision,
  IdentityEvidence,
  PipelineMode,
  RiskObservation,
  RiskState,
  RiskTrend,
  SessionStatus,
  TimelineEntry,
  VerificationState,
  WSEvent,
} from '../types';

/**
 * Live security dashboard state.
 *
 * The backend is authoritative: this store never computes a risk score, it only
 * records what arrived. Every WebSocket event is funnelled through `applyEvent`,
 * which is a pure-ish reducer so it can be unit-tested without a socket.
 *
 * Edge cases handled here (see __tests__/riskStore.test.ts):
 *   - duplicate events        → dropped by event_id
 *   - out-of-order / stale    → dropped by seq
 *   - malformed / missing     → ignored, never throws
 *   - unknown event types     → ignored
 *   - reconnects              → seq resets are tolerated
 *   - session end / new call  → `reset()` clears everything
 */

/** Bounded history for the live risk graph (~2 minutes at 1 obs/sec). */
export const MAX_HISTORY = 120;
const MAX_TIMELINE = 100;
const MAX_ALERTS = 20;
/** Ring buffer of recently seen event ids, for de-duplication. */
const MAX_SEEN_IDS = 400;

export interface RiskStoreState {
  // ── Overall security ───────────────────────────────────────────────────────
  riskScore: number;
  riskState: RiskState;
  riskTrend: RiskTrend;
  riskHistory: RiskObservation[];
  evidenceConfidence: number;

  // ── Evidence streams (independent) ─────────────────────────────────────────
  authenticity: AuthenticityEvidence | null;
  identity: IdentityEvidence | null;
  context: ContextEvidence | null;
  audioQuality: AudioQualityEvidence | null;
  audioActive: boolean;

  // ── Decision ───────────────────────────────────────────────────────────────
  decision: Decision;
  decisionReasons: string[];
  recommendedAction: string;
  consequence: string;

  // ── Timeline & alerts ──────────────────────────────────────────────────────
  detectedEvents: TimelineEntry[];
  preTransactionWarning: boolean;
  recommendedActions: string[];
  evidence: Record<string, any> | null;
  callSource: string;
  alerts: DashboardAlert[];

  // ── Interactive verification ───────────────────────────────────────────────
  challengeState: ChallengeState;
  challengeId: string | null;
  challengeText: string | null;
  verificationState: VerificationState;
  verificationId: string | null;
  verificationMethod: string | null;

  // ── Session ────────────────────────────────────────────────────────────────
  sessionStatus: SessionStatus;
  sessionId: string | null;
  pipelineMode: PipelineMode;
  modelVersions: Record<string, string>;
  incidentId: string | null;
  lastUpdated: number | null;
  lastError: string | null;

  // ── Internal bookkeeping ───────────────────────────────────────────────────
  lastSeq: number;
  seenEventIds: string[];

  // ── Actions ────────────────────────────────────────────────────────────────
  applyEvent: (event: unknown) => void;
  setSessionStatus: (status: SessionStatus) => void;
  dismissAlert: (id: string) => void;
  reset: () => void;
}

const initialState = {
  riskScore: 0,
  riskState: 'insufficient_evidence' as RiskState,
  riskTrend: 'stable' as RiskTrend,
  riskHistory: [] as RiskObservation[],
  evidenceConfidence: 0,

  authenticity: null,
  identity: null,
  context: null,
  audioQuality: null,
  audioActive: false,

  decision: 'ALLOW' as Decision,
  decisionReasons: [] as string[],
  recommendedAction: '',
  consequence: 'low',

  detectedEvents: [] as TimelineEntry[],
  preTransactionWarning: false,
  recommendedActions: [] as string[],
  evidence: null as Record<string, any> | null,
  callSource: 'DEVICE_MICROPHONE',
  alerts: [] as DashboardAlert[],

  challengeState: 'idle' as ChallengeState,
  challengeId: null,
  challengeText: null,
  verificationState: 'idle' as VerificationState,
  verificationId: null,
  verificationMethod: null,

  sessionStatus: 'idle' as SessionStatus,
  sessionId: null,
  pipelineMode: 'mock' as PipelineMode,
  modelVersions: {} as Record<string, string>,
  incidentId: null,
  lastUpdated: null,
  lastError: null,

  lastSeq: 0,
  seenEventIds: [] as string[],
};

// ── Guards ────────────────────────────────────────────────────────────────────

const isObject = (v: unknown): v is Record<string, any> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const num = (v: unknown, fallback = 0): number =>
  typeof v === 'number' && Number.isFinite(v) ? v : fallback;

const str = (v: unknown, fallback = ''): string =>
  typeof v === 'string' ? v : fallback;

const strArray = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [];

/** Parse an ISO timestamp, falling back to now for malformed values. */
const parseAt = (v: unknown): number => {
  const parsed = typeof v === 'string' ? Date.parse(v) : NaN;
  return Number.isNaN(parsed) ? Date.now() : parsed;
};

export const useRiskStore = create<RiskStoreState>((set, get) => ({
  ...initialState,

  applyEvent: (raw: unknown) => {
    // ── Malformed: never let one bad event break the dashboard ──────────────
    if (!isObject(raw) || typeof raw.type !== 'string') {
      return;
    }
    const event = raw as WSEvent & Record<string, any>;

    // `pong` carries no envelope and needs no state change.
    if (event.type === 'pong') {
      return;
    }

    const state = get();

    // ── Duplicate suppression ───────────────────────────────────────────────
    const eventId = str(event.event_id);
    if (eventId && state.seenEventIds.includes(eventId)) {
      return;
    }

    // ── Ordering: drop stale events, tolerate a reconnect's seq reset ───────
    const seq = num(event.seq, 0);
    if (seq > 0 && seq <= state.lastSeq) {
      // A far-lower seq means the server restarted the sequence (new socket),
      // which is legitimate; a slightly-lower one is a genuinely late event.
      const isSequenceRestart = seq === 1;
      if (!isSequenceRestart) {
        return;
      }
    }

    // Freeze display once session has ended: drop late risk/quality updates
    if (state.sessionStatus === 'ended' && event.type !== 'session_started') {
      return;
    }

    const patch: Partial<RiskStoreState> = {};
    if (eventId) {
      patch.seenEventIds = [...state.seenEventIds, eventId].slice(-MAX_SEEN_IDS);
    }
    if (seq > 0) {
      patch.lastSeq = seq;
    }
    const at = parseAt(event.timestamp);
    patch.lastUpdated = at;

    switch (event.type) {
      // ── Session lifecycle ────────────────────────────────────────────────
      case 'session_started': {
        patch.sessionId = str(event.session_id) || state.sessionId;
        patch.sessionStatus = 'monitoring';
        patch.pipelineMode = event.pipeline_mode === 'live' ? 'live' : 'mock';
        patch.modelVersions = isObject(event.model_versions)
          ? event.model_versions
          : {};
        break;
      }

      case 'session_ended': {
        patch.sessionStatus = 'ended';
        patch.incidentId = str(event.incident_id) || null;
        break;
      }

      // ── Audio / channel quality ──────────────────────────────────────────
      case 'audio_quality': {
        if (isObject(event.audio)) {
          patch.audioQuality = event.audio as AudioQualityEvidence;
        }
        patch.audioActive = event.active === true;
        break;
      }

      // ── Real-time streaming STT transcript update (Deepgram / Whisper) ────
      case 'transcript_update': {
        const text = str(event.transcript);
        const currentCtx = state.context || {
          score: 0,
          confidence: 0,
          urgency: false,
          financial_request: false,
          otp_request: false,
          credential_request: false,
          sensitive_information_request: false,
          social_engineering: false,
          authority_claim: false,
          consequence: 'low',
          transcript: '',
          detected_phrases: [],
          model_version: 'stt-v1',
          is_mock: false,
          transcript_is_mock: false,
        };
        patch.context = {
          ...currentCtx,
          transcript: text,
          transcript_model: str(event.transcript_model, currentCtx.transcript_model || 'Deepgram Nova-2'),
          transcript_language: str(event.language, currentCtx.transcript_language || 'en'),
        };
        break;
      }

      // ── The primary dashboard event ──────────────────────────────────────
      case 'risk_update': {
        const score = num(event.risk_score, state.riskScore);
        const riskState = str(event.risk_state, state.riskState) as RiskState;

        patch.riskScore = score;
        patch.riskState = riskState;
        patch.riskTrend = str(event.risk_trend, 'stable') as RiskTrend;
        patch.evidenceConfidence = num(event.evidence_confidence, 0);
        patch.riskHistory = [
          ...state.riskHistory,
          { score, state: riskState, at },
        ].slice(-MAX_HISTORY);

        // Each stream is replaced only when this event actually carried it, so
        // a partial update never wipes an unrelated panel.
        if (isObject(event.authenticity)) {
          patch.authenticity = event.authenticity as AuthenticityEvidence;
        }
        if (isObject(event.identity)) {
          patch.identity = event.identity as IdentityEvidence;
        }
        if (isObject(event.context)) {
          patch.context = event.context as ContextEvidence;
        }

        patch.decision = str(event.decision, state.decision) as Decision;
        patch.decisionReasons = strArray(event.reasons);
        patch.consequence = str(event.consequence, state.consequence);
        if (event.pipeline_mode === 'live' || event.pipeline_mode === 'mock') {
          patch.pipelineMode = event.pipeline_mode;
        }
        if (event.pre_transaction_warning !== undefined) {
          patch.preTransactionWarning = Boolean(event.pre_transaction_warning);
        }
        if (Array.isArray(event.recommended_actions)) {
          patch.recommendedActions = event.recommended_actions;
        }
        if (event.evidence) {
          patch.evidence = event.evidence;
        }
        if (event.call_source) {
          patch.callSource = event.call_source;
        }
        break;
      }

      // ── Timeline ─────────────────────────────────────────────────────────
      case 'detected_event': {
        const entry: TimelineEntry = {
          id: eventId || `${seq}-${at}`,
          label: str(event.label, str(event.code, 'Event')),
          stream: str(event.stream, 'risk') as TimelineEntry['stream'],
          severity: str(event.severity, 'info') as TimelineEntry['severity'],
          at,
        };
        patch.detectedEvents = [entry, ...state.detectedEvents].slice(0, MAX_TIMELINE);
        break;
      }

      case 'alert': {
        const alert: DashboardAlert = {
          id: eventId || `${seq}-${at}`,
          severity: str(event.severity, 'high') as DashboardAlert['severity'],
          message: str(event.message, 'Elevated risk detected'),
          recommendedAction: str(event.recommended_action),
          at,
        };
        patch.alerts = [alert, ...state.alerts].slice(0, MAX_ALERTS);
        break;
      }

      // ── Policy ───────────────────────────────────────────────────────────
      case 'policy_decision': {
        patch.decision = str(event.decision, state.decision) as Decision;
        patch.decisionReasons = strArray(event.reasons);
        patch.recommendedAction = str(event.recommended_action);
        break;
      }

      // ── Challenge ────────────────────────────────────────────────────────
      case 'challenge_started': {
        patch.challengeState = 'started';
        patch.challengeId = str(event.challenge_id) || null;
        patch.challengeText = str(event.challenge_text) || null;
        break;
      }

      case 'challenge_result': {
        const outcome = str(event.outcome);
        patch.challengeState = (
          outcome === 'passed' || outcome === 'failed' || outcome === 'timeout'
            ? outcome
            : 'idle'
        ) as ChallengeState;
        break;
      }

      // ── Independent verification ─────────────────────────────────────────
      case 'verification_requested': {
        patch.verificationState = 'requested';
        patch.verificationId = str(event.verification_id) || null;
        patch.verificationMethod = str(event.method) || null;
        break;
      }

      case 'verification_result': {
        const outcome = str(event.outcome);
        patch.verificationState = (
          outcome === 'approved' || outcome === 'rejected' || outcome === 'timeout'
            ? outcome
            : 'idle'
        ) as VerificationState;
        break;
      }

      case 'error': {
        patch.lastError = str(event.detail, 'Unknown error');
        break;
      }

      // ── Unknown types are ignored, not fatal ─────────────────────────────
      default:
        return;
    }

    set(patch as RiskStoreState);
  },

  setSessionStatus: (status) => set({ sessionStatus: status }),

  dismissAlert: (id) =>
    set(state => ({ alerts: state.alerts.filter(a => a.id !== id) })),

  reset: () => set({ ...initialState, riskHistory: [], detectedEvents: [], alerts: [], seenEventIds: [] }),
}));
