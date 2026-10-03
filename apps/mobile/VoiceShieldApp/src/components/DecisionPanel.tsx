import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTheme } from '../utils/theme';
import { Decision } from '../types';

interface Props {
  decision: Decision;
  reasons: string[];
  recommendedAction: string;
  evidenceConfidence: number;
}

const DECISION_CONFIG: Record<
  Decision,
  { icon: string; emoji: string; title: string; stateKey: 'success' | 'warning' | 'danger' | 'critical' }
> = {
  ALLOW: { icon: '✓', emoji: '🛡', title: 'NO ACTION REQUIRED', stateKey: 'success' },
  VERIFY: { icon: '⚠', emoji: '🔍', title: 'VERIFICATION REQUIRED', stateKey: 'warning' },
  HOLD: { icon: '🔒', emoji: '🔒', title: 'ACTION HELD', stateKey: 'danger' },
  BLOCK: { icon: '⛔', emoji: '🚫', title: 'BLOCKED', stateKey: 'critical' },
  ESCALATE: { icon: '🚨', emoji: '🚨', title: 'ESCALATED', stateKey: 'critical' },
};

const REASON_TEXT: Record<string, string> = {
  voice_authenticity_anomaly: 'Voice authenticity anomaly',
  moderate_synthetic_indicators: 'Moderate synthetic-voice indicators',
  speaker_identity_mismatch: 'Speaker does not match enrolled reference',
  speaker_identity_inconsistency: 'Speaker consistency has degraded',
  high_consequence_request: 'High-consequence request detected',
  suspicious_conversation_context: 'Suspicious conversation context',
  authenticity_evidence_pending: 'Authenticity evidence still accumulating',
  context_evidence_pending: 'Conversation context still accumulating',
  no_enrolled_speaker_reference: 'No enrolled speaker reference',
  evidence_stale: 'Evidence is stale (stream interrupted)',
  insufficient_evidence_for_high_consequence: 'Evidence too thin for a high-consequence request',
  consequence_medium: 'Medium-consequence action requested',
  consequence_high: 'High-consequence action requested',
  consequence_critical: 'Critical-consequence action requested',
  challenge_failed: 'Caller failed the challenge',
  challenge_passed: 'Caller passed the challenge',
  verification_approved: 'Independent verification approved',
  verification_rejected: 'Independent verification rejected',
};

const humanise = (code: string) =>
  REASON_TEXT[code] || code.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

/** Premium security decision card with gradient tinted border and reason list. */
export const DecisionPanel: React.FC<Props> = ({
  decision,
  reasons,
  recommendedAction,
  evidenceConfidence,
}) => {
  const { colors, isDark } = useTheme();
  const cfg = DECISION_CONFIG[decision] ?? DECISION_CONFIG.ALLOW;

  const decisionColor =
    cfg.stateKey === 'success'
      ? colors.success
      : cfg.stateKey === 'warning'
      ? colors.warning
      : cfg.stateKey === 'danger'
      ? colors.danger
      : colors.critical ?? colors.danger;

  const confidencePct = Math.round(evidenceConfidence * 100);
  const confidenceTone =
    confidencePct >= 70 ? colors.success : confidencePct >= 40 ? colors.warning : colors.textMuted;

  return (
    <View
      style={[
        styles.card,
        {
          borderColor: isDark ? `${decisionColor}40` : `${decisionColor}30`,
          backgroundColor: isDark ? colors.surface : colors.surface,
        },
      ]}
    >
      {/* Top accent bar */}
      <View style={[styles.topBar, { backgroundColor: decisionColor }]} />

      {/* Label */}
      <Text style={[styles.sectionLabel, { color: colors.textMuted }]}>
        SECURITY DECISION
      </Text>

      {/* Headline */}
      <View style={styles.headline}>
        <Text style={styles.emoji}>{cfg.emoji}</Text>
        <View style={styles.headlineText}>
          <Text style={[styles.title, { color: decisionColor }]}>{cfg.title}</Text>
          <Text style={[styles.decisionBadge, { color: decisionColor }]}>
            {decision}
          </Text>
        </View>
      </View>

      {/* Reason list */}
      {reasons.length > 0 && (
        <View style={styles.reasons}>
          <Text style={[styles.reasonsLabel, { color: colors.textMuted }]}>Why this decision</Text>
          {reasons.slice(0, 5).map((reason, index) => (
            <View key={`${reason}-${index}`} style={styles.reasonRow}>
              <View
                style={[
                  styles.bullet,
                  { backgroundColor: decisionColor },
                ]}
              />
              <Text style={[styles.reasonText, { color: colors.textSecondary }]}>
                {humanise(reason)}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Recommended action */}
      {!!recommendedAction && (
        <View
          style={[
            styles.actionBox,
            {
              backgroundColor: `${decisionColor}10`,
              borderColor: `${decisionColor}30`,
            },
          ]}
        >
          <Text style={[styles.actionLabel, { color: colors.textMuted }]}>
            RECOMMENDED ACTION
          </Text>
          <Text style={[styles.actionValue, { color: decisionColor }]}>
            {recommendedAction}
          </Text>
        </View>
      )}

      {/* Evidence confidence footer */}
      <View style={styles.footer}>
        <Text style={[styles.footerLabel, { color: colors.textMuted }]}>
          Evidence sufficiency
        </Text>
        <View style={[styles.confTrack, { backgroundColor: colors.surfaceElevated }]}>
          <View
            style={[
              styles.confFill,
              {
                width: `${confidencePct}%`,
                backgroundColor: confidenceTone,
              },
            ]}
          />
        </View>
        <Text style={[styles.confPct, { color: confidenceTone }]}>
          {confidencePct}%
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    gap: 12,
    paddingBottom: 14,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  topBar: {
    height: 2,
    width: '100%',
  },
  sectionLabel: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1.4,
    paddingHorizontal: 16,
  },
  headline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
  },
  emoji: { fontSize: 28 },
  headlineText: { flex: 1, gap: 2 },
  title: { fontSize: 18, fontWeight: '800', letterSpacing: 0.3 },
  decisionBadge: { fontSize: 11, fontWeight: '700', letterSpacing: 1.2 },
  reasons: { gap: 5, paddingHorizontal: 16 },
  reasonsLabel: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginBottom: 2,
  },
  reasonRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  bullet: {
    width: 6,
    height: 6,
    borderRadius: 3,
    flexShrink: 0,
  },
  reasonText: { flex: 1, fontSize: 13, lineHeight: 18 },
  actionBox: {
    marginHorizontal: 16,
    borderRadius: 10,
    borderWidth: 1,
    padding: 10,
    gap: 3,
  },
  actionLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  actionValue: { fontSize: 14, fontWeight: '700' },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
  },
  footerLabel: { fontSize: 10, fontWeight: '500' },
  confTrack: {
    flex: 1,
    height: 5,
    borderRadius: 3,
    overflow: 'hidden',
  },
  confFill: { height: 5, borderRadius: 3 },
  confPct: { fontSize: 11, fontWeight: '700', width: 32, textAlign: 'right' },
});
