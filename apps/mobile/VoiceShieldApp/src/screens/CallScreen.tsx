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
import { wsService } from "../services/websocket/wsService";

import { RiskOrb } from "../components/RiskOrb";
import { RiskBadge } from "../components/RiskBadge";
import { AuthenticityPanel } from "../components/AuthenticityPanel";
import { IdentityPanel } from "../components/IdentityPanel";
import { ActiveLivenessPanel } from "../components/ActiveLivenessPanel";
import { ConsequencesPanel } from "../components/ConsequencesPanel";
import { EventTimeline } from "../components/EventTimeline";
import { DecisionPanel } from "../components/DecisionPanel";
import { AlertCard } from "../components/AlertCard";
import { PipelineModeBanner } from "../components/PipelineModeBanner";
import { RootStackParamList } from "../navigation/AppNavigator";
import { SessionStatus } from "../types";
import { notificationService } from "../services/notification/notificationService";

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
  const { colors, riskColors, radius, isDark } = useTheme();

  const { sessionId, mode = "live" } = route.params;
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
  const audioQuality = useRiskStore((s) => s.audioQuality);
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
  const lastError = useRiskStore((s) => s.lastError);
  const evidenceConfidence = useRiskStore((s) => s.evidenceConfidence);
  const dismissAlert = useRiskStore((s) => s.dismissAlert);
  const reset = useRiskStore((s) => s.reset);

  const [isEnding, setIsEnding] = useState(false);
  const isEndingRef = useRef(false);

  const {
    isRecording: isMicRecording,
    permissionStatus: micPermission,
    error: micError,
    metrics: micMetrics,
    requestPermission: requestMicPermission,
    start: startMicCapture,
    stop: stopMicCapture,
  } = useAudioCapture(false);

  useRiskStream(sessionId);

  useEffect(() => {
    if (sessionStatus === "ended" && mode === "live") {
      stopMicCapture().catch(() => {});
    }
  }, [sessionStatus, mode, stopMicCapture]);

  useEffect(() => {
    let cancelled = false;
    reset();

    wsService
      .connect(sessionId)
      .then(() => {
        if (!cancelled && mode === "mock") {
          wsService.startDemo();
        } else if (!cancelled && mode === "live") {
          startMicCapture();
          notificationService.notifyMicAnalysisStarted().catch(() => {});
        }
      })
      .catch(() => {});

    return () => {
      cancelled = true;
      if (mode === "live") {
        stopMicCapture().catch(() => {});
      }
      notificationService.reset();
      wsService.disconnect();
      stopSession(sessionId).catch(() => {});
      reset();
    };
  }, [sessionId, mode, reset, startMicCapture, stopMicCapture, stopSession]);

  useEffect(() => {
    if (sessionStatus === "monitoring") {
      notificationService
        .notifyRiskTransition(riskState, riskScore, decision, recommendedAction)
        .catch(() => {});
    }
  }, [sessionStatus, riskState, riskScore, decision, recommendedAction]);

  const handleEndSession = useCallback(async () => {
    // Single-click guard: if already ending or ended, strictly ignore all further taps
    if (isEndingRef.current) return;
    isEndingRef.current = true;
    setIsEnding(true);

    try {
      if (mode === "live") {
        await stopMicCapture().catch(() => {});
      }
      notificationService.reset();
      wsService.disconnect();
      try {
        await stopSession(sessionId);
      } catch {}
    } finally {
      if (navigation.canGoBack()) {
        navigation.goBack();
      } else {
        navigation.navigate("Home");
      }
    }
  }, [sessionId, mode, stopMicCapture, stopSession, navigation]);

  const resolveEvidenceStatus = () => {
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

  const evidenceStatus = resolveEvidenceStatus();
  const latestAlert = alerts[0];
  const isElevated = riskState === "high" || riskState === "critical";

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
        },
      ]}
    >
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
          <Text style={[styles.headerTitle, { color: colors.textPrimary }]}>
            Live Analysis
          </Text>
          <Text style={[styles.headerSubtitle, { color: colors.accent }]}>
            {sessionStatus === "monitoring" ? "Active Monitoring" : "Session Connected"}
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
      >
        <PipelineModeBanner mode={pipelineMode} />

        {/* ── Caller & Channel Information (design.md Section 22 & 23) ───── */}
        <View
          style={[
            styles.callerCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.callerRow}>
            <View>
              <Text style={[styles.callerPhone, { color: colors.textPrimary }]}>
                {source === "voip" || (mode as string) === "voip" || source === "asterisk"
                  ? callerNumber || "SIP / Asterisk Trunk"
                  : mode === "live"
                  ? "Device Microphone Feed"
                  : "+91 91234 56789"}
              </Text>
              <Text style={[styles.callerName, { color: colors.textSecondary }]}>
                {source === "voip" || (mode as string) === "voip" || source === "asterisk"
                  ? callerName || "Live VoIP Caller"
                  : mode === "live"
                  ? "Acoustic Speech Stream"
                  : "Unknown Caller"}
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
                  ? "LIVE VOIP / ASTERISK"
                  : mode === "live"
                  ? "Device Mic"
                  : "Simulated Audio"}
              </Text>
            </View>
          </View>
        </View>

        {/* ── Central Voice Risk Orb (Section 14, 22, 23) ─────────────────── */}
        <RiskOrb
          score={riskScore}
          state={riskState}
          isActive={sessionStatus === "monitoring"}
          trend={riskTrend}
          size={210}
        />

        {/* ── Sub-scores Row: Synthetic Risk, Identity Match, Context Threat ── */}
        <View
          style={[
            styles.subMetricsCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: isElevated ? `${colors.danger}44` : colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.subMetricCol}>
            <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
              Synthetic Risk
            </Text>
            <Text
              style={[
                styles.subMetricScore,
                {
                  color:
                    authenticity && authenticity.confidence > 0
                      ? authenticity.score >= 50
                        ? colors.danger
                        : authenticity.score >= 25
                        ? colors.warning
                        : colors.success
                      : colors.textPrimary,
                  fontSize: authenticity && authenticity.confidence > 0 ? 20 : 13,
                },
              ]}
            >
              {authenticity && authenticity.confidence > 0
                ? `${authenticity.score}%`
                : "Analyzing..."}
            </Text>
            <Text style={[styles.subMetricBand, { color: colors.textMuted }]}>
              {authenticity && authenticity.confidence > 0
                ? authenticity.acoustic_anomaly
                : "Accumulating"}
            </Text>
          </View>

          <View style={[styles.subMetricDivider, { backgroundColor: colors.border }]} />

          <View style={styles.subMetricCol}>
            <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
              Identity Match
            </Text>
            <Text
              style={[
                styles.subMetricScore,
                {
                  color: colors.textPrimary,
                  fontSize:
                    identity &&
                    identity.enrollment_status !== "NOT_ENROLLED" &&
                    identity.match_score !== null
                      ? 20
                      : 12,
                },
              ]}
            >
              {identity?.enrollment_status === "NOT_ENROLLED"
                ? "No Reference"
                : identity && identity.match_score !== null
                ? `${identity.match_score}%`
                : "Analyzing..."}
            </Text>
            <Text style={[styles.subMetricBand, { color: colors.textMuted }]}>
              {identity?.enrollment_status === "NOT_ENROLLED"
                ? "Unenrolled"
                : identity?.consistency || "Awaiting"}
            </Text>
          </View>

          <View style={[styles.subMetricDivider, { backgroundColor: colors.border }]} />

          <View style={styles.subMetricCol}>
            <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
              Context Threat
            </Text>
            <Text
              style={[
                styles.subMetricScore,
                {
                  color:
                    context && context.transcript
                      ? context.score >= 50
                        ? colors.danger
                        : context.score >= 25
                        ? colors.warning
                        : colors.success
                      : colors.textPrimary,
                  fontSize: context && context.transcript ? 20 : 13,
                },
              ]}
            >
              {context && context.transcript ? `${context.score} / 100` : "Analyzing..."}
            </Text>
            <Text style={[styles.subMetricBand, { color: colors.textMuted }]}>
              {context && context.transcript
                ? context.consequence.toUpperCase()
                : "Awaiting STT"}
            </Text>
          </View>
        </View>

        {/* ── Dynamic Live Evidence & Status Banner ────────────────────────── */}
        <View
          style={[
            styles.evidenceBanner,
            {
              backgroundColor: evidenceStatus.bg,
              borderColor: evidenceStatus.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.evidenceHeaderRow}>
            <Text style={{ fontSize: 16 }}>{evidenceStatus.icon}</Text>
            <Text style={[styles.evidenceTitleText, { color: evidenceStatus.textColor }]}>
              {evidenceStatus.message}
            </Text>
          </View>
          {evidenceStatus.subMessage ? (
            <Text style={[styles.evidenceSubText, { color: colors.textSecondary }]}>
              {evidenceStatus.subMessage}
            </Text>
          ) : null}
        </View>

        {/* ── Partial Live Transcript ─────────────────────────────────────── */}
        <View
          style={[
            styles.transcriptCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <Text style={[styles.transcriptHeader, { color: colors.textSecondary }]}>
            LIVE TRANSCRIPT
          </Text>
          <Text
            style={[
              styles.transcriptContent,
              {
                color: context?.transcript ? colors.textPrimary : colors.textMuted,
                fontStyle: context?.transcript ? "normal" : "italic",
              },
            ]}
          >
            {context?.transcript
              ? `"${context.transcript}"`
              : "Listening for spoken speech… Transcriptions will stream here in real time."}
          </Text>
        </View>

        {/* ── Action Buttons: Challenge / Independent Verification ────────── */}
        <View style={styles.actionControlsRow}>
          <TouchableOpacity
            style={[
              styles.controlBtn,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
            onPress={() => navigation.navigate("Challenge", { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Challenge Caller"
          >
            <Text style={{ fontSize: 16 }}>🧩</Text>
            <Text style={[styles.controlBtnText, { color: colors.textPrimary }]}>
              Challenge Caller
            </Text>
            {challengeState !== "idle" && (
              <Text style={[styles.controlBtnSub, { color: colors.accent }]}>
                {challengeState.toUpperCase()}
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.controlBtn,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
            onPress={() => navigation.navigate("Verification", { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Independent Verification"
          >
            <Text style={{ fontSize: 16 }}>🔐</Text>
            <Text style={[styles.controlBtnText, { color: colors.textPrimary }]}>
              Verify Channel
            </Text>
            {verificationState !== "idle" && (
              <Text style={[styles.controlBtnSub, { color: colors.accent }]}>
                {verificationState.toUpperCase()}
              </Text>
            )}
          </TouchableOpacity>
        </View>

        {/* ── Security Decision ───────────────────────────────────────────── */}
        <DecisionPanel
          decision={decision}
          reasons={decisionReasons}
          recommendedAction={recommendedAction}
          evidenceConfidence={evidenceConfidence}
        />

        {/* ── Active Alert ────────────────────────────────────────────────── */}
        {latestAlert && (
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
        )}

        {/* ── 4 Persistent Evidence Panels ────────────────────────────────── */}
        <AuthenticityPanel authenticity={authenticity} />
        <IdentityPanel identity={identity} />
        <ActiveLivenessPanel
          challengeState={challengeState}
          challengeText={challengeText}
          verificationState={verificationState}
          audioActive={audioActive}
        />
        <ConsequencesPanel context={context} />

        {/* ── Event Timeline ──────────────────────────────────────────────── */}
        <EventTimeline events={detectedEvents} />

        {/* ── Technical Diagnostics Disclosure ────────────────────────────── */}
        <View
          style={[
            styles.disclosureBox,
            {
              backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
              borderColor: colors.border,
              borderRadius: radius.sm,
            },
          ]}
        >
          <Text style={[styles.disclosureText, { color: colors.textMuted }]}>
            ℹ Notice: Audio analysis evaluates captured device microphone PCM. Raw cellular SIM media cannot be recorded by Android applications.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
  },
  backBtn: {
    paddingVertical: 6,
    paddingRight: 10,
  },
  backText: {
    fontSize: 16,
    fontWeight: "600",
  },
  headerTitleWrap: {
    alignItems: "center",
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  headerSubtitle: {
    fontSize: 11,
    fontWeight: "600",
    marginTop: 1,
  },
  endBtn: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 999,
    borderWidth: 1,
  },
  endBtnText: {
    fontSize: 12,
    fontWeight: "700",
  },
  scroll: {
    paddingHorizontal: 16,
    paddingTop: 12,
    gap: 12,
  },
  callerCard: {
    borderWidth: 1,
    padding: 14,
  },
  callerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  callerPhone: {
    fontSize: 16,
    fontWeight: "700",
  },
  callerName: {
    fontSize: 12,
    marginTop: 2,
  },
  sourcePill: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
  },
  sourceText: {
    fontSize: 11,
    fontWeight: "700",
  },
  subMetricsCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderWidth: 1,
    paddingVertical: 14,
    paddingHorizontal: 8,
  },
  subMetricCol: {
    alignItems: "center",
    flex: 1,
  },
  subMetricLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  subMetricScore: {
    fontSize: 20,
    fontWeight: "800",
    marginVertical: 2,
  },
  subMetricBand: {
    fontSize: 10,
    fontWeight: "500",
  },
  subMetricDivider: {
    width: 1,
    height: 32,
  },
  evidenceBanner: {
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  evidenceHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  evidenceTitleText: {
    fontSize: 13,
    fontWeight: "700",
    flex: 1,
  },
  evidenceSubText: {
    fontSize: 11,
    fontWeight: "500",
    paddingLeft: 24,
  },
  transcriptCard: {
    borderWidth: 1,
    padding: 14,
    gap: 6,
  },
  transcriptHeader: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  transcriptContent: {
    fontSize: 13,
    lineHeight: 18,
  },
  actionControlsRow: {
    flexDirection: "row",
    gap: 10,
  },
  controlBtn: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 12,
    paddingHorizontal: 8,
    alignItems: "center",
    gap: 4,
  },
  controlBtnText: {
    fontSize: 12,
    fontWeight: "700",
  },
  controlBtnSub: {
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  disclosureBox: {
    borderWidth: 1,
    padding: 12,
    marginTop: 6,
  },
  disclosureText: {
    fontSize: 11,
    lineHeight: 15,
  },
});
