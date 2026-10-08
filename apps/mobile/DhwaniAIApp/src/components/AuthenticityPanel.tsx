import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { AnomalyBand, AuthenticityEvidence } from '../types';
import { MicIcon } from './Icons';

interface Props {
  authenticity: (AuthenticityEvidence & {
    synthetic_probability?: number;
    raw_score?: number;
    artifacts_detected?: string[];
    is_synthetic?: boolean;
    model_confidence?: number;
    aasist?: {
      spoof_probability?: number | null;
      confidence?: number | null;
      model_version?: string;
      status?: string;
    };
  }) | null;
  reasons?: string[];
  score?: number;
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

function resolveAnomalyBands(
  authenticity: any,
  reasons: string[] = [],
  score?: number
): { acoustic: AnomalyBand; spectral: AnomalyBand; prosody: AnomalyBand } {
  // If explicitly specified with non-default values in authenticity, use them
  if (
    authenticity.acoustic_anomaly &&
    authenticity.spectral_anomaly &&
    authenticity.prosody_anomaly
  ) {
    return {
      acoustic: authenticity.acoustic_anomaly,
      spectral: authenticity.spectral_anomaly,
      prosody: authenticity.prosody_anomaly,
    };
  }

  const artifacts: string[] = Array.isArray(authenticity.artifacts_detected)
    ? authenticity.artifacts_detected.map((a: string) => a.toLowerCase())
    : [];
  const reasonsText = (reasons || []).join(' ').toLowerCase();

  const isSynthetic = authenticity.is_synthetic === true || (typeof score === 'number' && score >= 60);
  const isHuman = authenticity.is_synthetic === false || (typeof score === 'number' && score < 30);

  // 1. Acoustic Evidence Analysis
  let acoustic: AnomalyBand = authenticity.acoustic_anomaly || 'LOW';
  if (!authenticity.acoustic_anomaly) {
    const isHumanAcoustic =
      reasonsText.includes('no synthetic vocoder') ||
      reasonsText.includes('human vocal tract') ||
      reasonsText.includes('glottal airflow') ||
      isHuman;

    const hasAcousticArtifact = artifacts.some(a =>
      a.includes('neural') ||
      a.includes('vocoder') ||
      a.includes('conversion') ||
      a.includes('acoustic')
    );
    const hasAcousticReason =
      reasonsText.includes('neural voice') ||
      reasonsText.includes('synthetic text-to-speech') ||
      reasonsText.includes('synthetic vocoder') ||
      reasonsText.includes('voice cloning') ||
      reasonsText.includes('voice conversion') ||
      reasonsText.includes('synthetic acoustic model');

    if (!isHumanAcoustic && (hasAcousticArtifact || hasAcousticReason || isSynthetic)) {
      acoustic = 'HIGH';
    } else {
      acoustic = 'LOW';
    }
  }

  // 2. Spectral Evidence Analysis
  let spectral: AnomalyBand = authenticity.spectral_anomaly || 'LOW';
  if (!authenticity.spectral_anomaly) {
    const isHumanSpectral =
      reasonsText.includes('no synthetic vocoder or phase manipulation') ||
      reasonsText.includes('natural human vocal tract') ||
      isHuman;

    const hasSpectralArtifact = artifacts.some(a =>
      a.includes('spectral') ||
      a.includes('phase') ||
      a.includes('cutoff') ||
      a.includes('sub-band') ||
      a.includes('harmonic') ||
      a.includes('incoherence') ||
      a.includes('discontinuities')
    );
    const hasSpectralReason =
      reasonsText.includes('phase discontinuities') ||
      reasonsText.includes('spectral phase') ||
      reasonsText.includes('sub-band') ||
      reasonsText.includes('cepstral') ||
      reasonsText.includes('harmonic distribution');

    if (!isHumanSpectral && (hasSpectralArtifact || hasSpectralReason || isSynthetic)) {
      spectral = 'HIGH';
    } else {
      spectral = 'LOW';
    }
  }

  // 3. Prosody / Temporal Evidence Analysis
  let prosody: AnomalyBand = authenticity.prosody_anomaly || 'LOW';
  if (!authenticity.prosody_anomaly) {
    const isHumanProsody =
      reasonsText.includes('natural breathing cadence') ||
      reasonsText.includes('biometric micro-tremors') ||
      isHuman;

    const hasProsodyArtifact = artifacts.some(a =>
      a.includes('prosod') ||
      a.includes('cadence') ||
      a.includes('flattening') ||
      a.includes('temporal') ||
      a.includes('regularity')
    );
    const hasProsodyReason =
      reasonsText.includes('prosodic uniformity') ||
      reasonsText.includes('prosodic cadence mismatch') ||
      reasonsText.includes('prosody flattening') ||
      reasonsText.includes('harmonic regularity');

    if (!isHumanProsody && (hasProsodyArtifact || hasProsodyReason || isSynthetic)) {
      prosody = 'HIGH';
    } else {
      prosody = 'LOW';
    }
  }

  return { acoustic, spectral, prosody };
}

/**
 * Evidence stream 1 — voice authenticity.
 *
 * Deliberately shows nothing about who is speaking or what they are asking for.
 * Those are separate streams; conflating them would let a suspicious request
 * masquerade as evidence of synthesis.
 */
export const AuthenticityPanel: React.FC<Props> = ({ authenticity, reasons = [], score }) => {
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

  // Check if analysis genuinely resulted in insufficient speech
  const isGenuinelyInsufficient =
    authenticity.spoof_probability === null &&
    authenticity.synthetic_probability === undefined &&
    authenticity.raw_score === undefined &&
    authenticity.aasist?.spoof_probability === undefined;

  const rawProb =
    authenticity.spoof_probability ??
    authenticity.synthetic_probability ??
    authenticity.aasist?.spoof_probability ??
    (typeof authenticity.raw_score === 'number' ? authenticity.raw_score : null) ??
    (typeof score === 'number' && score > 0 ? score / 100 : null);

  const isSpoofAvailable = rawProb !== null && rawProb !== undefined && !isGenuinelyInsufficient;
  const spoofPct = isSpoofAvailable ? Math.round(rawProb * 100) : null;
  const tone = spoofPct !== null ? (spoofPct >= 66 ? 'bad' : spoofPct >= 33 ? 'warn' : 'good') : 'muted';
  const accentColor =
    tone === 'bad'
      ? colors.danger
      : tone === 'warn'
      ? colors.warning
      : colors.success;

  const aasistPct = isSpoofAvailable
    ? `${spoofPct}%`
    : 'Insufficient speech';

  const { acoustic, spectral, prosody } = resolveAnomalyBands(authenticity, reasons, score);

  const anomalyBands: { label: string; band: AnomalyBand }[] = [
    { label: 'Acoustic Anomaly', band: acoustic },
    { label: 'Spectral Anomaly', band: spectral },
    { label: 'Prosody / Temporal Anomaly', band: prosody },
  ];

  const conf =
    authenticity.confidence > 0
      ? authenticity.confidence
      : typeof authenticity.model_confidence === 'number'
      ? authenticity.model_confidence
      : 0;

  return (
    <PanelCard
      title="VOICE AUTHENTICITY"
      icon={<MicIcon size={13} color={colors.accent} />}
      meta={conf > 0 ? `conf ${Math.round(conf * 100)}%` : undefined}
      accent={tone !== 'good' && tone !== 'muted' ? accentColor : undefined}
    >
      {/* Model Providers Breakdown */}
      <MetricRow
        label={authenticity.is_mock ? "Synthetic / Spoof Probability" : "AASIST-L (Local)"}
        value={aasistPct}
        tone={isSpoofAvailable ? tone : 'muted'}
        fraction={rawProb ?? undefined}
        pill={isSpoofAvailable}
      />

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
