import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { colors } from '../utils/theme';
import { ChallengeState, VerificationState } from '../types';

interface Props {
  challengeState?: ChallengeState;
  challengeText?: string | null;
  verificationState?: VerificationState;
  audioActive?: boolean;
}

/**
 * Evidence stream 4 — Active Liveness & Challenge Response.
 * Displays real active liveness challenge verification or "Not performed".
 * Never fabricates 100% or synthetic percentages when no challenge has run.
 */
export const ActiveLivenessPanel: React.FC<Props> = ({
  challengeState = 'idle',
  challengeText = null,
  verificationState = 'idle',
  audioActive = false,
}) => {
  const isChallengeActive = challengeState !== 'idle';
  const isVerificationActive = verificationState !== 'idle';
  const hasInteractiveActivity = isChallengeActive || isVerificationActive;

  if (!hasInteractiveActivity) {
    return (
      <PanelCard title="ACTIVE LIVENESS" meta="on-demand">
        <MetricRow
          label="Liveness Challenge"
          value="Not performed"
          tone="muted"
        />
        <MetricRow
          label="Speech Activity Evidence"
          value={audioActive ? 'Acoustic signal detected' : 'Insufficient Evidence'}
          tone={audioActive ? 'good' : 'muted'}
        />
        <Text style={styles.note}>
          Active liveness verification has not been performed for this session.
          Use the 'Challenge Caller' action to initiate a synchronous cryptographic or voice phrase verification test.
        </Text>
      </PanelCard>
    );
  }

  const challengeTone =
    challengeState === 'passed' ? 'good' : challengeState === 'failed' ? 'bad' : 'warn';

  return (
    <PanelCard
      title="ACTIVE LIVENESS"
      meta={challengeState.toUpperCase()}
      accent={challengeState === 'failed' ? colors.high : undefined}>
      <MetricRow
        label="Challenge Status"
        value={challengeState.toUpperCase()}
        tone={challengeTone}
      />
      {challengeText && (
        <MetricRow
          label="Challenge Phrase"
          value={challengeText}
          tone="muted"
        />
      )}
      <MetricRow
        label="Independent Verification"
        value={verificationState === 'idle' ? 'Not performed' : verificationState.toUpperCase()}
        tone={verificationState === 'approved' ? 'good' : verificationState === 'rejected' ? 'bad' : 'muted'}
      />
      <MetricRow
        label="Activity State"
        value={audioActive ? 'Active speech energy' : 'No active speech'}
        tone={audioActive ? 'good' : 'muted'}
      />
      <Text style={styles.note}>
        Liveness challenge results reflect real-time acoustic response timing and semantic match against issued verification prompt.
      </Text>
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  note: { color: colors.textMuted, fontSize: 11, lineHeight: 16, marginTop: 4 },
});
