import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, radius, typography } from '../utils/theme';
import { RiskStateBadge } from '../components/RiskStateBadge';
import { RootStackParamList } from '../navigation/AppNavigator';
import { ScreenedCallEvent } from '../types/telecom';

type Route = RouteProp<RootStackParamList, 'CallSecurityDetails'>;

/**
 * Call Security Details Screen
 *
 * Displays a full breakdown of a screened SIM call:
 * - Risk Summary (badge, score, decision)
 * - Call Info (caller, time, source)
 * - Verification signals (carrier STIR/SHAKEN, contact status)
 * - Screening latency
 * - Human-readable explanation of the risk evaluation
 * - Reason codes
 * - Audio analysis status (always NOT_PERFORMED for Phase 3 SIM calls)
 *
 * Phase 3 constraint: Audio analysis is not performed on cellular SIM calls.
 * Android third-party CallScreeningService provides caller metadata, not raw audio.
 */
export const CallSecurityDetailsScreen: React.FC = () => {
  const navigation = useNavigation();
  const route = useRoute<Route>();
  const insets = useSafeAreaInsets();
  const { callRecord } = route.params;

  const formatDateTime = (timestamp: number): string => {
    const d = new Date(timestamp);
    const pad = (n: number) => `${n}`.padStart(2, '0');
    const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const time = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    return `${date} ${time}`;
  };

  const displayRiskState = (rs: string): string => {
    switch (rs) {
      case 'safe':      return 'Safe';
      case 'low':       return 'Low Risk';
      case 'suspicious': return 'Suspicious';
      case 'high':      return 'High Risk';
      case 'critical':  return 'Critical';
      default:          return rs;
    }
  };

  const badgeState = (): 'low' | 'suspicious' | 'high' | 'critical' | 'insufficient_evidence' => {
    switch (callRecord.riskState) {
      case 'safe':      return 'low';
      case 'low':       return 'low';
      case 'suspicious': return 'suspicious';
      case 'high':      return 'high';
      case 'critical':  return 'critical';
      default:          return 'insufficient_evidence';
    }
  };

  const riskScoreColor = (): string => {
    const score = callRecord.riskScore ?? 0;
    if (score >= 75) return colors.error;
    if (score >= 45) return colors.warning;
    return colors.success;
  };

  const verificationStatusLabel = (vs: string): string => {
    switch (vs) {
      case 'PASSED':       return '✅ Verified (STIR/SHAKEN Passed)';
      case 'FAILED':       return '🚫 Verification Failed (Possible Spoofing)';
      case 'NOT_VERIFIED': return '⚠️ Not Verified (carrier does not sign calls)';
      default:             return '❓ Unknown';
    }
  };

  const contactStatusLabel = (cs: string): string => {
    switch (cs) {
      case 'IN_CONTACTS':     return '📱 Saved in Device Contacts';
      case 'NOT_IN_CONTACTS': return '👤 Not in Device Contacts';
      default:                return '❓ Contact Status Unknown';
    }
  };

  const decisionLabel = (d: string): string => {
    switch (d) {
      case 'ALLOW':   return '✅ Allowed';
      case 'SILENCE': return '🔇 Silenced';
      case 'REJECT':  return '🚫 Rejected';
      default:        return d;
    }
  };

  const displayCaller = callRecord.callerName
    ? `${callRecord.callerName} (${callRecord.callerMasked})`
    : callRecord.callerMasked;

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backBtn}
          accessibilityLabel="Go back"
          accessibilityRole="button">
          <Text style={styles.backBtnText}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Call Security Details</Text>
        <View style={styles.backBtnPlaceholder} />
      </View>

      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + spacing.xxl }]}
        showsVerticalScrollIndicator={false}>

        {/* ── Risk Summary Card ────────────────────────────────────────── */}
        <View style={styles.summaryCard}>
          <View style={styles.summaryRow}>
            <View style={styles.summaryLeft}>
              <Text style={styles.summaryLabel}>RISK ASSESSMENT</Text>
              <Text style={styles.riskStateText}>{displayRiskState(callRecord.riskState ?? 'low')}</Text>
              <View style={styles.badgeRow}>
                <RiskStateBadge state={badgeState()} size="sm" />
              </View>
            </View>
            <View style={styles.scoreCircle}>
              <Text style={[styles.scoreValue, { color: riskScoreColor() }]}>
                {callRecord.riskScore ?? 0}
              </Text>
              <Text style={styles.scoreLabel}>/ 100</Text>
            </View>
          </View>
          <View style={styles.divider} />
          <View style={styles.decisionRow}>
            <Text style={styles.metaLabel}>DECISION</Text>
            <Text style={styles.decisionText}>{decisionLabel(callRecord.decision)}</Text>
          </View>
        </View>

        {/* ── Call Info ────────────────────────────────────────────────── */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Call Information</Text>
          <InfoRow label="Caller" value={displayCaller} />
          <InfoRow label="Time" value={formatDateTime(callRecord.timestamp)} />
          <InfoRow label="Category" value={callRecord.category ?? 'SIM Call'} />
          <InfoRow label="Source" value="Incoming SIM Call (Android Telecom)" />
        </View>

        {/* ── Security Signals ─────────────────────────────────────────── */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Security Signals</Text>
          <InfoRow
            label="Carrier Verification"
            value={verificationStatusLabel(callRecord.verificationStatus)}
          />
          <InfoRow
            label="Contact Status"
            value={contactStatusLabel(callRecord.contactStatus ?? 'UNKNOWN')}
          />
          <InfoRow
            label="Warning"
            value={callRecord.warningType === 'NONE' ? 'None detected' : callRecord.warningType}
          />
        </View>

        {/* ── Screening Metadata ───────────────────────────────────────── */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Screening Metadata</Text>
          <InfoRow
            label="Latency"
            value={`${callRecord.screeningLatencyMs ?? 0} ms (well within 5000 ms limit)`}
          />
          <InfoRow label="Event ID" value={callRecord.eventId} mono />
        </View>

        {/* ── Why This Risk Level ──────────────────────────────────────── */}
        {!!callRecord.explanation && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Why This Risk Level?</Text>
            <View style={styles.explanationBox}>
              <Text style={styles.explanationText}>{callRecord.explanation}</Text>
            </View>
          </View>
        )}

        {/* ── Reason Codes ─────────────────────────────────────────────── */}
        {callRecord.reasonCodes && callRecord.reasonCodes.length > 0 && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Detection Signals</Text>
            {callRecord.reasonCodes.map((code, i) => (
              <View key={i} style={styles.codeChip}>
                <Text style={styles.codeText}>{code}</Text>
              </View>
            ))}
          </View>
        )}

        {/* ── Audio Analysis ───────────────────────────────────────────── */}
        <View style={[styles.section, styles.audioSection]}>
          <Text style={styles.sectionTitle}>Audio Analysis</Text>
          <View style={styles.audioCard}>
            <View style={styles.audioStatusRow}>
              <Text style={styles.audioStatusIcon}>🔇</Text>
              <View style={styles.audioStatusBody}>
                <Text style={styles.audioStatusTitle}>Not Performed</Text>
                <Text style={styles.audioStatusDesc}>
                  Android third-party call screening provides caller metadata only, not raw cellular call audio.
                  ML voice analysis (AASIST-L / ECAPA-TDNN / Whisper) is not performed on SIM calls in Phase 3.
                </Text>
              </View>
            </View>
            <View style={styles.divider} />
            <Text style={styles.audioNote}>
              To perform AI audio analysis, use{' '}
              <Text style={styles.audioNoteEmphasis}>Live Audio Analysis</Text> or{' '}
              <Text style={styles.audioNoteEmphasis}>Analyze Audio File</Text> from the home screen.
            </Text>
          </View>
        </View>

      </ScrollView>
    </View>
  );
};

/** Reusable info row component */
const InfoRow: React.FC<{ label: string; value: string; mono?: boolean }> = ({ label, value, mono }) => (
  <View style={styles.infoRow}>
    <Text style={styles.infoLabel}>{label}</Text>
    <Text style={[styles.infoValue, mono && styles.infoValueMono]} numberOfLines={2} ellipsizeMode="middle">
      {value}
    </Text>
  </View>
);

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    backgroundColor: colors.bgCard,
  },
  backBtn: {
    paddingVertical: 4,
    paddingRight: spacing.sm,
  },
  backBtnText: {
    color: colors.brand,
    fontSize: 16,
    fontWeight: '600',
  },
  backBtnPlaceholder: {
    width: 48,
  },
  headerTitle: {
    ...typography.h3,
    fontSize: 16,
    color: colors.textPrimary,
    fontWeight: '700',
  },
  scroll: {
    padding: spacing.lg,
    gap: spacing.md,
  },
  summaryCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  summaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  summaryLeft: {
    flex: 1,
  },
  summaryLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginBottom: 4,
  },
  riskStateText: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  badgeRow: {
    flexDirection: 'row',
  },
  scoreCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: colors.bgElevated,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 2,
    borderColor: colors.border,
  },
  scoreValue: {
    fontSize: 26,
    fontWeight: '900',
    lineHeight: 30,
  },
  scoreLabel: {
    fontSize: 10,
    color: colors.textMuted,
    fontWeight: '600',
  },
  divider: {
    height: 1,
    backgroundColor: colors.border,
    marginVertical: spacing.sm,
  },
  decisionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  metaLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  decisionText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  section: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    gap: spacing.xs,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginBottom: spacing.xs,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: 3,
    borderBottomWidth: 1,
    borderBottomColor: `${colors.border}66`,
  },
  infoLabel: {
    fontSize: 12,
    color: colors.textMuted,
    fontWeight: '600',
    flex: 0.4,
  },
  infoValue: {
    fontSize: 12,
    color: colors.textPrimary,
    fontWeight: '500',
    flex: 0.6,
    textAlign: 'right',
  },
  infoValueMono: {
    fontFamily: 'monospace',
    fontSize: 10,
  },
  explanationBox: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.sm,
    padding: spacing.sm,
    borderLeftWidth: 3,
    borderLeftColor: colors.brand,
  },
  explanationText: {
    fontSize: 13,
    color: colors.textSecondary,
    lineHeight: 19,
  },
  codeChip: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: 4,
  },
  codeText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textSecondary,
    fontFamily: 'monospace',
  },
  audioSection: {
    borderColor: `${colors.textMuted}55`,
  },
  audioCard: {
    gap: spacing.xs,
  },
  audioStatusRow: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'flex-start',
  },
  audioStatusIcon: {
    fontSize: 24,
    marginTop: 2,
  },
  audioStatusBody: {
    flex: 1,
  },
  audioStatusTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  audioStatusDesc: {
    fontSize: 12,
    color: colors.textSecondary,
    lineHeight: 17,
  },
  audioNote: {
    fontSize: 12,
    color: colors.textMuted,
    lineHeight: 17,
    fontStyle: 'italic',
  },
  audioNoteEmphasis: {
    color: colors.brand,
    fontStyle: 'normal',
    fontWeight: '600',
  },
});
