import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { ChallengeState, VerificationState } from '../types';

interface Props {
  challengeState?: ChallengeState;
  challengeText?: string | null;
  verificationState?: VerificationState;
  audioActive?: boolean;
}

/**
 * Evidence stream — Active Liveness & Challenge Response.
 * Displays real active liveness challenge verification or "Not performed".
 * Never fabricates 100% or synthetic percentages when no challenge has run.
 */
export const ActiveLivenessPanel: React.FC<Props> = ({
  challengeState = 'idle',
  challengeText = null,
  verificationState = 'idle',
  audioActive = false,
}) => {
  const { colors } = useTheme();
  const isChallengeActive = challengeState !== 'idle';
  const isVerificationActive = verificationState !== 'idle';
  const hasInteractiveActivity = isChallengeActive || isVerificationActive;

  if (!hasInteractiveActivity) {
    return (
      <PanelCard title="ACTIVE LIVENESS" icon="🧩" meta="on-demand">
        <MetricRow
          label="Liveness Challenge"
          value="Not performed"
          tone="muted"
          pill
        />
        <MetricRow
          label="Speech Activity"
          value={audioActive ? 'Acoustic signal' : 'Insufficient Evidence'}
          tone={audioActive ? 'good' : 'muted'}
          pill
        />
        <Text style={[styles.note, { color: colors.textMuted }]}>
          Use "Challenge Caller" to initiate a synchronous voice phrase test.
        </Text>
      </PanelCard>
    );
  }

  const challengeTone =
    challengeState === 'passed' ? 'good' : challengeState === 'failed' ? 'bad' : 'warn';
  const verificationTone =
    verificationState === 'approved'
      ? 'good'
      : verificationState === 'rejected'
      ? 'bad'
      : 'muted';

  const accentColor =
    challengeState === 'failed' || verificationState === 'rejected'
      ? colors.danger
      : challengeState === 'passed' || verificationState === 'approved'
      ? colors.success
      : colors.warning;

  return (
    <PanelCard
      title="ACTIVE LIVENESS"
      icon="🧩"
      meta={challengeState.toUpperCase()}
      accent={accentColor}
    >
      <MetricRow
        label="Challenge Status"
        value={challengeState.toUpperCase()}
        tone={challengeTone}
        pill
      />
      {challengeText && (
        <View
          style={[
            styles.phraseBlock,
            {
              backgroundColor: `${colors.accent}0D`,
              borderLeftColor: colors.accent,
            },
          ]}
        >
          <Text style={[styles.phraseLabel, { color: colors.textMuted }]}>
            CHALLENGE PHRASE
          </Text>
          <Text style={[styles.phraseText, { color: colors.textPrimary }]}>
            "{challengeText}"
          </Text>
        </View>
      )}
      <MetricRow
        label="Independent Verification"
        value={isVerificationActive ? verificationState.toUpperCase() : 'Not performed'}
        tone={verificationTone}
        pill
      />
      <MetricRow
        label="Activity State"
        value={audioActive ? 'Active speech energy' : 'No active speech'}
        tone={audioActive ? 'good' : 'muted'}
        pill
      />
      <Text style={[styles.note, { color: colors.textMuted }]}>
        Liveness challenge results reflect real-time acoustic response timing
        and semantic match against the issued verification prompt.
      </Text>
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  note: { fontSize: 11, lineHeight: 16, marginTop: 2 },
  phraseBlock: {
    borderLeftWidth: 3,
    paddingLeft: 10,
    paddingVertical: 6,
    borderRadius: 4,
    gap: 2,
  },
  phraseLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  phraseText: {
    fontSize: 13,
    fontStyle: 'italic',
    fontWeight: '500',
  },
});
