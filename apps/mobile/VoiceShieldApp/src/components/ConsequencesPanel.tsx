import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { colors } from '../utils/theme';
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

/**
 * Evidence stream 3 — Consequences & Threat Classification.
 * Displays real financial, credential, urgency, authority, and impersonation threat detection.
 * If evidence is unavailable: displays "Unavailable" or "Insufficient Evidence".
 * Never fabricates 0% or 100%.
 */
export const ConsequencesPanel: React.FC<Props> = ({ context }) => {
  if (!context || !context.transcript) {
    return (
      <PanelCard title="CONSEQUENCES & THREAT CONTEXT" meta="speech context">
        <MetricRow
          label="Consequence Level"
          value="Insufficient Evidence"
          tone="muted"
        />
        <MetricRow
          label="Threat Signals"
          value="Unavailable (Awaiting transcript)"
          tone="muted"
        />
        <Text style={styles.pending}>
          Conversation consequence analysis requires transcribed speech.
          No consequence is assumed until speech context is evaluated.
        </Text>
      </PanelCard>
    );
  }

  const detectedThreats: string[] = [];
  if (context.otp_request) detectedThreats.push('OTP / 2FA Request');
  if (context.credential_request) detectedThreats.push('Password / Credentials');
  if (context.financial_request) detectedThreats.push('Bank / Money Transfer / UPI');
  if (context.sensitive_information_request) detectedThreats.push('KYC / Card Details / Personal Data');
  if (context.authority_claim) detectedThreats.push('Authority Impersonation (Police/Bank/Govt)');
  if (context.urgency) detectedThreats.push('Artificial Urgency / Panic Induction');
  if (context.social_engineering) detectedThreats.push('Social Engineering Pattern');

  const consequenceLevel = context.consequence?.toUpperCase() || 'LOW';
  const tone = CONSEQUENCE_TONE[context.consequence] ?? 'good';

  return (
    <PanelCard
      title="CONSEQUENCES & THREAT CONTEXT"
      meta={`level ${consequenceLevel}`}
      accent={context.consequence === 'critical' || context.consequence === 'high' ? colors.high : undefined}>
      <MetricRow
        label="Transaction Consequence"
        value={consequenceLevel}
        tone={tone}
      />
      <MetricRow
        label="Context Threat Score"
        value={`${context.score} / 100`}
        tone={context.score >= 50 ? 'bad' : context.score >= 25 ? 'warn' : 'good'}
        fraction={context.score / 100}
      />
      <MetricRow
        label="Threat Classification"
        value={detectedThreats.length > 0 ? `${detectedThreats.length} Active Signal${detectedThreats.length > 1 ? 's' : ''}` : 'None detected'}
        tone={detectedThreats.length > 0 ? 'bad' : 'good'}
      />

      {detectedThreats.length > 0 && (
        <View style={styles.threatsList}>
          {detectedThreats.map((threat, idx) => (
            <View key={idx} style={styles.threatChip}>
              <Text style={styles.threatText}>⚠️ {threat}</Text>
            </View>
          ))}
        </View>
      )}

      {context.detected_phrases && context.detected_phrases.length > 0 && (
        <View style={styles.phrasesRow}>
          <Text style={styles.phrasesLabel}>Trigger phrases: </Text>
          <Text style={styles.phrasesValue}>
            {context.detected_phrases.join(', ')}
          </Text>
        </View>
      )}

      {!!context.transcript && (
        <Text style={styles.transcript} numberOfLines={3}>
          “{context.transcript}”
        </Text>
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  pending: { color: colors.textMuted, fontSize: 12, fontStyle: 'italic', marginTop: 4 },
  threatsList: { marginTop: 6, gap: 4 },
  threatChip: {
    backgroundColor: `${colors.error}18`,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: `${colors.error}33`,
  },
  threatText: { color: colors.high, fontSize: 12, fontWeight: '600' },
  phrasesRow: { flexDirection: 'row', marginTop: 6, flexWrap: 'wrap' },
  phrasesLabel: { color: colors.textMuted, fontSize: 11, fontWeight: '600' },
  phrasesValue: { color: colors.textSecondary, fontSize: 11, fontStyle: 'italic' },
  transcript: {
    color: colors.textSecondary,
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 6,
    lineHeight: 16,
  },
});
