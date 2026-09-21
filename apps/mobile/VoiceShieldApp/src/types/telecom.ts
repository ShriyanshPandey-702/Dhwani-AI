/**
 * Telecom Call Screening types for VoiceShield.
 * Represents metadata-only signals from Android Telecom CallScreeningService.
 */

export type ScreeningDecision = 'ALLOW' | 'SILENCE' | 'REJECT';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

/** UI-facing risk display state — directly maps to RiskStateBadge states. */
export type RiskState = 'safe' | 'low' | 'suspicious' | 'high' | 'critical';

export type CallerVerificationStatus = 'PASSED' | 'FAILED' | 'NOT_VERIFIED' | 'UNKNOWN';

export type WarningType =
  | 'NONE'
  | 'UNVERIFIED_CALLER'
  | 'VERIFICATION_FAILED'
  | 'RESTRICTED_NUMBER'
  | 'BLOCKLIST_MATCH';

export type ContactStatus = 'IN_CONTACTS' | 'NOT_IN_CONTACTS' | 'UNKNOWN';

export type AudioAnalysisStatus = 'NOT_PERFORMED' | 'PERFORMED' | 'FAILED';

export interface ScreenedCallEvent {
  eventId: string;
  timestamp: number;
  /** Privacy-masked caller number (e.g. "+91 ***** *3210") */
  callerMasked: string;
  /** Display name from device contacts, null if not in contacts or permission absent */
  callerName: string | null;
  callerHash: string;
  /** Whether caller is in device contacts */
  contactStatus: ContactStatus;
  verificationStatus: CallerVerificationStatus;
  /** Numeric risk score 0–100 */
  riskScore: number;
  /** UI-facing risk state for badge display */
  riskState: RiskState;
  decision: ScreeningDecision;
  riskLevel: RiskLevel;
  warningType: WarningType;
  category: string;
  /** Human-readable explanation of why this risk level was assigned */
  explanation: string;
  reasonCodes: string[];
  /** Measured screening latency in milliseconds */
  screeningLatencyMs: number;
  source: string;
  /** Whether ML audio analysis was performed (always NOT_PERFORMED for SIM calls in Phase 3) */
  audioAnalysisStatus: AudioAnalysisStatus;
}

export interface CallScreeningRoleResult {
  granted: boolean;
  alreadyHeld: boolean;
  error?: string;
}

export interface CallScreeningSettings {
  isRoleHeld: boolean;
  isAvailable: boolean;
}

export interface AudioFileInfo {
  uri: string;
  name: string;
  type: string;
  size: number;
}
