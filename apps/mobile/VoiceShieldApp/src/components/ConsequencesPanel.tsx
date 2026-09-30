import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { ContextEvidence } from '../types';

interface Props {
  context: ContextEvidence | null;
}

const CONSEQUENCE_TONE = {
  low: 'good',
  medium: 'warn',
  high: 'bad',
  critical: 'bad',
} as const;

type ThreatEntry = { label: string; icon: string };

/**
 * Evidence stream 4 — Consequences & Threat Classification.
 * Surfaces real financial, credential, urgency, authority, and impersonation
 * threat detection. Never fabricates data.
 */
export const ConsequencesPanel: React.FC<Props> = ({ context }) => {
  const { colors } = useTheme();

  if (!context || !context.transcript) {
    return (
      <PanelCard title="CONSEQUENCES & THREATS" icon="🛡" meta="speech context">
        <MetricRow label="Consequence Level" value="Insufficient Evidence" tone="muted" pill />
        <Text style={[styles.pending, { color: colors.textMuted }]}>
          Consequence analysis requires transcribed speech. No threat is assumed
          until context is evaluated.
        </Text>
      </PanelCard>
    );
  }

  const detectedThreats: ThreatEntry[] = [];
  if (context.otp_request) detectedThreats.push({ label: 'OTP / 2FA Request', icon: '🔑' });
  if (context.credential_request) detectedThreats.push({ label: 'Password / Credentials', icon: '🔐' });
  if (context.financial_request) detectedThreats.push({ label: 'Bank / Money / UPI Transfer', icon: '💸' });
  if (context.sensitive_information_request)
    detectedThreats.push({ label: 'KYC / Card / Personal Data', icon: '📋' });
  if (context.authority_claim)
    detectedThreats.push({ label: 'Authority Impersonation', icon: '🚨' });
  if (context.urgency) detectedThreats.push({ label: 'Artificial Urgency / Panic', icon: '⏱' });
  if (context.social_engineering)
    detectedThreats.push({ label: 'Social Engineering Pattern', icon: '⚡' });

  const consequenceLevel = context.consequence?.toUpperCase() || 'LOW';
  const tone = CONSEQUENCE_TONE[context.consequence] ?? 'good';
  const hasHighThreat =
    context.consequence === 'critical' || context.consequence === 'high';
  const accentColor = hasHighThreat ? colors.danger : detectedThreats.length > 0 ? colors.warning : undefined;

  return (
    <PanelCard
      title="CONSEQUENCES & THREATS"
      icon="🛡"
      meta={`level ${consequenceLevel}`}
      accent={accentColor}
    >
      {/* Consequence level + threat score */}
      <MetricRow
        label="Transaction Consequence"
        value={consequenceLevel}
        tone={tone}
        pill
      />
      <MetricRow
        label="Context Threat Score"
        value={`${context.score} / 100`}
        tone={context.score >= 50 ? 'bad' : context.score >= 25 ? 'warn' : 'good'}
        fraction={context.score / 100}
      />

      {/* Threat classification summary */}
      <MetricRow
        label="Active Threat Signals"
        value={
          detectedThreats.length > 0
            ? `${detectedThreats.length} Signal${detectedThreats.length > 1 ? 's' : ''}`
            : 'None Detected'
        }
        tone={detectedThreats.length > 0 ? 'bad' : 'good'}
        pill
      />

      {/* Individual threat chips */}
      {detectedThreats.length > 0 && (
        <View style={styles.threatGrid}>
          {detectedThreats.map((threat, idx) => (
            <View
              key={idx}
              style={[
                styles.threatChip,
                {
                  backgroundColor: `${colors.danger}14`,
                  borderColor: `${colors.danger}35`,
                },
              ]}
            >
              <Text style={styles.threatIcon}>{threat.icon}</Text>
              <Text style={[styles.threatText, { color: colors.danger }]}>
                {threat.label}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Detected phrases */}
      {context.detected_phrases && context.detected_phrases.length > 0 && (
        <View style={styles.phrasesRow}>
          <Text style={[styles.phrasesLabel, { color: colors.textMuted }]}>
            Trigger phrases:{' '}
          </Text>
          <Text style={[styles.phrasesValue, { color: colors.textSecondary }]}>
            {context.detected_phrases.join(', ')}
          </Text>
        </View>
      )}

      {/* Transcript quote */}
      {!!context.transcript && (
        <View
          style={[
            styles.transcriptBlock,
            {
              backgroundColor: `${colors.accent}0D`,
              borderLeftColor: accentColor ?? colors.accent,
            },
          ]}
        >
          <Text
            style={[styles.transcriptQuote, { color: colors.textSecondary }]}
            numberOfLines={3}
          >
            {`"${context.transcript}"`}
          </Text>
        </View>
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  pending: { fontSize: 12, fontStyle: 'italic', marginTop: 4, lineHeight: 16 },
  threatGrid: { marginTop: 4, gap: 5 },
  threatChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderWidth: 1,
  },
  threatIcon: { fontSize: 13 },
  threatText: { fontSize: 12, fontWeight: '700', flex: 1 },
  phrasesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 4,
  },
  phrasesLabel: { fontSize: 11, fontWeight: '600' },
  phrasesValue: { fontSize: 11, fontStyle: 'italic', flex: 1 },
  transcriptBlock: {
    borderLeftWidth: 3,
    paddingLeft: 10,
    paddingVertical: 6,
    marginTop: 4,
    borderRadius: 4,
  },
  transcriptQuote: {
    fontSize: 12,
    fontStyle: 'italic',
    lineHeight: 17,
  },
});
