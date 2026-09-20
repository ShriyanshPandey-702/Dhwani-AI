import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing, radius, typography } from '../utils/theme';
import { analyzeAudioFile } from '../services/api/client';
import { RiskGauge } from '../components/RiskGauge';
import { DecisionPanel } from '../components/DecisionPanel';
import { AuthenticityPanel } from '../components/AuthenticityPanel';
import { IdentityPanel } from '../components/IdentityPanel';
import { ContextPanel } from '../components/ContextPanel';
import { RiskStateBadge } from '../components/RiskStateBadge';
import { RiskState, Decision } from '../types';

export const ManualAnalysisScreen: React.FC = () => {
  const insets = useSafeAreaInsets();
  const [analyzing, setAnalyzing] = useState(false);
  const [report, setReport] = useState<any>(null);

  const handleAnalyzeSample = async (sampleType: 'synthetic' | 'benign' | 'short') => {
    setAnalyzing(true);
    setReport(null);

    try {
      const formData = new FormData();

      if (sampleType === 'short') {
        formData.append('file', {
          uri: 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
          name: 'short_sample.wav',
          type: 'audio/wav',
        } as any);
      } else {
        formData.append('file', {
          uri: 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=',
          name: `${sampleType}_sample.wav`,
          type: 'audio/wav',
        } as any);
      }

      const data = await analyzeAudioFile(formData);
      setReport(data);
    } catch (err: any) {
      const msg = err?.response?.data?.detail?.message || err?.message || 'Analysis failed';
      Alert.alert('Analysis Error', msg);
    } finally {
      setAnalyzing(false);
    }
  };

  const riskState: RiskState = (report?.risk_state as RiskState) || 'insufficient_evidence';
  const decision: Decision = (report?.decision as Decision) || 'VERIFY';

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: insets.bottom + spacing.xl }]}>
        {/* Header Section */}
        <View style={styles.header}>
          <Text style={styles.title}>Manual Audio Analysis</Text>
          <Text style={styles.subtitle}>
            Upload or select an audio file to run deepfake detection, speaker identity verification, and context threat classification.
          </Text>
        </View>

        {/* Action Panel */}
        <View style={styles.actionCard}>
          <Text style={styles.cardTitle}>Select Audio Source</Text>
          <Text style={styles.cardDesc}>
            Run VoiceShield Core (AASIST-L + ECAPA-TDNN + Whisper) on pre-recorded audio:
          </Text>

          <TouchableOpacity
            style={[styles.btn, styles.btnPrimary]}
            onPress={() => handleAnalyzeSample('synthetic')}
            disabled={analyzing}>
            {analyzing ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <Text style={styles.btnText}>🧪 Analyze Deepfake Sample Audio</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.btn, styles.btnSecondary]}
            onPress={() => handleAnalyzeSample('benign')}
            disabled={analyzing}>
            <Text style={styles.btnSecondaryText}>🟢 Analyze Benign Human Audio</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.btn, styles.btnOutline]}
            onPress={() => handleAnalyzeSample('short')}
            disabled={analyzing}>
            <Text style={styles.btnOutlineText}>⏱ Test Short Audio Gate (&lt; 4.038s)</Text>
          </TouchableOpacity>
        </View>

        {/* Results Section */}
        {report && (
          <View style={styles.resultsContainer}>
            <View style={styles.resultHeader}>
              <Text style={styles.sectionTitle}>Analysis Report</Text>
              <RiskStateBadge state={riskState} size="md" />
            </View>

            <View style={styles.telemetryCard}>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>Status: </Text>
                <Text style={styles.metaValue}>{report.status.toUpperCase()}</Text>
              </Text>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>File: </Text>
                <Text style={styles.metaValue}>{report.filename}</Text>
              </Text>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>Duration: </Text>
                <Text style={styles.metaValue}>{report.duration_seconds.toFixed(2)}s</Text>
              </Text>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>Analysis Windows: </Text>
                <Text style={styles.metaValue}>{report.windows_evaluated}</Text>
              </Text>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>Processing Time: </Text>
                <Text style={styles.metaValue}>{report.processing_time_ms} ms</Text>
              </Text>
            </View>

            {/* Risk Gauge */}
            {report.analysis_completed && report.risk_score !== null && (
              <View style={styles.gaugeCard}>
                <RiskGauge
                  score={report.risk_score}
                  state={riskState}
                  trend="stable"
                />
              </View>
            )}

            {/* Decision Panel */}
            <DecisionPanel
              decision={decision}
              reasons={report.reasons || []}
              recommendedAction={report.recommended_action || ''}
              evidenceConfidence={report.evidence_confidence ?? 0.0}
            />

            {/* Authenticity Panel */}
            <AuthenticityPanel authenticity={report.authenticity || null} />

            {/* Identity Panel */}
            <IdentityPanel identity={report.identity || null} />

            {/* Context Panel */}
            <ContextPanel context={report.context || null} />

            {/* Window Timeline Breakdown */}
            {report.window_timeline && report.window_timeline.length > 0 && (
              <View style={styles.timelineCard}>
                <Text style={styles.cardTitle}>Window Breakdown (Exact 4038ms / 1000ms Hop)</Text>
                {report.window_timeline.map((w: any) => (
                  <View key={w.window_index} style={styles.windowRow}>
                    <Text style={styles.windowTime}>
                      W{w.window_index + 1} ({w.offset_ms / 1000}s)
                    </Text>
                    <Text style={styles.windowSpoof}>
                      Spoof: {(w.authenticity_spoof_prob * 100).toFixed(0)}%
                    </Text>
                    <Text style={styles.windowRisk}>
                      Risk: {w.window_risk_score}
                    </Text>
                    <RiskStateBadge state={w.window_risk_state as RiskState} size="sm" />
                  </View>
                ))}
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  scroll: {
    padding: spacing.md,
  },
  header: {
    marginBottom: spacing.md,
  },
  title: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  subtitle: {
    ...typography.body,
    color: colors.textSecondary,
    lineHeight: 20,
  },
  actionCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardTitle: {
    ...typography.h3,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  cardDesc: {
    ...typography.body,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  btn: {
    borderRadius: radius.sm,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  btnPrimary: {
    backgroundColor: colors.brand,
  },
  btnSecondary: {
    backgroundColor: colors.brandDim,
    borderWidth: 1,
    borderColor: colors.brand,
  },
  btnOutline: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.border,
  },
  btnText: {
    color: colors.white,
    fontWeight: '700',
    fontSize: 15,
  },
  btnSecondaryText: {
    color: colors.brand,
    fontWeight: '700',
    fontSize: 15,
  },
  btnOutlineText: {
    color: colors.textSecondary,
    fontWeight: '600',
    fontSize: 14,
  },
  resultsContainer: {
    marginTop: spacing.sm,
  },
  resultHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  sectionTitle: {
    ...typography.h3,
    color: colors.textPrimary,
  },
  telemetryCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  metaRow: {
    fontSize: 14,
    color: colors.textPrimary,
    marginBottom: 4,
  },
  metaLabel: {
    color: colors.textSecondary,
    fontWeight: '600',
  },
  metaValue: {
    fontWeight: '700',
    color: colors.textPrimary,
  },
  gaugeCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  timelineCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  windowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs + 2,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  windowTime: {
    fontSize: 13,
    color: colors.textSecondary,
    width: 90,
  },
  windowSpoof: {
    fontSize: 13,
    color: colors.textPrimary,
    fontWeight: '600',
  },
  windowRisk: {
    fontSize: 13,
    color: colors.textPrimary,
    fontWeight: '600',
  },
});
