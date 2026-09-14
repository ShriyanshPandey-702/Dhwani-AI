import React from 'react';
import { Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { colors } from '../utils/theme';
import { AnomalyBand, AuthenticityEvidence } from '../types';

interface Props {
  authenticity: AuthenticityEvidence | null;
}

const BAND_TONE: Record<AnomalyBand, 'good' | 'warn' | 'bad'> = {
  LOW: 'good',
  MEDIUM: 'warn',
  HIGH: 'bad',
};

/**
 * Evidence stream 1 — voice authenticity.
 *
 * Deliberately shows nothing about who is speaking or what they are asking for.
 * Those are separate streams; conflating them would let a suspicious request
 * masquerade as evidence of synthesis.
 */
export const AuthenticityPanel: React.FC<Props> = ({ authenticity }) => {
  if (!authenticity) {
    return (
      <PanelCard title="VOICE AUTHENTICITY">
        <Text style={styles.pending}>Awaiting sufficient audio…</Text>
      </PanelCard>
    );
  }

  const spoofPct = Math.round(authenticity.spoof_probability * 100);
  const tone = spoofPct >= 66 ? 'bad' : spoofPct >= 33 ? 'warn' : 'good';

  return (
    <PanelCard
      title="VOICE AUTHENTICITY"
      meta={`confidence ${Math.round(authenticity.confidence * 100)}%`}
      accent={tone === 'bad' ? colors.high : undefined}>
      <MetricRow
        label="Authenticity Score"
        value={`${authenticity.score}`}
        tone={tone}
        fraction={authenticity.score / 100}
      />
      <MetricRow
        label="Synthetic / Spoof Probability"
        value={`${spoofPct}%`}
        tone={tone}
        fraction={authenticity.spoof_probability}
      />
      <MetricRow
        label="Acoustic Anomaly"
        value={authenticity.acoustic_anomaly}
        tone={BAND_TONE[authenticity.acoustic_anomaly] ?? 'muted'}
      />
      <MetricRow
        label="Spectral Anomaly"
        value={authenticity.spectral_anomaly}
        tone={BAND_TONE[authenticity.spectral_anomaly] ?? 'muted'}
      />
      <MetricRow
        label="Prosody / Temporal Anomaly"
        value={authenticity.prosody_anomaly}
        tone={BAND_TONE[authenticity.prosody_anomaly] ?? 'muted'}
      />
      <MetricRow
        label="Detection Confidence"
        value={`${Math.round(authenticity.confidence * 100)}%`}
        tone="muted"
        fraction={authenticity.confidence}
      />
      {authenticity.is_mock ? (
        <Text style={styles.stub}>
          Heuristic DSP stub — not a trained deepfake model ({authenticity.model_version})
        </Text>
      ) : (
        <Text style={styles.stub}>
          {authenticity.model_name} · {authenticity.model_version} — pretrained,
          not evaluated on this channel
        </Text>
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  pending: { color: colors.textMuted, fontSize: 13, fontStyle: 'italic' },
  stub: { color: colors.textMuted, fontSize: 10, marginTop: 2, lineHeight: 14 },
});
