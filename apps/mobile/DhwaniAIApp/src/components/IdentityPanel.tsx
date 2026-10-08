import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { IdentityEvidence } from '../types';
import { UserIcon } from './Icons';

interface Props {
  identity: (IdentityEvidence & {
    speaker_match?: boolean;
    target_enrolled?: boolean;
    similarity_score?: number;
    threshold?: number;
  }) | null;
  comparison?: {
    similarity: number;
    threshold: number;
    verdict: 'SAME_SPEAKER' | 'DIFFERENT_SPEAKER';
    confidence: number;
    voiceA?: { label: string; isReal: boolean };
    voiceB?: { label: string; isReal: boolean };
  } | null;
  hasReference?: boolean;
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
 *
 * When no reference voice is supplied, Dhwani AI truthfully reports NOT ENROLLED
 * rather than fabricating a speaker match.
 */
export const IdentityPanel: React.FC<Props> = ({ identity, comparison, hasReference }) => {
  const { colors } = useTheme();

  // Reference is considered present only if explicitly indicated or if comparison data with enrollment is available
  const referencePresent =
    hasReference === true ||
    identity?.reference_available === true ||
    (identity?.enrollment_status !== undefined &&
      identity.enrollment_status !== 'NOT_ENROLLED' &&
      identity.enrollment_status !== 'SELF_CONSISTENCY');

  // Check if comparison data is available
  const hasComparisonData =
    Boolean(comparison) ||
    (identity !== null &&
      identity !== undefined &&
      ((identity.match_score !== null && identity.match_score !== undefined) ||
        (identity.similarity !== null && identity.similarity !== undefined) ||
        (identity.similarity_score !== null && identity.similarity_score !== undefined)));

  const isEnrolledWithComparison = referencePresent && hasComparisonData;

  if (!identity || !isEnrolledWithComparison) {
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

  // Reference voice exists and comparison data is available: extract honest metrics
  const sim =
    comparison?.similarity ??
    identity.similarity ??
    identity.similarity_score ??
    null;

  const conf =
    comparison?.confidence ??
    (identity.confidence > 0 ? identity.confidence : null);

  const thresh =
    comparison?.threshold ??
    identity.threshold ??
    0.60;

  const rawMatchScore =
    identity.match_score ??
    (sim !== null ? Math.round(sim * 100) : null);

  const isMatch =
    comparison?.verdict === 'SAME_SPEAKER'
      ? true
      : comparison?.verdict === 'DIFFERENT_SPEAKER'
      ? false
      : identity.speaker_match !== undefined
      ? identity.speaker_match
      : identity.enrollment_status === 'VERIFIED' || identity.enrollment_status === 'ENROLLED'
      ? true
      : identity.enrollment_status === 'MISMATCH'
      ? false
      : sim !== null
      ? sim >= thresh
      : (rawMatchScore ?? 0) >= 50;

  const matchTone = isMatch ? 'good' : 'bad';
  const matchColor = isMatch ? colors.success : colors.danger;

  const enrollStatus =
    identity.enrollment_status &&
    identity.enrollment_status !== 'NOT_ENROLLED' &&
    identity.enrollment_status !== 'SELF_CONSISTENCY'
      ? identity.enrollment_status
      : isMatch
      ? 'VERIFIED'
      : 'MISMATCH';

  const enrollIcon = ENROLLMENT_ICON[enrollStatus] ?? (isMatch ? '✓' : '⚠');
  const enrollTone = ENROLLMENT_TONE[enrollStatus] ?? (isMatch ? 'good' : 'bad');
  const consistencyTone = identity.consistency ? (CONSISTENCY_TONE[identity.consistency] ?? 'muted') : 'muted';

  return (
    <PanelCard
      title="SPEAKER IDENTITY"
      icon={<UserIcon size={13} color={colors.accent} />}
      meta={conf !== null ? `conf ${Math.round(conf * 100)}%` : undefined}
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
            {rawMatchScore !== null ? `${rawMatchScore}%` : isMatch ? 'MATCH' : 'MISMATCH'}
          </Text>
          <Text style={[styles.matchLabel, { color: colors.textMuted }]}>
            {isMatch ? 'match' : 'mismatch'}
          </Text>
        </View>

        <View style={styles.matchDetails}>
          {identity.consistency && (
            <MetricRow
              label="Consistency"
              value={identity.consistency}
              tone={consistencyTone}
              pill
            />
          )}
          <MetricRow
            label="Enrollment"
            value={`${enrollIcon} ${enrollStatus.replace('_', ' ')}`}
            tone={enrollTone}
            pill
          />
          {thresh !== null && thresh !== undefined && (
            <MetricRow
              label="Threshold"
              value={`${Math.round(thresh * 100)}% (${thresh.toFixed(2)})`}
              tone="muted"
              pill
            />
          )}
          {sim !== null && (
            <MetricRow
              label="Similarity"
              value={`${Math.round(sim * 100)}% (${sim.toFixed(2)})`}
              tone={matchTone}
              pill
            />
          )}
          {conf !== null && (
            <MetricRow
              label="Identity Confidence"
              value={`${Math.round(conf * 100)}%`}
              tone="muted"
              fraction={conf}
            />
          )}
        </View>
      </View>

      {/* Model footer */}
      <Text style={[styles.stub, { color: colors.textMuted }]}>
        {identity.is_mock
          ? `Spectral-fingerprint stub · ${identity.model_version || 'ecapa-stub'}`
          : `${identity.model_name || 'ECAPA-TDNN'} · ${identity.model_version || 'ECAPA-TDNN-voxceleb'}`}
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
