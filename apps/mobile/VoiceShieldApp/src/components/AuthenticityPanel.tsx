import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { AnomalyBand, AuthenticityEvidence } from '../types';
import { MicIcon } from './Icons';

interface Props {
  authenticity: AuthenticityEvidence | null;
}

const BAND_TONE: Record<AnomalyBand, 'good' | 'warn' | 'bad'> = {
  LOW: 'good',
  MEDIUM: 'warn',
  HIGH: 'bad',
};

const BAND_ICON: Record<AnomalyBand, string> = {
  LOW: '✓',
  MEDIUM: '⚡',
  HIGH: '⚠',
};

/**
 * Evidence stream 1 — voice authenticity.
 *
 * Deliberately shows nothing about who is speaking or what they are asking for.
 * Those are separate streams; conflating them would let a suspicious request
 * masquerade as evidence of synthesis.
 */
export const AuthenticityPanel: React.FC<Props> = ({ authenticity }) => {
  const { colors } = useTheme();

  if (!authenticity) {
    return (
      <PanelCard
        title="VOICE AUTHENTICITY"
        icon={<MicIcon size={13} color={colors.accent} />}
      >
        <Text style={[styles.pending, { color: colors.textMuted }]}>
          Awaiting sufficient audio…
        </Text>
      </PanelCard>
    );
  }

  const spoofProb = authenticity.spoof_probability;
  const isSpoofAvailable = spoofProb !== null && spoofProb !== undefined;
  const spoofPct = isSpoofAvailable ? Math.round(spoofProb * 100) : null;
  const tone = spoofPct !== null ? (spoofPct >= 66 ? 'bad' : spoofPct >= 33 ? 'warn' : 'good') : 'muted';
  const accentColor =
    tone === 'bad'
      ? colors.danger
      : tone === 'warn'
      ? colors.warning
      : colors.success;

  const modulate = (authenticity as any).modulate;
  const aasist = (authenticity as any).aasist;

  const modulateStatus = modulate?.provider_status || 'not_configured';
  const modulatePct = modulate?.synthetic_probability != null
    ? `${Math.round(modulate.synthetic_probability * 100)}%`
    : (modulateStatus === 'not_configured' ? 'Not configured' : 'Unavailable');

  const aasistPct = isSpoofAvailable
    ? `${spoofPct}%`
    : 'Insufficient speech';

  const anomalyBands: { label: string; band: AnomalyBand }[] = [
    { label: 'Acoustic Anomaly', band: authenticity.acoustic_anomaly || 'LOW' },
    { label: 'Spectral Anomaly', band: authenticity.spectral_anomaly || 'LOW' },
    { label: 'Prosody / Temporal Anomaly', band: authenticity.prosody_anomaly || 'LOW' },
  ];

  return (
    <PanelCard
      title="VOICE AUTHENTICITY"
      icon={<MicIcon size={13} color={colors.accent} />}
      meta={authenticity.confidence > 0 ? `conf ${Math.round(authenticity.confidence * 100)}%` : undefined}
      accent={tone !== 'good' && tone !== 'muted' ? accentColor : undefined}
    >
      {/* Model Providers Breakdown */}
      <MetricRow
        label={authenticity.is_mock ? "Synthetic / Spoof Probability" : "AASIST-L (Local)"}
        value={aasistPct}
        tone={isSpoofAvailable ? tone : 'muted'}
        fraction={spoofProb ?? undefined}
        pill={isSpoofAvailable}
      />
      {!authenticity.is_mock && (
        <MetricRow
          label="Modulate Velma-2"
          value={modulatePct}
          tone={modulate?.synthetic_probability != null ? (modulate.synthetic_probability >= 0.65 ? 'bad' : 'good') : 'muted'}
          fraction={modulate?.synthetic_probability ?? undefined}
          pill={modulate?.synthetic_probability != null}
        />
      )}

      {/* Anomaly band trio */}
      <View style={styles.bandRow}>
        {anomalyBands.map(({ label, band }) => {
          const t = BAND_TONE[band] ?? 'muted';
          const bandColor =
            t === 'good'
              ? colors.success
              : t === 'warn'
              ? colors.warning
              : colors.danger;
          return (
            <View
              key={label}
              style={[
                styles.bandChip,
                {
                  backgroundColor: `${bandColor}18`,
                  borderColor: `${bandColor}40`,
                },
              ]}
            >
              <Text style={[styles.bandIcon, { color: bandColor }]}>
                {BAND_ICON[band]}
              </Text>
              <Text style={[styles.bandLabel, { color: colors.textSecondary }]}>
                {label.split(' ')[0]}
              </Text>
              <Text style={[styles.bandValue, { color: bandColor }]}>
                {band}
              </Text>
              {/* Hidden label for accessibility and full text match */}
              <Text style={{ display: 'none' }}>{label}</Text>
            </View>
          );
        })}
      </View>

      {/* Model footer */}
      <Text style={[styles.stub, { color: colors.textMuted }]}>
        {authenticity.is_mock
          ? `Heuristic DSP stub · not a trained deepfake model · ${authenticity.model_version}`
          : `${authenticity.model_name || 'AASIST-L'} · ${authenticity.model_version || 'AASIST-L+cascade'} — pretrained, not evaluated on this channel`}
      </Text>
    </PanelCard>
  );
};


const styles = StyleSheet.create({
  pending: { fontSize: 13, fontStyle: 'italic' },
  bandRow: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 4,
  },
  bandChip: {
    flex: 1,
    borderRadius: 8,
    borderWidth: 1,
    paddingVertical: 6,
    paddingHorizontal: 4,
    alignItems: 'center',
    gap: 2,
  },
  bandIcon: { fontSize: 13 },
  bandLabel: { fontSize: 9, fontWeight: '600', letterSpacing: 0.2, textAlign: 'center' },
  bandValue: { fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  stub: { fontSize: 10, marginTop: 2, lineHeight: 14 },
});
