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
import { analyzeAudioFile, formatApiError } from '../services/api/client';
import { callScreeningService } from '../services/telecom/callScreeningService';
import { AudioFileInfo } from '../types/telecom';
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
  const [selectedFile, setSelectedFile] = useState<AudioFileInfo | null>(null);
  const [report, setReport] = useState<any>(null);

  const handlePickAudioFile = async () => {
    try {
      const picked = await callScreeningService.pickAudioFile();
      if (picked) {
        setSelectedFile(picked);
      }
    } catch (err: any) {
      Alert.alert('File Picker Error', err?.message || 'Could not pick audio file.');
    }
  };

  const handleAnalyzeAudio = async (source: 'selected' | 'synthetic' | 'benign' | 'short') => {
    setAnalyzing(true);
    setReport(null);

    try {
      let audioTarget: AudioFileInfo;

      if (source === 'selected') {
        if (!selectedFile) {
          Alert.alert('No File Selected', 'Please choose an audio file from your device first.');
          setAnalyzing(false);
          return;
        }
        audioTarget = selectedFile;
      } else {
        try {
          audioTarget = await callScreeningService.getDemoAudioSample(source);
        } catch (err: any) {
          Alert.alert('Demo Sample Unavailable', 'Demo audio sample is unavailable.');
          setAnalyzing(false);
          return;
        }
      }

      const formData = new FormData();
      formData.append('file', {
        uri: audioTarget.uri,
        name: audioTarget.name,
        type: audioTarget.type || 'audio/wav',
      } as any);

      const data = await analyzeAudioFile(formData);
      setReport(data);
    } catch (err: any) {
      const errorMsg = formatApiError(err);
      Alert.alert('Analysis Error', errorMsg);
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

        {/* User File Selection Section */}
        <View style={styles.actionCard}>
          <Text style={styles.cardTitle}>Device Audio File</Text>
          <Text style={styles.cardDesc}>
            Select a WAV, FLAC, OGG, MP3, or M4A file from device storage:
          </Text>

          <TouchableOpacity
            style={[styles.btn, styles.btnFilePicker]}
            onPress={handlePickAudioFile}
            disabled={analyzing}
            accessibilityLabel="Choose Audio File"
            accessibilityRole="button">
            <Text style={styles.btnFilePickerText}>📁  Choose Audio File</Text>
          </TouchableOpacity>

          {selectedFile ? (
            <View style={styles.selectedFileCard}>
              <Text style={styles.selectedFileHeader}>Selected File</Text>
              <Text style={styles.selectedFileRow}>
                <Text style={styles.metaLabel}>Name: </Text>
                <Text style={styles.metaValue}>{selectedFile.name}</Text>
              </Text>
              <Text style={styles.selectedFileRow}>
                <Text style={styles.metaLabel}>Size: </Text>
                <Text style={styles.metaValue}>{(selectedFile.size / 1024).toFixed(1)} KB</Text>
              </Text>
              <Text style={styles.selectedFileRow}>
                <Text style={styles.metaLabel}>Type: </Text>
                <Text style={styles.metaValue}>{selectedFile.type}</Text>
              </Text>

              <TouchableOpacity
                style={[styles.btn, styles.btnPrimary, { marginTop: spacing.md }]}
                onPress={() => handleAnalyzeAudio('selected')}
                disabled={analyzing}
                accessibilityLabel="Analyze Selected Audio"
                accessibilityRole="button">
                {analyzing ? (
                  <ActivityIndicator color={colors.white} />
                ) : (
                  <Text style={styles.btnText}>⚡  Analyze Selected Audio</Text>
                )}
              </TouchableOpacity>
            </View>
          ) : null}
        </View>

        {/* Demo Samples Section */}
        <View style={styles.actionCard}>
          <Text style={styles.cardTitle}>Demo Audio Samples</Text>
          <Text style={styles.cardDesc}>
            Test VoiceShield Core (AASIST-L + ECAPA-TDNN + Whisper) with bundled test audio:
          </Text>

          <TouchableOpacity
            style={[styles.btn, styles.btnPrimary]}
            onPress={() => handleAnalyzeAudio('synthetic')}
            disabled={analyzing}
            accessibilityLabel="Analyze Deepfake Sample Audio"
            accessibilityRole="button">
            {analyzing ? (
              <ActivityIndicator color={colors.white} />
            ) : (
              <Text style={styles.btnText}>🧪  Analyze Deepfake Sample Audio</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.btn, styles.btnSecondary]}
            onPress={() => handleAnalyzeAudio('benign')}
            disabled={analyzing}
            accessibilityLabel="Analyze Benign Human Audio"
            accessibilityRole="button">
            <Text style={styles.btnSecondaryText}>🟢  Analyze Benign Human Audio</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.btn, styles.btnOutline]}
            onPress={() => handleAnalyzeAudio('short')}
            disabled={analyzing}
            accessibilityLabel="Test Short Audio Gate"
            accessibilityRole="button">
            <Text style={styles.btnOutlineText}>⏱  Test Short Audio Gate (&lt; 4.038s)</Text>
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
                <Text style={styles.metaValue}>{report.status?.toUpperCase()}</Text>
              </Text>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>File: </Text>
                <Text style={styles.metaValue}>{report.filename}</Text>
              </Text>
              <Text style={styles.metaRow}>
                <Text style={styles.metaLabel}>Duration: </Text>
                <Text style={styles.metaValue}>
                  {report.duration_seconds !== undefined ? `${report.duration_seconds.toFixed(2)}s` : '--'}
                </Text>
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
              evidenceConfidence={report.evidence_confidence || 0}
              recommendedAction={report.recommended_action || ''}
            />

            {/* Multi-modal breakdown */}
            {report.analysis_completed && (
              <>
                <AuthenticityPanel
                  authenticity={report.authenticity}
                />

                <IdentityPanel
                  identity={report.identity}
                />

                <ContextPanel
                  context={report.context}
                />
              </>
            )}

            {/* Window Timeline (if available) */}
            {report.window_timeline && report.window_timeline.length > 0 && (
              <View style={styles.timelineCard}>
                <Text style={styles.cardTitle}>Window Timeline</Text>
                {report.window_timeline.map((win: any) => (
                  <View key={win.window_index} style={styles.windowRow}>
                    <Text style={styles.windowTime}>
                      {(win.offset_ms / 1000).toFixed(1)}s - {((win.offset_ms + 4038) / 1000).toFixed(1)}s
                    </Text>
                    <Text style={styles.windowSpoof}>
                      Spoof: {(win.spoof_score * 100).toFixed(0)}%
                    </Text>
                    <Text style={styles.windowRisk}>
                      Risk: {win.risk_score}
                    </Text>
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
    padding: spacing.lg,
  },
  header: {
    marginBottom: spacing.lg,
  },
  title: {
    ...typography.h2,
    color: colors.textPrimary,
    marginBottom: spacing.xs,
  },
  subtitle: {
    fontSize: 14,
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
    fontSize: 16,
    fontWeight: '700',
    color: colors.textPrimary,
    marginBottom: 4,
  },
  cardDesc: {
    fontSize: 13,
    color: colors.textSecondary,
    marginBottom: spacing.md,
    lineHeight: 18,
  },
  btn: {
    borderRadius: radius.md,
    paddingVertical: 14,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  btnFilePicker: {
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderStyle: 'dashed',
  },
  btnFilePickerText: {
    color: colors.brand,
    fontWeight: '700',
    fontSize: 15,
  },
  selectedFileCard: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.sm,
    padding: spacing.sm,
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  selectedFileHeader: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.brand,
    marginBottom: spacing.xs,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  selectedFileRow: {
    fontSize: 13,
    color: colors.textPrimary,
    marginBottom: 2,
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
    marginBottom: 0,
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
