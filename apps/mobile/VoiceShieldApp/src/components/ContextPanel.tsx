import React from 'react';
import { Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { colors } from '../utils/theme';
import { ContextEvidence } from '../types';

interface Props {
  context: ContextEvidence | null;
}

const flag = (value: boolean): { value: string; tone: 'bad' | 'muted' } =>
  value ? { value: 'DETECTED', tone: 'bad' } : { value: 'NO', tone: 'muted' };

const CONSEQUENCE_TONE = {
  low: 'good',
  medium: 'warn',
  high: 'bad',
  critical: 'bad',
} as const;

/**
 * Evidence stream 3 — conversation context.
 *
 * These are signals about *what is being asked for*, not about how the voice
 * sounds. A detected OTP request raises consequence and contextual risk; it
 * says nothing about authenticity.
 */
export const ContextPanel: React.FC<Props> = ({ context }) => {
  if (!context) {
    return (
      <PanelCard title="CONVERSATION CONTEXT">
        <Text style={styles.pending}>Awaiting transcribed speech…</Text>
      </PanelCard>
    );
  }

  const urgency = context.urgency
    ? { value: 'HIGH', tone: 'bad' as const }
    : { value: 'NORMAL', tone: 'muted' as const };

  return (
    <PanelCard
      title="CONVERSATION CONTEXT"
      meta={`confidence ${Math.round(context.confidence * 100)}%`}
      accent={context.social_engineering ? colors.high : undefined}>
      <MetricRow
        label="Context Risk"
        value={`${context.score}`}
        tone={context.score >= 66 ? 'bad' : context.score >= 33 ? 'warn' : 'good'}
        fraction={context.score / 100}
      />
      <MetricRow label="Urgency" {...urgency} />
      <MetricRow label="Financial Request" {...flag(context.financial_request)} />
      <MetricRow label="OTP Request" {...flag(context.otp_request)} />
      <MetricRow label="Credential Request" {...flag(context.credential_request)} />
      <MetricRow
        label="Sensitive Information"
        {...flag(context.sensitive_information_request)}
      />
      <MetricRow label="Authority Claim" {...flag(context.authority_claim)} />
      <MetricRow
        label="Social Engineering"
        value={context.social_engineering ? 'HIGH' : 'LOW'}
        tone={context.social_engineering ? 'bad' : 'good'}
      />
      <MetricRow
        label="Transaction Consequence"
        value={context.consequence.toUpperCase()}
        tone={CONSEQUENCE_TONE[context.consequence] ?? 'muted'}
      />
      {!!context.transcript && (
        <Text style={styles.transcript} numberOfLines={2}>
          “{context.transcript}”
        </Text>
      )}
      {context.transcript_is_mock ? (
        <Text style={styles.stub}>
          Scripted transcript stub — not real speech recognition. Signal rules
          themselves are live ({context.model_version}).
        </Text>
      ) : (
        <Text style={styles.stub}>
          Transcript: {context.transcript_model}
          {context.transcript_language ? ` · ${context.transcript_language}` : ''} — rules {context.model_version}
        </Text>
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  pending: { color: colors.textMuted, fontSize: 13, fontStyle: 'italic' },
  transcript: {
    color: colors.textSecondary,
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 4,
    lineHeight: 17,
  },
  stub: { color: colors.textMuted, fontSize: 10, marginTop: 2, lineHeight: 14 },
});
