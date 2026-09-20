/**
 * Telecom Call Screening types for VoiceShield.
 * Represents metadata-only signals from Android Telecom CallScreeningService.
 */

export type ScreeningDecision = 'ALLOW' | 'SILENCE' | 'REJECT';

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH';

export type CallerVerificationStatus = 'PASSED' | 'FAILED' | 'NOT_VERIFIED' | 'UNKNOWN';

export type WarningType =
  | 'NONE'
  | 'UNVERIFIED_CALLER'
  | 'VERIFICATION_FAILED'
  | 'RESTRICTED_NUMBER'
  | 'BLOCKLIST_MATCH';

export interface ScreenedCallEvent {
  eventId: string;
  timestamp: number;
  callerMasked: string;
  callerHash: string;
  verificationStatus: CallerVerificationStatus;
  decision: ScreeningDecision;
  riskLevel: RiskLevel;
  warningType: WarningType;
  reasonCodes: string[];
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
