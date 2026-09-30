import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { IdentityEvidence } from '../types';
import { UserIcon } from './Icons';

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

const ENROLLMENT_ICON = {
  VERIFIED: '✓',
  ENROLLED: '⚡',
  MISMATCH: '⚠',
  NOT_ENROLLED: '–',
};

/**
 * Evidence stream 2 — speaker identity.
 *
 * A mismatch here is evidence about *identity only*. It is never presented as
 * proof that the voice is synthetic; the Risk Engine decides how much weight it
 * carries alongside the other streams.
 */
export const IdentityPanel: React.FC<Props> = ({ identity }) => {
  const { colors } = useTheme();

  if (
    !identity ||
    identity.enrollment_status === 'NOT_ENROLLED' ||
    identity.enrollment_status === 'SELF_CONSISTENCY' ||
    identity.match_score === null ||
    identity.match_score === undefined
  ) {
    return (
      <PanelCard
        title="SPEAKER IDENTITY"
        icon={<UserIcon size={13} color={colors.accent} />}
        meta="no reference"
      >
        <MetricRow label="Enrollment" value="NOT ENROLLED" tone="muted" pill />
        <MetricRow label="Match Confidence" value="UNAVAILABLE" tone="muted" pill />
        <Text style={[styles.note, { color: colors.textMuted }]}>
          Identity comparison is unavailable until a reference voice is supplied.
          Dhwani AI reports the gap rather than assuming a match.
        </Text>
      </PanelCard>
    );
  }


  const matchTone =
    identity.match_score >= 75 ? 'good' : identity.match_score >= 50 ? 'warn' : 'bad';
  const matchColor =
    matchTone === 'good'
      ? colors.success
      : matchTone === 'warn'
      ? colors.warning
      : colors.danger;

  const enrollIcon =
    ENROLLMENT_ICON[identity.enrollment_status] ?? '–';
  const enrollTone = ENROLLMENT_TONE[identity.enrollment_status] ?? 'muted';
  const consistencyTone = CONSISTENCY_TONE[identity.consistency] ?? 'muted';

  return (
    <PanelCard
      title="SPEAKER IDENTITY"
      icon={<UserIcon size={13} color={colors.accent} />}
      meta={`conf ${Math.round(identity.confidence * 100)}%`}
      accent={matchTone === 'bad' ? colors.danger : undefined}
    >
      {/* Match score ring-indicator row */}
      <View style={styles.matchRow}>
        <View
          style={[
            styles.matchRing,
            {
              borderColor: matchColor,
              backgroundColor: `${matchColor}14`,
            },
          ]}
        >
          <Text style={[styles.matchScore, { color: matchColor }]}>
            {`${identity.match_score}%`}
          </Text>
          <Text style={[styles.matchLabel, { color: colors.textMuted }]}>
            match
          </Text>
        </View>

        <View style={styles.matchDetails}>
          <MetricRow
            label="Consistency"
            value={identity.consistency}
            tone={consistencyTone}
            pill
          />
          <MetricRow
            label="Enrollment"
            value={`${enrollIcon} ${identity.enrollment_status.replace('_', ' ')}`}
            tone={enrollTone}
            pill
          />
          <MetricRow
            label="Identity Confidence"
            value={`${Math.round(identity.confidence * 100)}%`}
            tone="muted"
            fraction={identity.confidence}
          />
        </View>
      </View>

      {/* Model footer */}
      <Text style={[styles.stub, { color: colors.textMuted }]}>
        {identity.is_mock
          ? `Spectral-fingerprint stub · ${identity.model_version}`
          : `${identity.model_name} · ${identity.model_version}`}
      </Text>
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  note: { fontSize: 11, lineHeight: 16 },
  stub: { fontSize: 10, marginTop: 2, lineHeight: 14 },
  matchRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 14,
    marginTop: 2,
  },
  matchRing: {
    width: 68,
    height: 68,
    borderRadius: 34,
    borderWidth: 2.5,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  matchScore: {
    fontSize: 18,
    fontWeight: '800',
    letterSpacing: -0.5,
  },
  matchLabel: {
    fontSize: 9,
    fontWeight: '600',
    letterSpacing: 0.3,
    marginTop: -2,
  },
  matchDetails: {
    flex: 1,
    gap: 4,
  },
});
