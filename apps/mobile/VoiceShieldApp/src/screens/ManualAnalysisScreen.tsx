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
import { LiveAudioWaveform } from "../components/LiveAudioWaveform";
import { DecisionPanel } from "../components/DecisionPanel";
import { AuthenticityPanel } from "../components/AuthenticityPanel";
import { IdentityPanel } from "../components/IdentityPanel";
import { ConsequencesPanel } from "../components/ConsequencesPanel";
import { RiskBadge } from "../components/RiskBadge";
import { BottomNavigation } from "../components/BottomNavigation";
import { BackgroundWave } from "../components/BackgroundWave";
import { RiskState, Decision } from "../types";
import { notificationService } from "../services/notification/notificationService";
import { RootStackParamList } from "../navigation/AppNavigator";
import { MicIcon, FolderIcon, UserIcon, ShieldIcon } from "../components/Icons";

type Nav = NativeStackNavigationProp<RootStackParamList>;

type WorkspaceTab = "LIVE" | "FORENSIC" | "SPEAKER";

export const ManualAnalysisScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const createSession = useSessionStore((s) => s.createSession);
  const startSession = useSessionStore((s) => s.startSession);

  const [activeTab, setActiveTab] = useState<WorkspaceTab>("LIVE");
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

  const hasReferenceComparison = speakerReferenceFile && report?.identity?.enrollment_status === "ENROLLED";
  const speakerSimilarityPct = report?.identity?.match_score ?? null;

  return (
    <View style={[styles.container, { backgroundColor: colors.background }]}>
      <BackgroundWave />

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 12,
            paddingBottom: Math.max(insets.bottom, 20) + 16,
          },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Top Title & Header */}
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Voice Analysis Engine
          </Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Real-time microphone monitoring, forensic file inspection, and speaker verification.
          </Text>
        </View>

        {/* ── Segmented Workspace Bar ──────────────────────────────────── */}
        {!report && (
          <View
            style={[
              styles.segmentContainer,
              {
                backgroundColor: isDark ? colors.surfaceElevated : "#EDE8E4",
                borderRadius: radius.lg,
              },
            ]}
          >
            {(["LIVE", "FORENSIC", "SPEAKER"] as WorkspaceTab[]).map((tab) => {
              const active = activeTab === tab;
              return (
                <TouchableOpacity
                  key={tab}
                  style={[
                    styles.segmentTab,
                    active && [
                      styles.segmentTabActive,
                      {
                        backgroundColor: isDark ? colors.surface : "#FFFFFF",
                        shadowColor: isDark ? "#000000" : colors.cardShadow,
                      },
                    ],
                  ]}
                  onPress={() => setActiveTab(tab)}
                  activeOpacity={0.8}
                >
                  <Text
                    style={[
                      styles.segmentText,
                      {
                        color: active ? colors.accent : colors.textMuted,
                        fontWeight: active ? "700" : "600",
                      },
                    ]}
                  >
                    {tab === "LIVE"
                      ? "LIVE MIC"
                      : tab === "FORENSIC"
                      ? "FORENSIC"
                      : "SPEAKER"}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        {/* ── SECTION 1: LIVE MICROPHONE ──────────────────────────────── */}
        {!report && activeTab === "LIVE" && (
          <View
            style={[
              styles.glassCard,
              {
                backgroundColor: isDark ? `${colors.surface}EE` : "#FFFFFFEE",
                borderColor: colors.border,
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
              },
            ]}
          >
            <View style={styles.cardHeaderRow}>
              <View style={styles.cardHeaderIconText}>
                <View
                  style={[
                    styles.iconBadge,
                    { backgroundColor: `${colors.accent}15` },
                  ]}
                >
                  <MicIcon size={18} color={colors.accent} />
                </View>
                <View>
                  <Text style={[styles.cardHeaderTitle, { color: colors.textPrimary }]}>
                    LIVE MICROPHONE
                  </Text>
                  <Text style={[styles.cardHeaderSub, { color: colors.textSecondary }]}>
                    Real-time voice monitoring & threat analysis
                  </Text>
                </View>
              </View>
              <View
                style={[
                  styles.statusTag,
                  { backgroundColor: `${colors.success}18` },
                ]}
              >
                <View
                  style={[
                    styles.statusDot,
                    { backgroundColor: colors.success },
                  ]}
                />
                <Text style={[styles.statusTagText, { color: colors.success }]}>
                  READY
                </Text>
              </View>
            </View>

            {/* Live Audio Waveform Animation Area */}
            <View
              style={[
                styles.waveformPreviewBox,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : "#F8F5F2",
                  borderRadius: radius.md,
                },
              ]}
            >
              <LiveAudioWaveform isActive={true} audioLevel={0.08} height={48} />
              <Text style={[styles.waveCaption, { color: colors.textMuted }]}>
                Monitor live audio in real time
              </Text>
            </View>

            {/* Action Button */}
            <TouchableOpacity
              style={[
                styles.primaryBtn,
                { backgroundColor: colors.accent, borderRadius: radius.lg },
              ]}
              onPress={handleStartLiveMic}
              disabled={startingLive}
              activeOpacity={0.85}
            >
              {startingLive ? (
                <ActivityIndicator color="#FFFFFF" size="small" />
              ) : (
                <Text style={styles.primaryBtnText}>
                  START LIVE ANALYSIS
                </Text>
              )}
            </TouchableOpacity>

            {/* Metadata Footer */}
            <View style={styles.metaInfoRow}>
              <Text style={[styles.metaItem, { color: colors.textMuted }]}>
                Source: Device Microphone
              </Text>
              <Text style={[styles.metaItem, { color: colors.textMuted }]}>
                Format: 16 kHz PCM Mono
              </Text>
            </View>

            {/* Provider Engine Status Bar */}
            <View style={[styles.providerStatusBox, { borderColor: colors.border }]}>
              <Text style={[styles.providerHeader, { color: colors.textSecondary }]}>
                VOICE ENGINE PIPELINE
              </Text>
              <View style={styles.providerGrid}>
                <View style={styles.providerItem}>
                  <View style={[styles.provDot, { backgroundColor: colors.success }]} />
                  <Text style={[styles.provName, { color: colors.textPrimary }]}>AASIST-L</Text>
                </View>
                <View style={styles.providerItem}>
                  <View style={[styles.provDot, { backgroundColor: colors.success }]} />
                  <Text style={[styles.provName, { color: colors.textPrimary }]}>ECAPA-TDNN</Text>
                </View>
                <View style={styles.providerItem}>
                  <View style={[styles.provDot, { backgroundColor: colors.success }]} />
                  <Text style={[styles.provName, { color: colors.textPrimary }]}>Deepgram STT</Text>
                </View>
                <View style={styles.providerItem}>
                  <View style={[styles.provDot, { backgroundColor: colors.accent }]} />
                  <Text style={[styles.provName, { color: colors.textPrimary }]}>Modulate Velma-2</Text>
                </View>
              </View>
            </View>
          </View>
        )}

        {/* ── SECTION 2: FORENSIC AUDIO FILE ──────────────────────────── */}
        {!report && activeTab === "FORENSIC" && (
          <View
            style={[
              styles.glassCard,
              {
                backgroundColor: isDark ? `${colors.surface}EE` : "#FFFFFFEE",
                borderColor: colors.border,
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
              },
            ]}
          >
            <View style={styles.cardHeaderRow}>
              <View style={styles.cardHeaderIconText}>
                <View
                  style={[
                    styles.iconBadge,
                    { backgroundColor: `${colors.accent}15` },
                  ]}
                >
                  <FolderIcon size={18} color={colors.accent} />
                </View>
                <View>
                  <Text style={[styles.cardHeaderTitle, { color: colors.textPrimary }]}>
                    FORENSIC AUDIO
                  </Text>
                  <Text style={[styles.cardHeaderSub, { color: colors.textSecondary }]}>
                    Analyze recorded audio files for synthetic voices & threats
                  </Text>
                </View>
              </View>
            </View>

            {/* Dropzone / Upload Box */}
            <TouchableOpacity
              style={[
                styles.dropzone,
                {
                  borderColor: selectedFile ? colors.accent : colors.border,
                  backgroundColor: isDark ? colors.surfaceElevated : "#F8F5F2",
                  borderRadius: radius.lg,
                },
              ]}
              onPress={handlePickAudioFile}
              disabled={analyzing}
              activeOpacity={0.8}
            >
              <FolderIcon size={32} color={colors.accent} />
              <Text style={[styles.dropzoneTitle, { color: colors.textPrimary }]}>
                {selectedFile ? "Change Selected File" : "Choose Audio File"}
              </Text>
              <Text style={[styles.dropzoneSub, { color: colors.textMuted }]}>

                Supported: WAV · MP3 · M4A · FLAC · OGG (up to 25 MB)
              </Text>
            </TouchableOpacity>

            {/* Selected File Details */}
            {selectedFile && (
              <View
                style={[
                  styles.fileDetailBox,
                  {
                    backgroundColor: isDark ? colors.surfaceElevated : "#F4EFEA",
                    borderColor: colors.border,
                    borderRadius: radius.md,
                  },
                ]}
              >
                <Text style={[styles.fileName, { color: colors.textPrimary }]} numberOfLines={1}>
                  {selectedFile.name}
                </Text>
                <View style={styles.fileMetaRow}>
                  <Text style={[styles.fileMetaText, { color: colors.textSecondary }]}>
                    Size: {(selectedFile.size / 1024).toFixed(1)} KB
                  </Text>
                  <Text style={[styles.fileMetaText, { color: colors.textSecondary }]}>
                    Type: {selectedFile.type || "audio/wav"}
                  </Text>
                </View>
              </View>
            )}

            {/* Analyze Button */}
            {selectedFile && (
              <TouchableOpacity
                style={[
                  styles.primaryBtn,
                  { backgroundColor: colors.accent, borderRadius: radius.lg },
                ]}
                onPress={handleAnalyzeAudio}
                disabled={analyzing}
                activeOpacity={0.85}
              >
                {analyzing ? (
                  <View style={styles.btnRow}>
                    <ActivityIndicator color="#FFFFFF" size="small" />
                    <Text style={styles.primaryBtnText}>
                      Analyzing with Multi-Modal ML Core…
                    </Text>
                  </View>
                ) : (
                  <Text style={styles.primaryBtnText}>
                    ANALYZE RECORDING
                  </Text>
                )}
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* ── SECTION 3: SPEAKER REFERENCE ────────────────────────────── */}
        {!report && activeTab === "SPEAKER" && (
          <View
            style={[
              styles.glassCard,
              {
                backgroundColor: isDark ? `${colors.surface}EE` : "#FFFFFFEE",
                borderColor: colors.border,
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
              },
            ]}
          >
            <View style={styles.cardHeaderRow}>
              <View style={styles.cardHeaderIconText}>
                <View
                  style={[
                    styles.iconBadge,
                    { backgroundColor: `${colors.accent}15` },
                  ]}
                >
                  <UserIcon size={18} color={colors.accent} />
                </View>
                <View>
                  <Text style={[styles.cardHeaderTitle, { color: colors.textPrimary }]}>
                    SPEAKER REFERENCE
                  </Text>
                  <Text style={[styles.cardHeaderSub, { color: colors.textSecondary }]}>
                    Compare target voice against a verified speaker
                  </Text>
                </View>
              </View>
              {speakerReferenceFile && (
                <TouchableOpacity onPress={handleClearSpeakerReference} disabled={analyzing}>
                  <Text style={[styles.removeLink, { color: colors.danger }]}>Remove</Text>
                </TouchableOpacity>
              )}
            </View>

            {speakerReferenceFile ? (
              <View
                style={[
                  styles.fileDetailBox,
                  {
                    backgroundColor: isDark ? colors.surfaceElevated : "#F4EFEA",
                    borderColor: colors.border,
                    borderRadius: radius.md,
                  },
                ]}
              >
                <Text style={[styles.fileName, { color: colors.textPrimary }]}>
                  {speakerReferenceFile.name}
                </Text>
                <Text style={[styles.fileMetaText, { color: colors.textSecondary }]}>
                  Enrolled Reference Voice · {(speakerReferenceFile.size / 1024).toFixed(1)} KB
                </Text>
              </View>
            ) : (
              <View
                style={[
                  styles.noticeContainer,
                  {
                    backgroundColor: isDark ? colors.surfaceElevated : "#F8F5F2",
                    borderRadius: radius.md,
                  },
                ]}
              >
                <Text style={[styles.noticeText, { color: colors.textMuted }]}>
                  Identity comparison unavailable until a reference voice is supplied.
                </Text>
              </View>
            )}

            <TouchableOpacity
              style={[
                styles.outlineBtn,
                {
                  borderColor: colors.accent,
                  borderRadius: radius.lg,
                },
              ]}
              onPress={handlePickSpeakerReference}
              disabled={analyzing}
              activeOpacity={0.8}
            >
              <Text style={[styles.outlineBtnText, { color: colors.accent }]}>
                {speakerReferenceFile ? "CHANGE REFERENCE VOICE" : "ADD REFERENCE VOICE"}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── ANALYSIS REPORT VIEW (WHEN COMPLETED) ────────────────────── */}
        {report && (
          <View style={styles.reportContainer}>
            <View style={styles.reportTopBar}>
              <TouchableOpacity
                style={[styles.backBtn, { borderColor: colors.border }]}
                onPress={() => setReport(null)}
              >
                <Text style={[styles.backBtnText, { color: colors.textPrimary }]}>
                  ← Back to Workspace
                </Text>
              </TouchableOpacity>
              <RiskBadge state={riskState} size="md" />
            </View>

            {/* 1. NEW SCORE ORB AT TOP (CLEAN CENTER) */}
            <View style={styles.scoreOrbContainer}>
              <RiskOrb
                score={report.risk_score ?? 0}
                state={riskState}
                size={190}
                sublabel="FORENSIC RISK"
              />
            </View>

            {/* 2. AUDIO FILE METADATA CARD (CLEANLY PLACED BELOW SCORE ORB) */}
            <View
              style={[
                styles.metaCard,
                {
                  backgroundColor: isDark ? colors.surface : "#FFFFFF",
                  borderColor: colors.border,
                  borderRadius: radius.lg,
                  shadowColor: isDark ? "#000000" : colors.cardShadow,
                },
              ]}
            >
              <Text style={[styles.metaCardHeader, { color: colors.accent }]}>
                AUDIO FILE INFORMATION
              </Text>
              <Text style={[styles.metaFileName, { color: colors.textPrimary }]}>
                {report.filename}
              </Text>
              <View style={styles.metaGrid}>
                <View style={styles.metaCell}>
                  <Text style={[styles.metaCellLabel, { color: colors.textMuted }]}>Duration</Text>
                  <Text style={[styles.metaCellValue, { color: colors.textPrimary }]}>
                    {report.duration_seconds?.toFixed(1)}s
                  </Text>
                </View>
                <View style={styles.metaCell}>
                  <Text style={[styles.metaCellLabel, { color: colors.textMuted }]}>Sample Rate</Text>
                  <Text style={[styles.metaCellValue, { color: colors.textPrimary }]}>
                    {report.sample_rate} Hz
                  </Text>
                </View>
                <View style={styles.metaCell}>
                  <Text style={[styles.metaCellLabel, { color: colors.textMuted }]}>Channels</Text>
                  <Text style={[styles.metaCellValue, { color: colors.textPrimary }]}>
                    {report.channels === 1 ? "Mono" : "Stereo"}
                  </Text>
                </View>
                <View style={styles.metaCell}>
                  <Text style={[styles.metaCellLabel, { color: colors.textMuted }]}>Windows</Text>
                  <Text style={[styles.metaCellValue, { color: colors.textPrimary }]}>
                    {report.windows_evaluated}
                  </Text>
                </View>
              </View>
            </View>

            {/* 3. POLICY DECISION */}
            <DecisionPanel
              decision={decision}
              reasons={report.reasons || []}
              recommendedAction={report.recommended_action || "Manual verification recommended"}
              evidenceConfidence={report.evidence_confidence ?? 0.85}
            />

            {/* 4. VOICE AUTHENTICITY (AASIST + MODULATE) */}
            <AuthenticityPanel authenticity={report.authenticity} />

            {/* 5. SPEAKER IDENTITY */}
            <IdentityPanel identity={report.identity} />

            {/* 6. LIVE TRANSCRIPT (DEEPGRAM / FASTER-WHISPER) */}
            <View
              style={[
                styles.transcriptCard,
                {
                  backgroundColor: isDark ? colors.surface : "#FFFFFF",
                  borderColor: colors.border,
                  borderRadius: radius.lg,
                },
              ]}
            >
              <View style={styles.transcriptHeaderRow}>
                <Text style={[styles.transcriptTitle, { color: colors.textPrimary }]}>
                  TRANSCRIPT & CONVERSATION
                </Text>
                <View style={[styles.providerBadge, { backgroundColor: `${colors.accent}15` }]}>
                  <Text style={[styles.providerBadgeText, { color: colors.accent }]}>
                    {report.context?.stt_provider || "Deepgram"}
                  </Text>
                </View>
              </View>

              <Text style={[styles.transcriptContent, { color: colors.textPrimary }]}>
                {report.context?.transcript || "No audible speech transcription detected in this recording."}
              </Text>
            </View>

            {/* 7. CONSEQUENCES & THREAT SIGNALS */}
            <ConsequencesPanel context={report.context} />

            {/* 8. WINDOW TIMELINE */}
            {report.window_timeline && report.window_timeline.length > 0 && (
              <View
                style={[
                  styles.timelineCard,
                  {
                    backgroundColor: isDark ? colors.surface : "#FFFFFF",
                    borderColor: colors.border,
                    borderRadius: radius.lg,
                  },
                ]}
              >
                <Text style={[styles.timelineHeader, { color: colors.textPrimary }]}>
                  WINDOW TIMELINE ({report.window_timeline.length} Windows)
                </Text>
                {report.window_timeline.slice(0, 8).map((win: any, idx: number) => (
                  <View key={idx} style={[styles.windowRow, { borderBottomColor: colors.border }]}>
                    <Text style={[styles.windowTime, { color: colors.textMuted }]}>
                      {((win.offset_ms ?? 0) / 1000).toFixed(1)}s - {(((win.offset_ms ?? 0) + (win.duration_ms ?? 4038)) / 1000).toFixed(1)}s
                    </Text>
                    <Text style={[styles.windowProb, { color: win.authenticity_spoof_prob > 0.65 ? colors.danger : colors.textSecondary }]}>
                      Synth: {Math.round((win.authenticity_spoof_prob ?? 0) * 100)}%
                    </Text>
                    <Text style={[styles.windowRisk, { color: win.window_risk_score >= 60 ? colors.danger : colors.textPrimary }]}>
                      Risk: {win.window_risk_score}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}
      </ScrollView>

      <BottomNavigation activeTab="analyze" />
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  scroll: { paddingHorizontal: 16 },
  header: { marginBottom: 14 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5 },
  subtitle: { fontSize: 13, marginTop: 4, lineHeight: 18 },

  segmentContainer: {
    flexDirection: "row",
    padding: 4,
    marginBottom: 16,
  },
  segmentTab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 8,
  },
  segmentTabActive: {
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.12,
    shadowRadius: 4,
    elevation: 2,
  },
  segmentText: { fontSize: 12, letterSpacing: 0.5 },

  glassCard: {
    borderWidth: 1,
    padding: 16,
    marginBottom: 16,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 3,
  },
  cardHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 14,
  },
  cardHeaderIconText: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    flex: 1,
  },
  iconBadge: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  cardHeaderTitle: {
    fontSize: 15,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  cardHeaderSub: {
    fontSize: 11,
    marginTop: 2,
  },
  statusTag: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
    gap: 5,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  statusTagText: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  waveformPreviewBox: {
    padding: 14,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14,
  },
  waveCaption: {
    fontSize: 11,
    fontWeight: "500",
    marginTop: 6,
  },
  primaryBtn: {
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
    marginVertical: 6,
  },
  primaryBtnText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.6,
  },
  btnRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  metaInfoRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: 8,
  },
  metaItem: { fontSize: 10, fontWeight: "500" },

  providerStatusBox: {
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
  },
  providerHeader: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
    marginBottom: 8,
  },
  providerGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
  },
  providerItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  provDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  provName: {
    fontSize: 11,
    fontWeight: "600",
  },

  dropzone: {
    borderWidth: 1.5,
    borderStyle: "dashed",
    paddingVertical: 24,
    paddingHorizontal: 16,
    alignItems: "center",
    justifyContent: "center",
    marginVertical: 10,
  },
  dropzoneTitle: {
    fontSize: 14,
    fontWeight: "700",
    marginTop: 8,
  },
  dropzoneSub: {
    fontSize: 11,
    marginTop: 4,
    textAlign: "center",
  },
  fileDetailBox: {
    borderWidth: 1,
    padding: 12,
    marginBottom: 12,
  },
  fileName: {
    fontSize: 13,
    fontWeight: "700",
  },
  fileMetaRow: {
    flexDirection: "row",
    gap: 12,
    marginTop: 4,
  },
  fileMetaText: {
    fontSize: 11,
  },

  noticeContainer: {
    padding: 12,
    marginVertical: 10,
  },
  noticeText: {
    fontSize: 12,
    lineHeight: 16,
    fontStyle: "italic",
  },
  outlineBtn: {
    borderWidth: 1.5,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 4,
  },
  outlineBtnText: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  removeLink: {
    fontSize: 12,
    fontWeight: "600",
  },

  reportContainer: {
    gap: 14,
  },
  reportTopBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  backBtn: {
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },
  backBtnText: {
    fontSize: 12,
    fontWeight: "600",
  },
  scoreOrbContainer: {
    alignItems: "center",
    justifyContent: "center",
    marginVertical: 4,
  },

  metaCard: {
    borderWidth: 1,
    padding: 14,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  metaCardHeader: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.8,
    marginBottom: 4,
  },
  metaFileName: {
    fontSize: 13,
    fontWeight: "700",
    marginBottom: 10,
  },
  metaGrid: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  metaCell: {
    alignItems: "center",
  },
  metaCellLabel: {
    fontSize: 10,
    fontWeight: "500",
  },
  metaCellValue: {
    fontSize: 12,
    fontWeight: "700",
    marginTop: 2,
  },

  transcriptCard: {
    borderWidth: 1,
    padding: 14,
  },
  transcriptHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  transcriptTitle: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.6,
  },
  providerBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  providerBadgeText: {
    fontSize: 9,
    fontWeight: "700",
  },
  transcriptContent: {
    fontSize: 12,
    lineHeight: 18,
    fontStyle: "italic",
  },

  timelineCard: {
    borderWidth: 1,
    padding: 14,
  },
  timelineHeader: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.6,
    marginBottom: 10,
  },
  windowRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 6,
    borderBottomWidth: 1,
  },
  windowTime: { fontSize: 11 },
  windowProb: { fontSize: 11, fontWeight: "600" },
  windowRisk: { fontSize: 11, fontWeight: "700" },
});
