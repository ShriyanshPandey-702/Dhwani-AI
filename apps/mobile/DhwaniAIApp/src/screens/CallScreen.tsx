import React, { useCallback, useEffect, useState, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
} from "react-native";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "../utils/theme";
import { useRiskStore } from "../store/riskStore";
import { useSessionStore } from "../store/sessionStore";
import { useRiskStream } from "../hooks/useRiskStream";
import { useAudioCapture } from "../hooks/useAudioCapture";
import { useFileAudioCapture } from "../hooks/useFileAudioCapture";
import { wsService } from "../services/websocket/wsService";

import { RiskOrb } from "../components/RiskOrb";
import { LiveAudioWaveform } from "../components/LiveAudioWaveform";
import { AuthenticityPanel } from "../components/AuthenticityPanel";
import { IdentityPanel } from "../components/IdentityPanel";
import { ActiveLivenessPanel } from "../components/ActiveLivenessPanel";
import { ConsequencesPanel } from "../components/ConsequencesPanel";
import { EventTimeline } from "../components/EventTimeline";
import { DecisionPanel } from "../components/DecisionPanel";
import { AlertCard } from "../components/AlertCard";
import { PipelineModeBanner } from "../components/PipelineModeBanner";
import { BackgroundWave } from "../components/BackgroundWave";
import { PhoneIcon, MicIcon, DeviceIcon, UserIcon } from "../components/Icons";
import { RootStackParamList } from "../navigation/AppNavigator";
import { notificationService } from "../services/notification/notificationService";

import { LIVE_DEMO_MODE } from "../utils/demoLiveEngine";
import { useLiveDemoPlayback } from "../hooks/useLiveDemoPlayback";

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, "Call">;

const SEVERITY_TO_CARD = {
  suspicious: "warning",
  high: "error",
  critical: "critical",
} as const;

export const CallScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const { sessionId } = route.params;
  const mode: "mock" | "live" | "recording" = route.params.mode ?? "live";
  const routeParams = route.params as any;
  const source = routeParams?.source;
  const callerNumber = routeParams?.callerNumber;
  const callerName = routeParams?.callerName;

  const stopSession = useSessionStore((s) => s.stopSession);

  const riskScore = useRiskStore((s) => s.riskScore);
  const riskState = useRiskStore((s) => s.riskState);
  const riskTrend = useRiskStore((s) => s.riskTrend);
  const authenticity = useRiskStore((s) => s.authenticity);
  const identity = useRiskStore((s) => s.identity);
  const context = useRiskStore((s) => s.context);
  const audioActive = useRiskStore((s) => s.audioActive);
  const decision = useRiskStore((s) => s.decision);
  const decisionReasons = useRiskStore((s) => s.decisionReasons);
  const recommendedAction = useRiskStore((s) => s.recommendedAction);
  const detectedEvents = useRiskStore((s) => s.detectedEvents);
  const alerts = useRiskStore((s) => s.alerts);
  const challengeState = useRiskStore((s) => s.challengeState);
  const challengeText = useRiskStore((s) => s.challengeText);
  const verificationState = useRiskStore((s) => s.verificationState);
  const sessionStatus = useRiskStore((s) => s.sessionStatus);
  const pipelineMode = useRiskStore((s) => s.pipelineMode);
  const evidenceConfidence = useRiskStore((s) => s.evidenceConfidence);
  const dismissAlert = useRiskStore((s) => s.dismissAlert);
  const reset = useRiskStore((s) => s.reset);

  const captureMode = mode as string;
  const isDemoMode: boolean = Boolean(LIVE_DEMO_MODE || captureMode === "recording" || captureMode === "mock");
  const demo = useLiveDemoPlayback(isDemoMode);

  const [isEnding, setIsEnding] = useState(false);
  const isEndingRef = useRef(false);

  const {
    start: startMicCapture,
    stop: stopMicCapture,
    audioLevel: micAudioLevel,
  } = useAudioCapture(false);

  // ── File-based recording capture (SIH recording mode)
  // Plays WAV assets through speaker + streams PCM to existing pipeline.
  // Used when mode === 'recording'. Does NOT start the microphone.
  const {
    start: startFileCapture,
    stop: stopFileCapture,
    audioLevel: fileAudioLevel,
  } = useFileAudioCapture();

  // The waveform reacts to actual audio — demo audio in demo mode, mic in live mode, file in recording mode
  const audioLevel = isDemoMode
    ? demo.waveformState.rms
    : captureMode === "recording"
    ? fileAudioLevel
    : micAudioLevel;

  useRiskStream(sessionId);

  useEffect(() => {
    if (sessionStatus === "ended" && !isDemoMode && (captureMode === "live" || captureMode === "recording")) {
      if (captureMode === "live") stopMicCapture().catch(() => {});
      if (captureMode === "recording") stopFileCapture().catch(() => {});
    }
  }, [sessionStatus, captureMode, stopMicCapture, stopFileCapture, isDemoMode]);

  useEffect(() => {
    if (isDemoMode) return; // In demo mode, useLiveDemoPlayback handles playback & simulation

    let cancelled = false;
    reset();

    wsService
      .connect(sessionId)
      .then(() => {
        if (!cancelled && captureMode === "mock") {
          wsService.startDemo();
        } else if (!cancelled && captureMode === "live") {
          // Normal microphone analysis — unchanged
          startMicCapture();
          notificationService.notifyMicAnalysisStarted().catch(() => {});
        } else if (!cancelled && captureMode === "recording") {
          // SIH recording: stream WAV files through the existing audio pipeline
          // The microphone is NOT started — file audio is the sole source
          startFileCapture();
          notificationService.notifyMicAnalysisStarted().catch(() => {});
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      if (captureMode === "live") stopMicCapture().catch(() => {});
      if (captureMode === "recording") stopFileCapture().catch(() => {});
      notificationService.reset();
      wsService.disconnect();
      stopSession(sessionId).catch(() => {});
      reset();
    };
  }, [sessionId, captureMode, reset, startMicCapture, stopMicCapture, startFileCapture, stopFileCapture, stopSession, isDemoMode]);

  const handleEndSession = useCallback(() => {
    if (isEndingRef.current) return;
    isEndingRef.current = true;
    setIsEnding(true);

    if (isDemoMode) {
      demo.stop().catch(() => {});
    } else {
      // 1. Stop native microphone / file capture immediately
      if (mode === "live") {
        stopMicCapture().catch(() => {});
      } else if (mode === "recording") {
        stopFileCapture().catch(() => {});
      }

      // 2. Disconnect WebSocket cleanly and immediately
      wsService.disconnect();

      // 3. Reset notifications & local risk store immediately
      notificationService.reset();
      reset();

      // 5. Fire-and-forget backend session stop asynchronously in the background
      stopSession(sessionId).catch(() => {});
    }

    // 4. Immediately transition the mobile UI out of the active/loading state (<200ms)
    if (navigation.canGoBack()) {
      navigation.goBack();
    } else {
      navigation.navigate("Home");
    }
  }, [sessionId, mode, stopMicCapture, stopFileCapture, stopSession, reset, navigation, isDemoMode, demo]);

  const resolveEvidenceStatus = () => {
    if (isDemoMode) {
      const banner = demo.multimodalState.warningBanner;
      const bgMap = {
        safe: `${colors.success}14`,
        info: `${colors.accent}14`,
        warning: `${colors.warning}18`,
        critical: `${colors.critical || colors.danger}18`,
      };
      const borderMap = {
        safe: `${colors.success}44`,
        info: `${colors.accent}44`,
        warning: `${colors.warning}55`,
        critical: `${colors.critical || colors.danger}55`,
      };
      const textMap = {
        safe: colors.success,
        info: colors.accent,
        warning: colors.warning,
        critical: colors.critical || colors.danger,
      };

      return {
        message: banner.message,
        subMessage: banner.subMessage,
        icon: banner.icon,
        bg: bgMap[banner.severity],
        border: borderMap[banner.severity],
        textColor: textMap[banner.severity],
      };
    }

    if (sessionStatus !== "monitoring") {
      return {
        message: "Connecting audio stream...",
        subMessage: "Initializing real-time analysis pipeline",
        icon: "🎙",
        bg: `${colors.accent}14`,
        border: `${colors.accent}44`,
        textColor: colors.accent,
      };
    }

    const hasFinancial = Boolean(
      context &&
        (context.financial_request ||
          context.otp_request ||
          context.credential_request ||
          context.sensitive_information_request)
    );
    const hasSocialEng = Boolean(
      context &&
        (context.urgency ||
          context.social_engineering ||
          context.authority_claim)
    );
    const hasAcousticThreat = Boolean(
      authenticity &&
        (authenticity.spoof_probability >= 0.50 ||
          authenticity.acoustic_anomaly === "HIGH" ||
          authenticity.score >= 50)
    );
    const hasIdentityMismatch = Boolean(
      identity &&
        (identity.enrollment_status === "MISMATCH" ||
          (identity.match_score !== null && identity.match_score < 40))
    );

    if (riskState === "critical") {
      return {
        message:
          hasFinancial && hasAcousticThreat
            ? "Critical fraud & synthetic-voice risk detected"
            : hasFinancial
            ? "Critical fraud intent detected"
            : hasAcousticThreat
            ? "Critical synthetic-voice risk detected"
            : "Critical fraud indicators detected — verify before proceeding",
        subMessage: "Do not share credentials or authorize transactions",
        icon: "🚨",
        bg: `${colors.critical || colors.danger}18`,
        border: `${colors.critical || colors.danger}55`,
        textColor: colors.critical || colors.danger,
      };
    }

    if (riskState === "high") {
      let mainMsg = "High-risk indicators detected";
      let subMsg = "Verify caller before sharing sensitive information";

      if (hasAcousticThreat && hasFinancial) {
        mainMsg = "High synthetic voice & financial risk detected";
        subMsg = "Corroborated synthetic speech and transaction request";
      } else if (hasAcousticThreat) {
        mainMsg = "High synthetic-voice risk detected";
        subMsg = "Acoustic patterns indicate artificial or cloned voice";
      } else if (hasFinancial) {
        mainMsg = "High-risk financial intent detected";
        subMsg = "Sensitive credentials or transfer request identified";
      } else if (hasSocialEng) {
        mainMsg = "High-risk social-engineering intent detected";
        subMsg = "Urgency, impersonation or pressure tactics observed";
      } else if (hasIdentityMismatch) {
        mainMsg = "Speaker identity could not be verified";
        subMsg = "Voice profile does not match expected speaker";
      }

      return {
        message: mainMsg,
        subMessage: subMsg,
        icon: "⚠️",
        bg: `${colors.danger}14`,
        border: `${colors.danger}44`,
        textColor: colors.danger,
      };
    }

    if (riskState === "suspicious") {
      let mainMsg = "Suspicious voice or conversation signals detected";
      let subMsg = "Additional verification recommended";

      if (hasAcousticThreat) {
        mainMsg = "Suspicious synthetic-voice indicators detected";
        subMsg = "Acoustic anomaly detected — continue with caution";
      } else if (hasFinancial || hasSocialEng) {
        mainMsg = "Suspicious social-engineering context detected";
        subMsg = "Sensitive conversation topic or pressure detected";
      } else if (hasIdentityMismatch) {
        mainMsg = "Speaker identity variance detected";
        subMsg = "Confidence in speaker identity is reduced";
      }

      return {
        message: mainMsg,
        subMessage: subMsg,
        icon: "⚡",
        bg: `${colors.warning}18`,
        border: `${colors.warning}55`,
        textColor: colors.warning,
      };
    }

    if (riskState === "low") {
      return {
        message: context?.transcript
          ? "Voice appears low risk"
          : "No significant threat indicators detected",
        subMessage: "No significant fraud or credential intent detected",
        icon: "🛡",
        bg: `${colors.success}14`,
        border: `${colors.success}44`,
        textColor: colors.success,
      };
    }

    // Default: insufficient_evidence
    return {
      message: "Insufficient voice evidence — continue speaking",
      subMessage: "Real-time acoustic and semantic engines listening",
      icon: "🎙",
      bg: `${colors.accent}14`,
      border: `${colors.accent}44`,
      textColor: colors.accent,
    };
  };

  const activeAuthenticity = isDemoMode ? (demo.multimodalState.authenticity as any) : authenticity;
  const activeIdentity = isDemoMode ? (demo.multimodalState.identity as any) : identity;
  const activeContext = isDemoMode ? (demo.multimodalState.context as any) : context;
  const activeDecision = isDemoMode ? demo.multimodalState.decision : decision;
  const activeDecisionReasons = isDemoMode ? demo.multimodalState.decisionReasons : decisionReasons;
  const activeRecommendedAction = isDemoMode ? demo.multimodalState.recommendedAction : recommendedAction;
  const activeEvidenceConfidence = isDemoMode ? demo.multimodalState.evidenceConfidence : evidenceConfidence;
  const activeChallengeState = isDemoMode ? demo.multimodalState.challengeState : challengeState;
  const activeVerificationState = isDemoMode ? demo.multimodalState.verificationState : verificationState;
  const activeEvents = isDemoMode ? demo.multimodalState.detectedEvents : detectedEvents;

  const currentRiskScore = isDemoMode ? demo.displayedScore : riskScore;
  const currentRiskState = isDemoMode ? demo.riskState : riskState;
  const isElevated = currentRiskState === "high" || currentRiskState === "critical";

  const evidenceStatus = resolveEvidenceStatus();
  const latestAlert = alerts[0];

  useEffect(() => {
    if (isDemoMode) {
      if (demo.playbackStatus === "playing" || demo.playbackStatus === "ended") {
        notificationService
          .notifyRiskTransition(
            currentRiskState,
            currentRiskScore,
            activeDecision,
            activeRecommendedAction
          )
          .catch(() => {});
      }
    } else if (sessionStatus === "monitoring") {
      notificationService
        .notifyRiskTransition(riskState, riskScore, decision, recommendedAction)
        .catch(() => {});
    }
  }, [
    isDemoMode,
    demo.playbackStatus,
    currentRiskState,
    currentRiskScore,
    activeDecision,
    activeRecommendedAction,
    sessionStatus,
    riskState,
    riskScore,
    decision,
    recommendedAction,
  ]);

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
        },
      ]}
    >
      <BackgroundWave />

      {/* ── Top Bar / Header ─────────────────────────────────────────────── */}
      <View
        style={[
          styles.header,
          {
            paddingTop: insets.top + 8,
            borderBottomColor: colors.border,
            backgroundColor: isDark ? colors.surface : colors.surface,
          },
        ]}
      >
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backBtn}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <Text style={[styles.backText, { color: colors.textSecondary }]}>‹ Back</Text>
        </TouchableOpacity>

        <View style={styles.headerTitleWrap}>
          <View style={styles.headerTitleRow}>
            {(isDemoMode ? (demo.playbackStatus === "playing" || demo.playbackStatus === "ended") : sessionStatus === "monitoring") && (
              <View style={[styles.liveIndicator, { backgroundColor: colors.success }]} />
            )}
            <Text style={[styles.headerTitle, { color: colors.textPrimary }]}>
              Live Analysis
            </Text>
          </View>
          <Text style={[styles.headerSubtitle, { color: colors.accent }]}>
            {isDemoMode
              ? "● Active Monitoring"
              : sessionStatus === "monitoring"
              ? "● Active Monitoring"
              : "○ Connecting…"}
          </Text>
        </View>

        <TouchableOpacity
          onPress={handleEndSession}
          disabled={isEnding}
          style={[
            styles.endBtn,
            {
              backgroundColor: isEnding ? `${colors.textMuted}18` : `${colors.danger}18`,
              borderColor: isEnding ? `${colors.textMuted}44` : `${colors.danger}44`,
              opacity: isEnding ? 0.6 : 1.0,
            },
          ]}
          accessibilityRole="button"
          accessibilityLabel="End session"
        >
          {isEnding ? (
            <ActivityIndicator size="small" color={colors.danger} />
          ) : (
            <Text style={[styles.endBtnText, { color: colors.danger }]}>End</Text>
          )}
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: Math.max(insets.bottom, 24) + 16 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {!isDemoMode && <PipelineModeBanner mode={pipelineMode} />}

        {/* ── Caller & Channel Information ───── */}
        <View
          style={[
            styles.callerCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: isElevated ? `${colors.danger}50` : colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          {isElevated && (
            <View style={[styles.callerAccentBar, { backgroundColor: colors.danger }]} />
          )}
          <View style={[styles.callerRow, isElevated ? styles.callerRowPadded : null]}>
            <View
              style={[
                styles.callerIcon,
                {
                  backgroundColor: isDark ? `${colors.accent}18` : `${colors.accent}12`,
                  borderColor: `${colors.accent}33`,
                },
              ]}
            >
              {source === "voip" || (mode as string) === "voip" || source === "asterisk" ? (
                <PhoneIcon size={20} color={colors.accent} />
              ) : (
                <MicIcon size={20} color={colors.accent} />
              )}
            </View>
            <View style={styles.callerInfo}>
              <Text style={[styles.callerPhone, { color: colors.textPrimary }]}>
                {source === "voip" || (mode as string) === "voip" || source === "asterisk"
                  ? callerNumber || "SIP / Asterisk Trunk"
                  : "Device Microphone"}
              </Text>
              <Text style={[styles.callerName, { color: colors.textSecondary }]}>
                {source === "voip" || (mode as string) === "voip" || source === "asterisk"
                  ? callerName || "Live VoIP Caller"
                  : "Acoustic Speech Stream"}
              </Text>
            </View>

            <View
              style={[
                styles.sourcePill,
                {
                  backgroundColor: `${colors.accent}18`,
                  borderColor: `${colors.accent}44`,
                  borderRadius: radius.full,
                },
              ]}
            >
              <Text style={[styles.sourceText, { color: colors.accent }]}>
                {source === "voip" || (mode as string) === "voip" || source === "asterisk"
                  ? "VOIP"
                  : "MIC"}
              </Text>
            </View>
          </View>
        </View>

        {/* ── Central Voice Risk Orb (Sections 13, 14, 20) ─────────────────── */}
        <RiskOrb
          score={currentRiskScore}
          state={currentRiskState}
          isActive={isDemoMode ? (demo.playbackStatus === "playing" || demo.playbackStatus === "paused") : sessionStatus === "monitoring"}
          trend={isDemoMode ? demo.riskTrend : riskTrend}
          size={200}
          audioLevel={isDemoMode ? demo.waveformState.rms : audioLevel}
          sublabel={isDemoMode ? demo.sublabel : "LIVE RISK"}
        />

        {/* ── Real-Time Audio-Reactive Waveform ────────────────────────────── */}
        <View
          style={[
            styles.waveformCard,
            {
              backgroundColor: isDark ? colors.surface : "#FFFFFF",
              borderColor: colors.border,
              borderRadius: radius.lg,
            },
          ]}
        >
          <LiveAudioWaveform
            isActive={isDemoMode ? (demo.playbackStatus === "playing" || demo.playbackStatus === "paused") : sessionStatus === "monitoring"}
            audioLevel={isDemoMode ? demo.waveformState.rms : audioLevel}
            bars={isDemoMode ? demo.waveformState.bars : undefined}
            isSilence={isDemoMode ? demo.waveformState.isSilence : false}
            height={44}
            barCount={36}
          />
        </View>

        {/* ── Sub-scores Row: Synthetic, Identity, Context ── */}
        <View
          style={[
            styles.subMetricsCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: isElevated ? `${colors.danger}44` : colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          {/* Synthetic Risk */}
          {(() => {
            const hasAuth = activeAuthenticity && activeAuthenticity.confidence > 0;
            const authColor = hasAuth
              ? activeAuthenticity.score >= 50
                ? colors.danger
                : activeAuthenticity.score >= 25
                ? colors.warning
                : colors.success
              : colors.textMuted;
            return (
              <View style={styles.subMetricCol}>
                <MicIcon size={16} color={authColor} style={{ marginBottom: 2 }} />
                <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
                  Synthetic
                </Text>
                <Text style={[styles.subMetricScore, { color: authColor }]}>
                  {hasAuth ? `${activeAuthenticity.score}%` : "—"}
                </Text>
                <View
                  style={[
                    styles.subMetricBandChip,
                    { backgroundColor: `${authColor}18`, borderColor: `${authColor}35` },
                  ]}
                >
                  <Text style={[styles.subMetricBandText, { color: authColor }]}>
                    {hasAuth ? activeAuthenticity.acoustic_anomaly : "UNAVAILABLE"}
                  </Text>
                </View>
              </View>
            );
          })()}

          <View style={[styles.subMetricDivider, { backgroundColor: colors.border }]} />

          {/* Identity */}
          {(() => {
            const hasId =
              activeIdentity &&
              activeIdentity.enrollment_status !== "NOT_ENROLLED" &&
              activeIdentity.match_score !== null;
            const idColor = !hasId
              ? colors.textMuted
              : activeIdentity.match_score >= 75
              ? colors.success
              : activeIdentity.match_score >= 50
              ? colors.warning
              : colors.danger;
            return (
              <View style={styles.subMetricCol}>
                <UserIcon size={16} color={idColor} style={{ marginBottom: 2 }} />
                <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
                  Identity
                </Text>
                <Text style={[styles.subMetricScore, { color: idColor }]}>
                  {activeIdentity?.enrollment_status === "NOT_ENROLLED"
                    ? "—"
                    : hasId
                    ? `${activeIdentity.match_score}%`
                    : "—"}
                </Text>
                <View
                  style={[
                    styles.subMetricBandChip,
                    { backgroundColor: `${idColor}18`, borderColor: `${idColor}35` },
                  ]}
                >
                  <Text style={[styles.subMetricBandText, { color: idColor }]}>
                    {activeIdentity?.enrollment_status === "NOT_ENROLLED"
                      ? "NOT ENROLLED"
                      : activeIdentity?.consistency?.toUpperCase() || "UNAVAILABLE"}
                  </Text>
                </View>
              </View>
            );
          })()}

          <View style={[styles.subMetricDivider, { backgroundColor: colors.border }]} />

          {/* Context Threat */}
          {(() => {
            const hasCtx = isDemoMode
              ? !demo.transcriptState.isSilence
              : Boolean(activeContext && activeContext.transcript);
            const ctxColor = !hasCtx
              ? colors.textMuted
              : activeContext.score >= 50
              ? colors.danger
              : activeContext.score >= 25
              ? colors.warning
              : colors.success;
            return (
              <View style={styles.subMetricCol}>
                <Text style={styles.subMetricIcon}>💬</Text>
                <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
                  Context
                </Text>
                <Text style={[styles.subMetricScore, { color: ctxColor }]}>
                  {hasCtx ? `${activeContext.score}` : "—"}
                </Text>
                <View
                  style={[
                    styles.subMetricBandChip,
                    { backgroundColor: `${ctxColor}18`, borderColor: `${ctxColor}35` },
                  ]}
                >
                  <Text style={[styles.subMetricBandText, { color: ctxColor }]}>
                    {hasCtx ? activeContext.consequence.toUpperCase() : "NO SPEECH"}
                  </Text>
                </View>
              </View>
            );
          })()}
        </View>

        {/* ── Dynamic Live Evidence & Status Banner ────────────────────────── */}
        <View
          style={[
            styles.evidenceBanner,
            {
              backgroundColor: evidenceStatus.bg,
              borderColor: evidenceStatus.border,
              borderRadius: radius.xl,
            },
          ]}
        >
          <View style={styles.evidenceHeaderRow}>
            <Text style={{ fontSize: 18 }}>{evidenceStatus.icon}</Text>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[styles.evidenceTitleText, { color: evidenceStatus.textColor }]}>
                {evidenceStatus.message}
              </Text>
              {evidenceStatus.subMessage ? (
                <Text style={[styles.evidenceSubText, { color: colors.textSecondary }]}>
                  {evidenceStatus.subMessage}
                </Text>
              ) : null}
            </View>
            {(isDemoMode ? (demo.playbackStatus === "playing" || demo.playbackStatus === "ended") : sessionStatus === "monitoring") && (
              <View
                style={[
                  styles.livePill,
                  {
                    backgroundColor: `${evidenceStatus.textColor}20`,
                    borderColor: `${evidenceStatus.textColor}40`,
                  },
                ]}
              >
                <Text style={[styles.livePillText, { color: evidenceStatus.textColor }]}>
                  LIVE
                </Text>
              </View>
            )}
          </View>
        </View>

        {/* ── Partial Live Transcript (design.md Section 24) ──────────────── */}
        <View
          style={[
            styles.transcriptCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: (isDemoMode ? !demo.transcriptState.isSilence : Boolean(activeContext?.transcript))
                ? `${colors.accent}44`
                : colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <View style={styles.transcriptHeaderRow}>
            <Text style={[styles.transcriptHeader, { color: colors.textSecondary }]}>
              💬 LIVE TRANSCRIPT
            </Text>
            <Text style={[styles.transcriptEngine, { color: colors.textMuted }]}>
              {isDemoMode ? demo.transcriptState.model : (activeContext?.transcript_model || "Deepgram Nova-2")}
            </Text>
          </View>
          {isDemoMode ? (
            demo.transcriptState.transcript && demo.transcriptState.transcript !== "No speech detected" ? (
              <View
                style={[
                  styles.transcriptQuoteBlock,
                  {
                    backgroundColor: `${colors.accent}0D`,
                    borderLeftColor: colors.accent,
                  },
                ]}
              >
                <Text style={[styles.transcriptContent, { color: colors.textPrimary }]}>
                  {`"${demo.transcriptState.transcript}"`}
                </Text>
              </View>
            ) : (
              <Text style={[styles.transcriptContent, { color: colors.textMuted, fontStyle: "italic" }]}>
                No speech detected
              </Text>
            )
          ) : activeContext?.transcript ? (
            <View
              style={[
                styles.transcriptQuoteBlock,
                {
                  backgroundColor: `${colors.accent}0D`,
                  borderLeftColor: colors.accent,
                },
              ]}
            >
              <Text style={[styles.transcriptContent, { color: colors.textPrimary }]}>
                {`"${activeContext.transcript}"`}
              </Text>
            </View>
          ) : (
            <Text style={[styles.transcriptContent, { color: colors.textMuted, fontStyle: "italic" }]}>
              Listening for spoken speech… Transcriptions stream here in real time.
            </Text>
          )}
        </View>

        {/* ── Action Buttons: Challenge / Independent Verification ────────── */}
        <View style={styles.actionControlsRow}>
          <TouchableOpacity
            style={[
              styles.controlBtn,
              {
                backgroundColor:
                  activeChallengeState !== "idle"
                    ? `${colors.accent}18`
                    : colors.surfaceElevated,
                borderColor:
                  activeChallengeState !== "idle" ? `${colors.accent}50` : colors.border,
                borderRadius: radius.lg,
              },
            ]}
            onPress={() => navigation.navigate("Challenge", { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Challenge Caller"
          >
            <Text style={{ fontSize: 18 }}>🧩</Text>
            <Text
              style={[
                styles.controlBtnText,
                {
                  color:
                    activeChallengeState !== "idle" ? colors.accent : colors.textPrimary,
                },
              ]}
            >
              Challenge
            </Text>
            {activeChallengeState !== "idle" && (
              <View
                style={[
                  styles.controlBtnBadge,
                  {
                    backgroundColor: `${colors.accent}25`,
                    borderColor: `${colors.accent}50`,
                  },
                ]}
              >
                <Text style={[styles.controlBtnSub, { color: colors.accent }]}>
                  {activeChallengeState.toUpperCase()}
                </Text>
              </View>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.controlBtn,
              {
                backgroundColor:
                  activeVerificationState !== "idle"
                    ? `${colors.accentSecondary}18`
                    : colors.surfaceElevated,
                borderColor:
                  activeVerificationState !== "idle"
                    ? `${colors.accentSecondary}50`
                    : colors.border,
                borderRadius: radius.lg,
              },
            ]}
            onPress={() => navigation.navigate("Verification", { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Independent Verification"
          >
            <Text style={{ fontSize: 18 }}>🔐</Text>
            <Text
              style={[
                styles.controlBtnText,
                {
                  color:
                    activeVerificationState !== "idle"
                      ? colors.accentSecondary
                      : colors.textPrimary,
                },
              ]}
            >
              Verify
            </Text>
            {activeVerificationState !== "idle" && (
              <View
                style={[
                  styles.controlBtnBadge,
                  {
                    backgroundColor: `${colors.accentSecondary}20`,
                    borderColor: `${colors.accentSecondary}45`,
                  },
                ]}
              >
                <Text
                  style={[
                    styles.controlBtnSub,
                    { color: colors.accentSecondary },
                  ]}
                >
                  {activeVerificationState.toUpperCase()}
                </Text>
              </View>
            )}
          </TouchableOpacity>
        </View>

        {/* ── Security Decision Panel (design.md Section 21) ──────────────── */}
        <DecisionPanel
          decision={activeDecision}
          reasons={activeDecisionReasons}
          recommendedAction={activeRecommendedAction}
          evidenceConfidence={activeEvidenceConfidence}
        />

        {/* ── Active Alert ────────────────────────────────────────────────── */}
        {isDemoMode ? (
          currentRiskScore >= 25 && (
            <View style={{ marginVertical: 6 }}>
              <AlertCard
                severity={
                  currentRiskScore >= 85
                    ? "critical"
                    : currentRiskScore >= 60
                    ? "error"
                    : "warning"
                }
                title={
                  currentRiskScore >= 85
                    ? "Critical Security Threat"
                    : currentRiskScore >= 60
                    ? "High Risk Alert"
                    : "Suspicious Activity"
                }
                message={
                  currentRiskScore >= 85
                    ? "Critical synthetic-voice risk detected"
                    : currentRiskScore >= 60
                    ? "High synthetic-voice risk detected"
                    : "Suspicious voice activity detected"
                }
                recommendedAction={
                  currentRiskScore >= 85
                    ? "Do not share credentials or authorize transactions"
                    : currentRiskScore >= 60
                    ? "Synthetic speech signature identified — verify caller"
                    : "Acoustic anomaly detected — continue with caution"
                }
              />
            </View>
          )
        ) : (
          latestAlert && (
            <View style={{ marginVertical: 6 }}>
              <AlertCard
                severity={SEVERITY_TO_CARD[latestAlert.severity] ?? "warning"}
                title="Security Alert"
                message={latestAlert.message}
                recommendedAction={latestAlert.recommendedAction}
              />
              <TouchableOpacity
                onPress={() => dismissAlert(latestAlert.id)}
                style={{ alignSelf: "center", paddingVertical: 6 }}
              >
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>Dismiss</Text>
              </TouchableOpacity>
            </View>
          )
        )}

        {/* ── 4 Persistent Evidence Panels (design.md Sections 14 & 22) ────── */}
        <AuthenticityPanel authenticity={activeAuthenticity as any} />
        <IdentityPanel identity={activeIdentity as any} />
        <ActiveLivenessPanel
          challengeState={activeChallengeState as any}
          challengeText={challengeText}
          verificationState={activeVerificationState as any}
          audioActive={isDemoMode ? !demo.waveformState.isSilence : audioActive}
        />
        <ConsequencesPanel context={activeContext as any} />

        {/* ── Event Timeline ──────────────────────────────────────────────── */}
        <EventTimeline events={activeEvents} />

        {/* ── Technical Diagnostics Disclosure ─────────────────────────── */}
        <View style={styles.disclosureBox}>
          <Text style={[styles.disclosureText, { color: colors.textMuted }]}>
            ℹ Dhwani AI analyses device microphone PCM audio. Raw cellular SIM media cannot be recorded on Android.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },

  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
  },
  backBtn: { paddingVertical: 6, paddingRight: 10 },
  backText: { fontSize: 16, fontWeight: "600" },
  headerTitleWrap: { alignItems: "center", gap: 2 },
  headerTitleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  liveIndicator: { width: 7, height: 7, borderRadius: 4 },
  headerTitle: { fontSize: 16, fontWeight: "700" },
  headerSubtitle: { fontSize: 10, fontWeight: "700", letterSpacing: 0.3 },
  endBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 1,
  },
  endBtnText: { fontSize: 12, fontWeight: "700" },

  scroll: { paddingHorizontal: 16, paddingTop: 12, gap: 12 },

  callerCard: {
    borderWidth: 1,
    overflow: "hidden",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  callerAccentBar: { height: 2, width: "100%" },
  callerRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    padding: 14,
  },
  callerRowPadded: { paddingTop: 10 },
  callerIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  callerIconText: { fontSize: 18 },
  callerInfo: { flex: 1 },
  callerPhone: { fontSize: 16, fontWeight: "700" },
  callerName: { fontSize: 12, marginTop: 2 },
  sourcePill: { paddingHorizontal: 10, paddingVertical: 4, borderWidth: 1 },
  sourceText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.5 },

  subMetricsCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderWidth: 1,
    paddingVertical: 16,
    paddingHorizontal: 8,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  subMetricCol: { alignItems: "center", flex: 1, gap: 4 },
  subMetricIcon: { fontSize: 15, marginBottom: 1 },
  subMetricLabel: { fontSize: 10, fontWeight: "600", letterSpacing: 0.3 },
  subMetricScore: { fontSize: 22, fontWeight: "800", letterSpacing: -0.5 },
  subMetricBandChip: {
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 99,
    borderWidth: 1,
  },
  subMetricBandText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.4,
    textTransform: "uppercase",
  },
  subMetricDivider: { width: 1, height: 40 },

  evidenceBanner: { borderWidth: 1, padding: 13 },
  evidenceHeaderRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  evidenceTitleText: { fontSize: 13, fontWeight: "700" },
  evidenceSubText: { fontSize: 11, fontWeight: "500", marginTop: 2 },
  livePill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 99,
    borderWidth: 1,
    marginLeft: 4,
  },
  livePillText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.8,
  },
  waveformCard: {
    borderWidth: 1,
    paddingVertical: 10,
    paddingHorizontal: 12,
    marginVertical: 6,
    alignItems: "center",
    justifyContent: "center",
  },

  transcriptCard: {
    borderWidth: 1,
    padding: 14,
    gap: 8,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 5,
    elevation: 2,
  },

  transcriptHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  transcriptHeader: { fontSize: 10, fontWeight: "800", letterSpacing: 1.0 },
  transcriptEngine: { fontSize: 9, fontWeight: "500" },
  transcriptQuoteBlock: {
    borderLeftWidth: 3,
    paddingLeft: 10,
    paddingVertical: 6,
    borderRadius: 4,
  },
  transcriptContent: { fontSize: 13, lineHeight: 19 },

  actionControlsRow: { flexDirection: "row", gap: 10 },
  controlBtn: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 14,
    paddingHorizontal: 8,
    alignItems: "center",
    gap: 5,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 5,
    elevation: 2,
  },
  controlBtnText: { fontSize: 13, fontWeight: "700" },
  controlBtnBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 99,
    borderWidth: 1,
  },
  controlBtnSub: { fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },

  disclosureBox: { paddingVertical: 6, paddingHorizontal: 2, marginTop: 4 },
  disclosureText: { fontSize: 10, lineHeight: 14 },

  demoControlsWrap: {
    gap: 8,
    marginVertical: 2,
  },
  demoDisclosureCard: {
    borderWidth: 1,
    padding: 12,
    marginTop: 4,
    gap: 4,
  },
  demoDisclosureHeader: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.6,
    textTransform: "uppercase",
  },
  demoDisclosureBody: {
    fontSize: 11,
    lineHeight: 16,
  },
});
