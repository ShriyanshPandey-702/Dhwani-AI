import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius } from '../utils/theme';
import { Decision } from '../types';

interface Props {
  decision: Decision;
  reasons: string[];
  recommendedAction: string;
  evidenceConfidence: number;
}

const DECISION_CONFIG: Record<Decision, { icon: string; color: string; title: string }> = {
  ALLOW: { icon: '✓', color: colors.safe, title: 'NO ACTION REQUIRED' },
  VERIFY: { icon: '⚠', color: colors.suspicious, title: 'VERIFICATION REQUIRED' },
  HOLD: { icon: '🔒', color: colors.high, title: 'ACTION HELD' },
  BLOCK: { icon: '⛔', color: colors.critical, title: 'BLOCKED' },
  ESCALATE: { icon: '🚨', color: colors.critical, title: 'ESCALATED' },
};

/** Human-readable text for the reason codes the backend emits. */
const REASON_TEXT: Record<string, string> = {
  voice_authenticity_anomaly: 'Voice authenticity anomaly',
  moderate_synthetic_indicators: 'Moderate synthetic-voice indicators',
  speaker_identity_mismatch: 'Speaker does not match the enrolled reference',
  speaker_identity_inconsistency: 'Speaker consistency has degraded',
  high_consequence_request: 'High-consequence request detected',
  suspicious_conversation_context: 'Suspicious conversation context',
  authenticity_evidence_pending: 'Authenticity evidence still accumulating',
  context_evidence_pending: 'Conversation context still accumulating',
  no_enrolled_speaker_reference: 'No enrolled speaker reference',
  evidence_stale: 'Evidence is stale (stream interrupted)',
  insufficient_evidence_for_high_consequence:
    'Evidence too thin for a high-consequence request',
  consequence_medium: 'Medium-consequence action requested',
  consequence_high: 'High-consequence action requested',
  consequence_critical: 'Critical-consequence action requested',
  challenge_failed: 'Caller failed the challenge',
  challenge_passed: 'Caller passed the challenge',
  verification_approved: 'Independent verification approved',
  verification_rejected: 'Independent verification rejected',
};

const humanise = (code: string) =>
  REASON_TEXT[code] || code.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());

/** The current security decision, and why. */
export const DecisionPanel: React.FC<Props> = ({
  decision,
  reasons,
  recommendedAction,
  evidenceConfidence,
}) => {
  const cfg = DECISION_CONFIG[decision] ?? DECISION_CONFIG.ALLOW;

  return (
    <View style={[styles.card, { borderColor: cfg.color, backgroundColor: `${cfg.color}14` }]}>
      <Text style={styles.sectionLabel}>SECURITY DECISION</Text>
      <View style={styles.headline}>
        <Text style={styles.icon}>{cfg.icon}</Text>
        <Text style={[styles.title, { color: cfg.color }]}>{cfg.title}</Text>
      </View>

      {reasons.length > 0 && (
        <View style={styles.reasons}>
          <Text style={styles.reasonsLabel}>Reasons</Text>
          {reasons.slice(0, 5).map((reason, index) => (
            <View key={`${reason}-${index}`} style={styles.reasonRow}>
              <Text style={[styles.bullet, { color: cfg.color }]}>•</Text>
              <Text style={styles.reasonText}>{humanise(reason)}</Text>
            </View>
          ))}
        </View>
      )}

      {!!recommendedAction && (
        <View style={[styles.footer, { borderTopColor: `${cfg.color}44` }]}>
          <Text style={styles.footerLabel}>Recommended action</Text>
          <Text style={[styles.footerValue, { color: cfg.color }]}>{recommendedAction}</Text>
        </View>
      )}

      <Text style={styles.confidence}>
        Evidence sufficiency {Math.round(evidenceConfidence * 100)}%
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textSecondary,
    letterSpacing: 1.2,
  },
  headline: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  icon: { fontSize: 20 },
  title: { fontSize: 17, fontWeight: '800', letterSpacing: 0.4, flex: 1 },
  reasons: { gap: 3 },
  reasonsLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.textMuted,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  reasonRow: { flexDirection: 'row', gap: 6 },
  bullet: { fontSize: 13 },
  reasonText: { flex: 1, fontSize: 13, color: colors.textSecondary, lineHeight: 18 },
  footer: { borderTopWidth: 1, paddingTop: spacing.sm, gap: 2 },
  footerLabel: {
    fontSize: 10,
    color: colors.textMuted,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  footerValue: { fontSize: 14, fontWeight: '700' },
  confidence: { fontSize: 10, color: colors.textMuted },
});
