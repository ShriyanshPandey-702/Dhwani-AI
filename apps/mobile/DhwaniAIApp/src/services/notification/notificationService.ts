import { callScreeningService } from '../telecom/callScreeningService';
import { RiskState, Decision } from '../../types';

class NotificationService {
  private lastNotifiedState: RiskState | null = null;
  private lastNotifiedDecision: Decision | null = null;
  private lastNotificationTimestamp: number = 0;
  private readonly THROTTLE_WINDOW_MS = 2500; // minimum interval between alert notifications

  /**
   * Dispatched when live microphone monitoring starts.
   */
  async notifyMicAnalysisStarted(): Promise<void> {
    this.lastNotifiedState = 'insufficient_evidence';
    this.lastNotificationTimestamp = Date.now();
    await callScreeningService.postSecurityNotification(
      'Dhwani AI — Live analysis started',
      'Source: Device Microphone\nStatus: INSUFFICIENT EVIDENCE\nAcoustic monitoring active.',
      false
    );
  }

  /**
   * Dispatched when audio file manual analysis starts.
   */
  async notifyFileAnalysisStarted(filename: string): Promise<void> {
    this.lastNotificationTimestamp = Date.now();
    await callScreeningService.postSecurityNotification(
      'Dhwani AI — Audio analysis started',
      `Target: ${filename}\nStatus: Evaluating multi-modal ML core (AASIST + ECAPA + Whisper)...`,
      false
    );
  }

  /**
   * Dispatched on meaningful risk state transitions or policy actions.
   * Throttled to prevent flooding on rapid chunk evaluation.
   */
  async notifyRiskTransition(
    state: RiskState,
    score: number,
    decision: Decision,
    evidenceSummary?: string
  ): Promise<void> {
    // Only notify on elevated risk states or decision changes
    const isElevated = state === 'suspicious' || state === 'high' || state === 'critical';
    const stateChanged = state !== this.lastNotifiedState;
    const decisionChanged = decision !== this.lastNotifiedDecision;
    const now = Date.now();

    if (!stateChanged && !decisionChanged) {
      return;
    }

    if (!isElevated && !decisionChanged) {
      this.lastNotifiedState = state;
      return;
    }

    if (now - this.lastNotificationTimestamp < this.THROTTLE_WINDOW_MS) {
      return;
    }

    this.lastNotifiedState = state;
    this.lastNotifiedDecision = decision;
    this.lastNotificationTimestamp = now;

    let title = '';
    let message = '';
    let isHighPriority = false;

    if (state === 'critical') {
      title = 'Dhwani AI — Critical impersonation attack detected';
      message = `Risk: CRITICAL · ${score}/100\nEvidence: ${evidenceSummary || 'Strong AI voice cloning + financial/credential threat'}\nAction: ${decision}`;
      isHighPriority = true;
    } else if (state === 'high') {
      title = 'Dhwani AI — High-risk call detected';
      message = `Risk: HIGH · ${score}/100\nEvidence: ${evidenceSummary || 'AI-generated voice indicators + identity mismatch'}\nAction: ${decision}`;
      isHighPriority = true;
    } else if (state === 'suspicious') {
      title = 'Dhwani AI — Suspicious voice activity detected';
      message = `Risk: SUSPICIOUS · ${score}/100\nEvidence: ${evidenceSummary || 'Voice authenticity anomaly + contextual risk'}\nAction: ${decision}`;
      isHighPriority = true;
    } else if (decisionChanged && (decision === 'VERIFY' || decision === 'HOLD' || decision === 'BLOCK')) {
      title = `Dhwani AI — Policy Action: ${decision}`;
      message = `Security decision updated to ${decision}.\nRisk State: ${state.toUpperCase()} · Score: ${score}/100`;
      isHighPriority = true;
    }

    if (title && message) {
      await callScreeningService.postSecurityNotification(title, message, isHighPriority);
    }
  }

  /**
   * Resets notification tracking on session termination.
   */
  reset(): void {
    this.lastNotifiedState = null;
    this.lastNotifiedDecision = null;
    this.lastNotificationTimestamp = 0;
  }
}

export const notificationService = new NotificationService();
