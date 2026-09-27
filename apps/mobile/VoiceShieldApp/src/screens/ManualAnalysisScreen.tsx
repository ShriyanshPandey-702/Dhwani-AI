import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "../utils/theme";
import { analyzeAudioFile, formatApiError } from "../services/api/client";
import { callScreeningService } from "../services/telecom/callScreeningService";
import { useSessionStore } from "../store/sessionStore";
import { AudioFileInfo } from "../types/telecom";
import { RiskOrb } from "../components/RiskOrb";
import { DecisionPanel } from "../components/DecisionPanel";
import { AuthenticityPanel } from "../components/AuthenticityPanel";
import { IdentityPanel } from "../components/IdentityPanel";
import { ActiveLivenessPanel } from "../components/ActiveLivenessPanel";
import { ConsequencesPanel } from "../components/ConsequencesPanel";
import { RiskBadge } from "../components/RiskBadge";
import { BottomNavigation } from "../components/BottomNavigation";
import { RiskState, Decision } from "../types";
import { notificationService } from "../services/notification/notificationService";
import { RootStackParamList } from "../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<RootStackParamList>;

export const ManualAnalysisScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const createSession = useSessionStore((s) => s.createSession);
  const startSession = useSessionStore((s) => s.startSession);

  const [startingLive, setStartingLive] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<AudioFileInfo | null>(null);
  const [speakerReferenceFile, setSpeakerReferenceFile] = useState<AudioFileInfo | null>(null);
  const [report, setReport] = useState<any>(null);

  const handleStartLiveMic = async () => {
    setStartingLive(true);
    try {
      const session = await createSession();
      if (session) {
        await startSession(session.id);
        navigation.navigate("Call", { sessionId: session.id, mode: "live" });
      }
    } catch {
      Alert.alert("Session Error", "Could not start live microphone session.");
    } finally {
      setStartingLive(false);
    }
  };

  const handlePickAudioFile = async () => {
    try {
      const picked = await callScreeningService.pickAudioFile();
      if (picked) {
        setSelectedFile(picked);
      }
    } catch (err: any) {
      Alert.alert("File Picker Error", err?.message || "Could not pick audio file.");
    }
  };

  const handlePickSpeakerReference = async () => {
    try {
      const picked = await callScreeningService.pickAudioFile();
      if (picked) {
        setSpeakerReferenceFile(picked);
      }
    } catch (err: any) {
      Alert.alert("Speaker Reference Error", err?.message || "Could not pick reference audio file.");
    }
  };

  const handleClearSpeakerReference = () => {
    setSpeakerReferenceFile(null);
  };

  const handleAnalyzeAudio = async () => {
    if (!selectedFile) {
      Alert.alert("No File Selected", "Please choose a target audio file from your device first.");
      return;
    }

    setAnalyzing(true);
    setReport(null);

    try {
      await notificationService.notifyFileAnalysisStarted(selectedFile.name);

      const formData = new FormData();
      formData.append("file", {
        uri: selectedFile.uri,
        name: selectedFile.name,
        type: selectedFile.type || "audio/wav",
      } as any);

      if (speakerReferenceFile) {
        formData.append("speaker_reference", {
          uri: speakerReferenceFile.uri,
          name: speakerReferenceFile.name,
          type: speakerReferenceFile.type || "audio/wav",
        } as any);
      }

      const data = await analyzeAudioFile(formData);
      setReport(data);

      const computedState: RiskState = (data?.risk_state as RiskState) || "insufficient_evidence";
      const computedDecision: Decision = (data?.decision as Decision) || "VERIFY";
      await notificationService.notifyRiskTransition(
        computedState,
        data?.risk_score ?? 0,
        computedDecision,
        data?.recommended_action
      );
    } catch (err: any) {
      const errorMsg = formatApiError(err);
      Alert.alert("Analysis Error", errorMsg);
    } finally {
      setAnalyzing(false);
    }
  };

  const riskState: RiskState = (report?.risk_state as RiskState) || "insufficient_evidence";
  const decision: Decision = (report?.decision as Decision) || "VERIFY";
  const isCapActive = report?.reasons?.includes("total_risk_uncorroborated_cap_active");

  // Determine comparison metrics if reference voice was supplied
  const hasReferenceComparison = speakerReferenceFile && report?.identity?.enrollment_status === "ENROLLED";
  const speakerSimilarityPct = report?.identity?.match_score ?? 0;
  const syntheticEvidencePct = Math.round((report?.authenticity?.spoof_probability ?? 0) * 100);
  const isAcousticallySimilar = speakerSimilarityPct >= 70;
  const isElevatedSynthetic = syntheticEvidencePct >= 60;

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
        },
      ]}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 16,
            paddingBottom: Math.max(insets.bottom, 20) + 16,
          },
        ]}
      >
        {/* Header Section (Section 29) */}
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Voice Analysis Engine
          </Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Live microphone streaming, forensic audio inspection, and enrolled speaker impersonation comparison.
          </Text>
        </View>

        {/* ── Workflow 1: Live Microphone Analysis ───────────────────────── */}
        <View
          style={[
            styles.actionCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>
            Live Microphone Analysis
          </Text>
          <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
            Stream ambient speech in real time from your device microphone directly into the AASIST + ECAPA-TDNN + Whisper pipeline.
          </Text>

          <TouchableOpacity
            style={[
              styles.btn,
              { backgroundColor: colors.accent, borderRadius: radius.md },
            ]}
            onPress={handleStartLiveMic}
            disabled={startingLive}
            accessibilityRole="button"
            accessibilityLabel="Start Live Microphone Analysis"
          >
            {startingLive ? (
              <ActivityIndicator color="#FFFFFF" size="small" />
            ) : (
              <Text style={styles.btnText}>🎙  Start Live Microphone Stream</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* ── Workflow 2: Target Audio File (Required) ───────────────────── */}
        <View
          style={[
            styles.actionCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>
            1. Target Audio File (Required)
          </Text>
          <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
            Select the suspicious or test voice recording (WAV, FLAC, OGG, MP3, M4A):
          </Text>

          <TouchableOpacity
            style={[
              styles.pickerBtn,
              {
                borderColor: colors.accent,
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderRadius: radius.sm,
              },
            ]}
            onPress={handlePickAudioFile}
            disabled={analyzing}
            accessibilityRole="button"
            accessibilityLabel="Choose Target Audio File"
          >
            <Text style={[styles.pickerBtnText, { color: colors.accent }]}>
              📁  Choose Target Audio File
            </Text>
          </TouchableOpacity>

          {selectedFile && (
            <View
              style={[
                styles.selectedFileBox,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                  borderRadius: radius.sm,
                },
              ]}
            >
              <Text style={[styles.selectedFileHeader, { color: colors.accent }]}>
                Selected Target Audio
              </Text>
              <Text style={[styles.metaRow, { color: colors.textPrimary }]}>
                <Text style={{ fontWeight: "700" }}>Name: </Text>{selectedFile.name}
              </Text>
              <Text style={[styles.metaRow, { color: colors.textSecondary }]}>
                <Text style={{ fontWeight: "700" }}>Size: </Text>{(selectedFile.size / 1024).toFixed(1)} KB
                {"  "}•{"  "}
                <Text style={{ fontWeight: "700" }}>Type: </Text>{selectedFile.type || "audio/wav"}
              </Text>
            </View>
          )}
        </View>

        {/* ── Workflow 3: Enrolled Reference Voice (Optional) ────────────── */}
        <View
          style={[
            styles.actionCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.refHeaderRow}>
            <Text style={[styles.cardTitle, { color: colors.textPrimary }]}>
              2. Enrolled Speaker Reference (Optional)
            </Text>
            {speakerReferenceFile && (
              <TouchableOpacity onPress={handleClearSpeakerReference} disabled={analyzing}>
                <Text style={[styles.removeText, { color: colors.danger }]}>Remove</Text>
              </TouchableOpacity>
            )}
          </View>
          <Text style={[styles.cardDesc, { color: colors.textSecondary }]}>
            Attach a genuine reference voice of the claimed person to test impersonation. If omitted, identity is un-enrolled.
          </Text>

          <TouchableOpacity
            style={[
              styles.pickerBtn,
              {
                borderColor: colors.textSecondary,
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderRadius: radius.sm,
              },
            ]}
            onPress={handlePickSpeakerReference}
            disabled={analyzing}
            accessibilityRole="button"
            accessibilityLabel="Choose Enrolled Speaker Reference"
          >
            <Text style={[styles.pickerBtnText, { color: colors.textPrimary }]}>
              {speakerReferenceFile
                ? "🔄  Change Reference Audio"
                : "🎙  Attach Enrolled Reference Voice"}
            </Text>
          </TouchableOpacity>

          {speakerReferenceFile ? (
            <View
              style={[
                styles.selectedFileBox,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                  borderRadius: radius.sm,
                },
              ]}
            >
              <Text style={[styles.selectedFileHeader, { color: colors.accent }]}>
                Enrolled Reference Audio
              </Text>
              <Text style={[styles.metaRow, { color: colors.textPrimary }]}>
                <Text style={{ fontWeight: "700" }}>Name: </Text>{speakerReferenceFile.name}
              </Text>
              <Text style={[styles.metaRow, { color: colors.textSecondary }]}>
                <Text style={{ fontWeight: "700" }}>Size: </Text>{(speakerReferenceFile.size / 1024).toFixed(1)} KB
              </Text>
            </View>
          ) : (
            <View
              style={[
                styles.noticeBox,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                  borderRadius: radius.sm,
                },
              ]}
            >
              <Text style={[styles.noticeText, { color: colors.textMuted }]}>
                No reference audio attached. Multi-modal policy caps uncorroborated single-source synthetic voice at 38 (LOW risk) unless scam context is present.
              </Text>
            </View>
          )}
        </View>

        {/* ── Run Real ML Analysis Button ─────────────────────────────────── */}
        {selectedFile && (
          <TouchableOpacity
            style={[
              styles.btn,
              {
                backgroundColor: colors.accent,
                borderRadius: radius.md,
                opacity: analyzing ? 0.7 : 1,
                marginVertical: 4,
              },
            ]}
            onPress={handleAnalyzeAudio}
            disabled={analyzing}
            accessibilityRole="button"
            accessibilityLabel="Run Real ML Analysis"
          >
            {analyzing ? (
              <View style={styles.analyzingRow}>
                <ActivityIndicator color="#FFFFFF" size="small" />
                <Text style={styles.btnText}>Analyzing via ML Core…</Text>
              </View>
            ) : (
              <Text style={styles.btnText}>⚡  Run Real ML Analysis</Text>
            )}
          </TouchableOpacity>
        )}

        {/* ── Results Section ─────────────────────────────────────────────── */}
        {report && (
          <View style={styles.resultsContainer}>
            <View style={styles.resultHeader}>
              <Text style={[styles.resultTitle, { color: colors.textPrimary }]}>
                Analysis Report
              </Text>
              <RiskBadge state={riskState} size="md" />
            </View>

            {/* Anti-False-Alarm Policy Cap Banner */}
            {isCapActive && (
              <View
                style={[
                  styles.bannerBox,
                  {
                    backgroundColor: `${colors.warning}18`,
                    borderColor: `${colors.warning}55`,
                    borderRadius: radius.sm,
                  },
                ]}
              >
                <Text style={[styles.bannerTitle, { color: colors.warning }]}>
                  ⚠️ Anti-False-Alarm Policy Cap Active (38/100)
                </Text>
                <Text style={[styles.bannerDesc, { color: colors.textSecondary }]}>
                  Single-source synthetic voice evidence without an enrolled reference voice or scam context is capped at 38 (LOW risk) to prevent false alarms on benign voice compression. To test impersonation against a claimed identity, attach an Enrolled Speaker Reference file above.
                </Text>
              </View>
            )}

            {/* Section 31: Dedicated Reference / Target Comparison UI */}
            {hasReferenceComparison && (
              <View
                style={[
                  styles.comparisonCard,
                  {
                    backgroundColor: isDark ? colors.surface : colors.surface,
                    borderColor: isElevatedSynthetic && isAcousticallySimilar ? colors.danger : colors.accent,
                    borderRadius: radius.md,
                  },
                ]}
              >
                <Text style={[styles.compHeader, { color: colors.textSecondary }]}>
                  SPEAKER COMPARISON & IMPERSONATION ANALYSIS
                </Text>

                <View style={styles.compGrid}>
                  <View style={styles.compItem}>
                    <Text style={[styles.compKey, { color: colors.textMuted }]}>
                      Speaker Similarity
                    </Text>
                    <Text style={[styles.compVal, { color: colors.textPrimary }]}>
                      {speakerSimilarityPct}%
                    </Text>
                  </View>

                  <View style={styles.compItem}>
                    <Text style={[styles.compKey, { color: colors.textMuted }]}>
                      Synthetic Evidence
                    </Text>
                    <Text
                      style={[
                        styles.compVal,
                        { color: isElevatedSynthetic ? colors.danger : colors.success },
                      ]}
                    >
                      {syntheticEvidencePct}%
                    </Text>
                  </View>

                  <View style={styles.compItem}>
                    <Text style={[styles.compKey, { color: colors.textMuted }]}>
                      Identity Match
                    </Text>
                    <Text style={[styles.compVal, { color: colors.textPrimary }]}>
                      {isAcousticallySimilar ? "High" : "Low / Mismatch"}
                    </Text>
                  </View>

                  <View style={styles.compItem}>
                    <Text style={[styles.compKey, { color: colors.textMuted }]}>
                      Authenticity
                    </Text>
                    <Text
                      style={[
                        styles.compVal,
                        { color: isElevatedSynthetic ? colors.danger : colors.success },
                      ]}
                    >
                      {isElevatedSynthetic ? "High synthetic evidence" : "Low synthetic evidence"}
                    </Text>
                  </View>
                </View>

                {/* Model-supported Interpretation */}
                <View
                  style={[
                    styles.interpBox,
                    {
                      backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                      borderRadius: radius.sm,
                    },
                  ]}
                >
                  <Text style={[styles.interpTitle, { color: colors.textPrimary }]}>
                    Interpretation
                  </Text>
                  <Text style={[styles.interpText, { color: colors.textSecondary }]}>
                    {isAcousticallySimilar && isElevatedSynthetic
                      ? "The target voice is acoustically similar to the reference speaker while showing elevated synthetic-voice evidence. Strong potential voice cloning / impersonation detected."
                      : isAcousticallySimilar
                      ? "The target voice is acoustically consistent with the reference speaker with low synthetic probability. Verified genuine human speech."
                      : isElevatedSynthetic
                      ? "The target voice exhibits synthetic speech artifacts and does not acoustically match the enrolled reference speaker."
                      : "The target voice does not match the enrolled reference speaker, but acoustic synthetic evidence is low."}
                  </Text>
                </View>
              </View>
            )}

            {/* Central Risk Orb */}
            {report.analysis_completed && report.risk_score !== null && (
              <RiskOrb
                score={report.risk_score}
                state={riskState}
                isActive={false}
                size={190}
                sublabel={selectedFile?.name || "Audio File"}
              />
            )}

            {/* Decision Panel */}
            <DecisionPanel
              decision={decision}
              reasons={report.reasons || []}
              evidenceConfidence={report.evidence_confidence || 0}
              recommendedAction={report.recommended_action || ""}
            />

            {/* 4 Core Evidence Panels */}
            {report.analysis_completed && (
              <>
                <AuthenticityPanel authenticity={report.authenticity} />
                <IdentityPanel identity={report.identity} />
                <ActiveLivenessPanel challengeState="idle" audioActive={false} />
                <ConsequencesPanel context={report.context} />
              </>
            )}

            {/* Window Timeline (No NaN) */}
            {report.window_timeline && report.window_timeline.length > 0 && (
              <View
                style={[
                  styles.timelineBox,
                  {
                    backgroundColor: isDark ? colors.surface : colors.surface,
                    borderColor: colors.border,
                    borderRadius: radius.md,
                  },
                ]}
              >
                <Text style={[styles.timelineTitle, { color: colors.textPrimary }]}>
                  Window Timeline
                </Text>
                {report.window_timeline.map((win: any) => {
                  const rawSpoof = win.spoof_score ?? win.authenticity_spoof_prob;
                  const isValidSpoof = typeof rawSpoof === "number" && Number.isFinite(rawSpoof);
                  const spoofDisplay = isValidSpoof ? `${Math.round(rawSpoof * 100)}%` : "Unavailable";
                  const riskDisplay =
                    win.window_risk_score !== undefined && win.window_risk_score !== null
                      ? `${win.window_risk_score}`
                      : "Insufficient Evidence";

                  return (
                    <View
                      key={win.window_index}
                      style={[
                        styles.windowRow,
                        { borderBottomColor: colors.border },
                      ]}
                    >
                      <Text style={[styles.windowTime, { color: colors.textSecondary }]}>
                        {(win.offset_ms / 1000).toFixed(1)}s - {((win.offset_ms + 4038) / 1000).toFixed(1)}s
                      </Text>
                      <Text style={[styles.windowSpoof, { color: colors.textPrimary }]}>
                        Spoof: {spoofDisplay}
                      </Text>
                      <Text style={[styles.windowRisk, { color: colors.textMuted }]}>
                        Risk: {riskDisplay}
                      </Text>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        )}
      </ScrollView>

      {/* Persistent Bottom Navigation (Section 28) */}
      <BottomNavigation activeTab="analyze" />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    paddingHorizontal: 18,
    gap: 12,
  },
  header: {
    marginBottom: 4,
    gap: 4,
  },
  title: {
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.4,
  },
  subtitle: {
    fontSize: 13,
    lineHeight: 18,
  },
  actionCard: {
    borderWidth: 1,
    padding: 16,
    gap: 8,
  },
  cardTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  cardDesc: {
    fontSize: 12,
    lineHeight: 17,
  },
  refHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  removeText: {
    fontSize: 12,
    fontWeight: "700",
  },
  pickerBtn: {
    borderWidth: 1,
    borderStyle: "dashed",
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 2,
  },
  pickerBtnText: {
    fontSize: 13,
    fontWeight: "700",
  },
  selectedFileBox: {
    borderWidth: 1,
    padding: 10,
    gap: 2,
    marginTop: 4,
  },
  selectedFileHeader: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
    textTransform: "uppercase",
    marginBottom: 2,
  },
  metaRow: {
    fontSize: 12,
  },
  noticeBox: {
    borderWidth: 1,
    padding: 10,
    marginTop: 4,
  },
  noticeText: {
    fontSize: 11,
    lineHeight: 15,
  },
  btn: {
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  btnText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
  },
  analyzingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  resultsContainer: {
    marginTop: 8,
    gap: 12,
  },
  resultHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  resultTitle: {
    fontSize: 18,
    fontWeight: "800",
  },
  bannerBox: {
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  bannerTitle: {
    fontSize: 12,
    fontWeight: "700",
  },
  bannerDesc: {
    fontSize: 11,
    lineHeight: 16,
  },
  comparisonCard: {
    borderWidth: 1.5,
    padding: 16,
    gap: 12,
  },
  compHeader: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  compGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  compItem: {
    width: "47%",
    gap: 2,
  },
  compKey: {
    fontSize: 11,
  },
  compVal: {
    fontSize: 15,
    fontWeight: "800",
  },
  interpBox: {
    padding: 12,
    gap: 4,
  },
  interpTitle: {
    fontSize: 12,
    fontWeight: "700",
  },
  interpText: {
    fontSize: 12,
    lineHeight: 17,
  },
  timelineBox: {
    borderWidth: 1,
    padding: 14,
    gap: 8,
  },
  timelineTitle: {
    fontSize: 13,
    fontWeight: "700",
  },
  windowRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 6,
    borderBottomWidth: 1,
  },
  windowTime: {
    fontSize: 11,
    fontFamily: "monospace",
  },
  windowSpoof: {
    fontSize: 11,
    fontWeight: "600",
  },
  windowRisk: {
    fontSize: 11,
  },
});
