import React from 'react';
import { Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { colors } from '../utils/theme';
import { IdentityEvidence } from '../types';

interface Props {
  identity: IdentityEvidence | null;
}

const CONSISTENCY_TONE = {
  GOOD: 'good',
  VARIABLE: 'warn',
  POOR: 'bad',
  UNKNOWN: 'muted',
} as const;

const ENROLLMENT_TONE = {
  VERIFIED: 'good',
  ENROLLED: 'warn',
  MISMATCH: 'bad',
  NOT_ENROLLED: 'muted',
} as const;

/**
 * Evidence stream 2 — speaker identity.
 *
 * A mismatch here is evidence about *identity only*. It is never presented as
 * proof that the voice is synthetic; the Risk Engine decides how much weight it
 * carries alongside the other streams.
 */
export const IdentityPanel: React.FC<Props> = ({ identity }) => {
  if (!identity || identity.enrollment_status === 'NOT_ENROLLED') {
    return (
      <PanelCard title="SPEAKER IDENTITY" meta="no reference">
        <MetricRow label="Enrollment" value="NOT ENROLLED" tone="muted" />
        <Text style={styles.note}>
          No enrolled speaker reference for this session, so identity contributes
          no evidence. Dhwani AI reports the gap rather than assuming a match.
        </Text>
      </PanelCard>
    );
  }

  const matchTone =
    identity.match_score >= 75 ? 'good' : identity.match_score >= 50 ? 'warn' : 'bad';

  return (
    <PanelCard
      title="SPEAKER IDENTITY"
      meta={`confidence ${Math.round(identity.confidence * 100)}%`}
      accent={matchTone === 'bad' ? colors.high : undefined}>
      <MetricRow
        label="Match Score"
        value={`${identity.match_score}%`}
        tone={matchTone}
        fraction={identity.match_score / 100}
      />
      <MetricRow
        label="Identity Confidence"
        value={`${Math.round(identity.confidence * 100)}%`}
        tone="muted"
        fraction={identity.confidence}
      />
      <MetricRow
        label="Speaker Consistency"
        value={identity.consistency}
        tone={CONSISTENCY_TONE[identity.consistency] ?? 'muted'}
      />
      <MetricRow
        label="Enrollment Status"
        value={identity.enrollment_status.replace('_', ' ')}
        tone={ENROLLMENT_TONE[identity.enrollment_status] ?? 'muted'}
      />
      {identity.is_mock ? (
        <Text style={styles.stub}>
          Spectral-fingerprint stub — not a speaker-recognition model ({identity.model_version})
        </Text>
      ) : (
        <Text style={styles.stub}>
          {identity.model_name} · {identity.model_version} — thresholds not
          calibrated for this channel
        </Text>
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  note: { color: colors.textMuted, fontSize: 11, lineHeight: 16 },
  stub: { color: colors.textMuted, fontSize: 10, marginTop: 2, lineHeight: 14 },
});
