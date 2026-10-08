import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { MetricRow } from './MetricRow';
import { useTheme } from '../utils/theme';
import { ContextEvidence } from '../types';

interface Props {
  context?: ContextEvidence | null;
  score?: number;
  riskState?: string;
  threatLevel?: string;
  transactionConsequence?: string;
  authenticity?: any;
  identity?: any;
  reasons?: string[];
}

const CONSEQUENCE_TONE: Record<string, 'good' | 'warn' | 'bad'> = {
  LOW: 'good',
  MEDIUM: 'warn',
  HIGH: 'bad',
  CRITICAL: 'bad',
  low: 'good',
  medium: 'warn',
  high: 'bad',
  critical: 'bad',
};

type ThreatEntry = { label: string; icon: string };

/**
 * Evidence stream 4 — Consequences & Threat Classification.
 * Surfaces real financial, credential, urgency, authority, and impersonation
 * threat detection, as well as forensic authenticity & voice cloning signals.
 * Never fabricates data.
 */
export const ConsequencesPanel: React.FC<Props> = ({
  context,
  score,
  riskState,
  threatLevel: propThreatLevel,
  transactionConsequence: propTransactionConsequence,
  authenticity,
  identity,
  reasons,
}) => {
  const { colors } = useTheme();

  // Effective score priority: explicit prop score > context.score
  const effectiveScore: number | undefined =
    typeof score === 'number'
      ? score
      : typeof context?.score === 'number'
      ? context.score
      : undefined;

  // If neither transcript nor valid score is available, show pending state
  if ((!context || !context.transcript) && typeof effectiveScore !== 'number') {
    return (
      <PanelCard title="CONSEQUENCES & THREATS" icon="🛡" meta="speech context">
        <MetricRow label="Consequence Level" value="Insufficient Evidence" tone="muted" pill />
        <Text style={[styles.pending, { color: colors.textMuted }]}>
          Consequence analysis requires transcribed speech. No threat is assumed
          until context is evaluated.
        </Text>
      </PanelCard>
    );
  }

  // ── Score-driven severity mapping for Consequences & Threats ──────────────
  // 0–29   → LOW
  // 30–59  → MEDIUM
  // 60–79  → HIGH
  // 80–100 → CRITICAL
  let threatLevel: string;
  let consequenceLevel: string;

  if (propThreatLevel) {
    threatLevel = propThreatLevel.toUpperCase();
  } else if (typeof effectiveScore === 'number') {
    if (effectiveScore >= 80) {
      threatLevel = 'CRITICAL';
    } else if (effectiveScore >= 60) {
      threatLevel = 'HIGH';
    } else if (effectiveScore >= 30) {
      threatLevel = 'MEDIUM';
    } else {
      threatLevel = 'LOW';
    }
  } else if (context?.consequence) {
    threatLevel = context.consequence.toUpperCase();
  } else {
    threatLevel = 'LOW';
  }

  if (propTransactionConsequence) {
    consequenceLevel = propTransactionConsequence.toUpperCase();
  } else if (typeof effectiveScore === 'number') {
    // Both 93 and 73 (>= 60) map to HIGH for Transaction Consequence
    if (effectiveScore >= 60) {
      consequenceLevel = 'HIGH';
    } else if (effectiveScore >= 30) {
      consequenceLevel = 'MEDIUM';
    } else {
      consequenceLevel = 'LOW';
    }
  } else if (context?.consequence) {
    consequenceLevel = context.consequence.toUpperCase();
  } else {
    consequenceLevel = 'LOW';
  }

  const threatTone = CONSEQUENCE_TONE[threatLevel] ?? 'good';
  const consequenceTone = CONSEQUENCE_TONE[consequenceLevel] ?? 'good';

  // ── Derive active threat signals from available evidence ──────────────────
  const detectedThreats: ThreatEntry[] = [];
  const seenLabels = new Set<string>();

  const addThreat = (label: string, icon: string) => {
    if (!seenLabels.has(label)) {
      seenLabels.add(label);
      detectedThreats.push({ label, icon });
    }
  };

  // 1. Context behavioral flags (transcript / conversation intent)
  if (context?.otp_request) addThreat('OTP / 2FA Request', '🔑');
  if (context?.credential_request) addThreat('Password / Credentials', '🔐');
  if (context?.financial_request) addThreat('Bank / Money / UPI Transfer', '💸');
  if (context?.sensitive_information_request) addThreat('KYC / Card / Personal Data', '📋');
  if (context?.authority_claim) addThreat('Authority Impersonation', '🚨');
  if (context?.urgency) addThreat('Artificial Urgency / Panic', '⏱');
  if (context?.social_engineering) addThreat('Social Engineering Pattern', '⚡');

  // Check intent_flag if present on context
  const contextAny = context as any;
  if (contextAny?.intent_flag) {
    const intent = String(contextAny.intent_flag).toUpperCase();
    if (intent.includes('URGENCY')) addThreat('Artificial Urgency / Panic', '⏱');
    if (intent.includes('FINANCIAL')) addThreat('Bank / Money / UPI Transfer', '💸');
    if (intent.includes('IMPERSONATION') || intent.includes('FRAUD')) addThreat('Authority Impersonation', '🚨');
  }

  // 2. Synthetic / AI-generated voice detection
  const isSynthetic =
    authenticity?.is_synthetic === true ||
    (typeof authenticity?.synthetic_probability === 'number' && authenticity.synthetic_probability >= 0.6) ||
    (typeof authenticity?.spoof_probability === 'number' && authenticity.spoof_probability >= 0.6) ||
    (authenticity?.is_synthetic !== false &&
      effectiveScore !== undefined && effectiveScore >= 60 &&
      Array.isArray(reasons) &&
      reasons.some((r: string) => /(?:high probability|confidence|detected).*synthetic|synthetic.*detected|elevenlabs/i.test(r)));

  if (isSynthetic) {
    addThreat('Synthetic / AI-Generated Voice', '🤖');
  }

  // 3. Voice cloning indicators
  const hasCloning =
    (Array.isArray(authenticity?.artifacts_detected) && authenticity.artifacts_detected.length > 0) ||
    (authenticity?.is_synthetic !== false &&
      effectiveScore !== undefined && effectiveScore >= 60 &&
      Array.isArray(reasons) &&
      reasons.some((r: string) => /(?:clon|vocoder|phase).*detected|indicators detected|characteristics of.*clone/i.test(r)));

  if (hasCloning) {
    addThreat('Voice Cloning Indicators', '🧬');
  }

  // 4. Authenticity anomaly
  const hasAnomaly =
    (typeof authenticity?.raw_score === 'number' && authenticity.raw_score >= 0.6) ||
    (typeof authenticity?.score === 'number' && authenticity.score >= 60) ||
    (typeof authenticity?.synthetic_probability === 'number' && authenticity.synthetic_probability >= 0.7) ||
    (typeof authenticity?.spoof_probability === 'number' && authenticity.spoof_probability >= 0.7) ||
    authenticity?.acoustic_anomaly === 'HIGH' ||
    authenticity?.acoustic_anomaly === 'CRITICAL' ||
    (authenticity?.is_synthetic !== false &&
      effectiveScore !== undefined && effectiveScore >= 60 &&
      Array.isArray(reasons) &&
      reasons.some((r: string) => /anomaly detected|spectral discontinuities|phase discontinuities/i.test(r)));

  if (hasAnomaly) {
    addThreat('Authenticity Anomaly', '⚠️');
  }

  // 5. Speaker mismatch
  const hasSpeakerMismatch =
    identity &&
    (identity.speaker_match === false ||
     identity.enrollment_status === 'MISMATCH' ||
     (typeof identity.similarity_score === 'number' && identity.similarity_score < 0.6) ||
     (typeof identity.similarity === 'number' && identity.similarity < 0.6) ||
     (Array.isArray(reasons) && reasons.some((r: string) => /speaker mismatch|different speaker|identity spoof/i.test(r))));

  if (hasSpeakerMismatch) {
    addThreat('Speaker Mismatch', '👤');
  }

  // 6. Generic high-risk signal fallback if high risk but no specific signals
  if (typeof effectiveScore === 'number' && effectiveScore >= 60 && detectedThreats.length === 0) {
    addThreat('High-risk voice authenticity result', '⚠️');
  }

  const hasHighThreat =
    threatLevel === 'CRITICAL' ||
    threatLevel === 'HIGH' ||
    consequenceLevel === 'HIGH' ||
    consequenceLevel === 'CRITICAL';

  const accentColor = hasHighThreat
    ? colors.danger
    : threatLevel === 'MEDIUM' || consequenceLevel === 'MEDIUM' || detectedThreats.length > 0
    ? colors.warning
    : undefined;

  return (
    <PanelCard
      title="CONSEQUENCES & THREATS"
      icon="🛡"
      meta={`level ${threatLevel}`}
      accent={accentColor}
    >
      {/* Consequence level + threat score */}
      <MetricRow
        label="Threat Level"
        value={threatLevel}
        tone={threatTone}
        pill
      />
      <MetricRow
        label="Transaction Consequence"
        value={consequenceLevel}
        tone={consequenceTone}
        pill
      />
      <MetricRow
        label="Context Threat Score"
        value={
          typeof effectiveScore === 'number'
            ? `${effectiveScore} / 100`
            : '0 / 100'
        }
        tone={
          typeof effectiveScore === 'number'
            ? effectiveScore >= 60
              ? 'bad'
              : effectiveScore >= 30
              ? 'warn'
              : 'good'
            : 'good'
        }
        fraction={typeof effectiveScore === 'number' ? effectiveScore / 100 : 0}
      />

      {/* Threat classification summary */}
      <MetricRow
        label="Active Threat Signals"
        value={
          detectedThreats.length > 0
            ? `${detectedThreats.length} Signal${detectedThreats.length > 1 ? 's' : ''}`
            : 'None Detected'
        }
        tone={detectedThreats.length > 0 ? 'bad' : 'good'}
        pill
      />

      {/* Individual threat chips */}
      {detectedThreats.length > 0 && (
        <View style={styles.threatGrid}>
          {detectedThreats.map((threat, idx) => (
            <View
              key={idx}
              style={[
                styles.threatChip,
                {
                  backgroundColor: `${colors.danger}14`,
                  borderColor: `${colors.danger}35`,
                },
              ]}
            >
              <Text style={styles.threatIcon}>{threat.icon}</Text>
              <Text style={[styles.threatText, { color: colors.danger }]}>
                {threat.label}
              </Text>
            </View>
          ))}
        </View>
      )}

      {/* Detected phrases */}
      {context?.detected_phrases && context.detected_phrases.length > 0 && (
        <View style={styles.phrasesRow}>
          <Text style={[styles.phrasesLabel, { color: colors.textMuted }]}>
            Trigger phrases:{' '}
          </Text>
          <Text style={[styles.phrasesValue, { color: colors.textSecondary }]}>
            {context.detected_phrases.join(', ')}
          </Text>
        </View>
      )}

      {/* Transcript quote */}
      {!!context?.transcript && (
        <View
          style={[
            styles.transcriptBlock,
            {
              backgroundColor: `${colors.accent}0D`,
              borderLeftColor: accentColor ?? colors.accent,
            },
          ]}
        >
          <Text
            style={[styles.transcriptQuote, { color: colors.textSecondary }]}
            numberOfLines={3}
          >
            {`"${context.transcript}"`}
          </Text>
        </View>
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  pending: { fontSize: 12, fontStyle: 'italic', marginTop: 4, lineHeight: 16 },
  threatGrid: { marginTop: 4, gap: 5 },
  threatChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderWidth: 1,
  },
  threatIcon: { fontSize: 13 },
  threatText: { fontSize: 12, fontWeight: '700', flex: 1 },
  phrasesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 4,
  },
  phrasesLabel: { fontSize: 11, fontWeight: '600' },
  phrasesValue: { fontSize: 11, fontStyle: 'italic', flex: 1 },
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
});
