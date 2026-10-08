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

const flag = (value: boolean): { value: string; tone: 'bad' | 'muted'; pill: true } =>
  value
    ? { value: 'DETECTED', tone: 'bad', pill: true }
    : { value: 'NO', tone: 'muted', pill: true };

/**
 * Evidence stream 3 — conversation context.
 *
 * These are signals about *what is being asked for*, not about how the voice
 * sounds. A detected OTP request raises consequence and contextual risk; it
 * says nothing about authenticity.
 */
export const ContextPanel: React.FC<Props> = ({ context }) => {
  const { colors } = useTheme();

  if (!context) {
    return (
      <PanelCard title="CONVERSATION CONTEXT" icon="💬">
        <Text style={[styles.pending, { color: colors.textMuted }]}>
          Awaiting transcribed speech…
        </Text>
      </PanelCard>
    );
  }

  const urgency = context.urgency
    ? { value: 'HIGH', tone: 'bad' as const, pill: true as const }
    : { value: 'NO', tone: 'muted' as const, pill: true as const };

  const accentColor =
    context.social_engineering
      ? colors.danger
      : context.consequence === 'high' || context.consequence === 'critical'
      ? colors.danger
      : context.score >= 33
      ? colors.warning
      : undefined;

  return (
    <PanelCard
      title="CONVERSATION CONTEXT"
      icon="💬"
      meta={`conf ${Math.round(context.confidence * 100)}%`}
      accent={accentColor}
    >
      {/* Context risk score with bar */}
      <MetricRow
        label="Context Risk Score"
        value={`${context.score} / 100`}
        tone={context.score >= 66 ? 'bad' : context.score >= 33 ? 'warn' : 'good'}
        fraction={context.score / 100}
      />

      <MetricRow
        label="Transaction Consequence"
        value={context.consequence.toUpperCase()}
        tone={CONSEQUENCE_TONE[context.consequence] ?? 'muted'}
        pill
      />
      <MetricRow label="Urgency / Pressure" {...urgency} />

      {/* Divider */}
      <View style={[styles.divider, { backgroundColor: colors.border }]} />

      {/* Threat flags */}
      <MetricRow label="Financial Request" {...flag(context.financial_request)} />
      <MetricRow label="OTP Request" {...flag(context.otp_request)} />
      <MetricRow label="Credential Request" {...flag(context.credential_request)} />
      <MetricRow label="Sensitive Information" {...flag(context.sensitive_information_request)} />
      <MetricRow label="Authority Claim" {...flag(context.authority_claim)} />
      <MetricRow
        label="Social Engineering"
        value={context.social_engineering ? 'HIGH' : 'NO'}
        tone={context.social_engineering ? 'bad' : 'muted'}
        pill
      />

      {/* Detected phrase tags */}
      {context.detected_phrases && context.detected_phrases.length > 0 && (
        <View style={styles.phrasesSection}>
          <Text style={[styles.phrasesLabel, { color: colors.textMuted }]}>
            Trigger Keywords
          </Text>
          <View style={styles.phraseRow}>
            {context.detected_phrases.map((phrase, idx) => (
              <View
                key={idx}
                style={[
                  styles.phraseChip,
                  {
                    backgroundColor: `${colors.warning}14`,
                    borderColor: `${colors.warning}35`,
                  },
                ]}
              >
                <Text style={[styles.phraseText, { color: colors.warning }]}>
                  {phrase}
                </Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Live transcript block */}
      {!!context.transcript && (
        <View
          style={[
            styles.transcriptBlock,
            {
              backgroundColor: `${colors.accent}0D`,
              borderLeftColor: colors.accent,
            },
          ]}
        >
          <Text style={[styles.transcriptQuote, { color: colors.textSecondary }]}>
            {`"${context.transcript}"`}
          </Text>
        </View>
      )}

      {/* Model footer */}
      <Text style={[styles.stub, { color: colors.textMuted }]}>
        {context.transcript_is_mock
          ? `Scripted stub · not real speech recognition · rules ${context.model_version}`
          : `${context.transcript_model}${context.transcript_language ? ` · ${context.transcript_language}` : ''} · rules ${context.model_version}`}
      </Text>
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  pending: { fontSize: 13, fontStyle: 'italic' },
  divider: { height: 1, marginVertical: 4 },
  phrasesSection: { marginTop: 4, gap: 6 },
  phrasesLabel: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  phraseRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 5 },
  phraseChip: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
  },
  phraseText: { fontSize: 11, fontWeight: '700' },
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
  stub: { fontSize: 10, marginTop: 2, lineHeight: 14 },
});
