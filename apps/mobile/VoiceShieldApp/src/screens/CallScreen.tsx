import React, { useCallback, useEffect } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
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
      stopMicCapture();
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
        stopMicCapture();
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

  const handleEndSession = useCallback(() => {
    Alert.alert("End Monitoring", "Stop monitoring this voice stream?", [
      { text: "Cancel", style: "cancel" },
      {
        text: "End Session",
        style: "destructive",
        onPress: async () => {
          if (mode === "live") {
            await stopMicCapture();
          }
          notificationService.reset();
          wsService.disconnect();
          try {
            await stopSession(sessionId);
          } catch {}
          if (navigation.canGoBack()) {
            navigation.goBack();
          } else {
            navigation.navigate("Home");
          }
        },
      },
    ]);
  }, [sessionId, mode, stopMicCapture, stopSession, navigation]);

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
          style={[
            styles.endBtn,
            {
              backgroundColor: `${colors.danger}18`,
              borderColor: `${colors.danger}44`,
            },
          ]}
          accessibilityRole="button"
          accessibilityLabel="End session"
        >
          <Text style={[styles.endBtnText, { color: colors.danger }]}>End</Text>
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
                {mode === "live" ? "Device Microphone Feed" : "+91 91234 56789"}
              </Text>
              <Text style={[styles.callerName, { color: colors.textSecondary }]}>
                {mode === "live" ? "Acoustic Speech Stream" : "Unknown Caller"}
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
                {mode === "live" ? "Device Mic" : "Simulated Audio"}
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

        {/* ── Sub-scores Row: Authenticity, Identity, Context ─────────────── */}
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
              Authenticity
            </Text>
            <Text style={[styles.subMetricScore, { color: colors.textPrimary }]}>
              {authenticity ? authenticity.score : "--"}
            </Text>
            <Text style={[styles.subMetricBand, { color: colors.textMuted }]}>
              {authenticity ? authenticity.acoustic_anomaly : "Accumulating"}
            </Text>
          </View>

          <View style={[styles.subMetricDivider, { backgroundColor: colors.border }]} />

          <View style={styles.subMetricCol}>
            <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
              Identity
            </Text>
            <Text style={[styles.subMetricScore, { color: colors.textPrimary }]}>
              {identity && identity.enrollment_status !== "NOT_ENROLLED"
                ? `${identity.match_score}%`
                : "--"}
            </Text>
            <Text style={[styles.subMetricBand, { color: colors.textMuted }]}>
              {identity?.enrollment_status === "NOT_ENROLLED"
                ? "No Reference"
                : identity?.consistency || "Awaiting"}
            </Text>
          </View>

          <View style={[styles.subMetricDivider, { backgroundColor: colors.border }]} />

          <View style={styles.subMetricCol}>
            <Text style={[styles.subMetricLabel, { color: colors.textSecondary }]}>
              Context
            </Text>
            <Text style={[styles.subMetricScore, { color: colors.textPrimary }]}>
              {context ? context.score : "--"}
            </Text>
            <Text style={[styles.subMetricBand, { color: colors.textMuted }]}>
              {context ? context.consequence.toUpperCase() : "Awaiting STT"}
            </Text>
          </View>
        </View>

        {/* ── Context Intent Banner ───────────────────────────────────────── */}
        <View
          style={[
            styles.intentBanner,
            {
              backgroundColor:
                context && (context.financial_request || context.otp_request || context.urgency)
                  ? `${colors.danger}18`
                  : `${colors.accent}14`,
              borderColor:
                context && (context.financial_request || context.otp_request || context.urgency)
                  ? `${colors.danger}44`
                  : `${colors.accent}44`,
              borderRadius: radius.sm,
            },
          ]}
        >
          <Text
            style={[
              styles.intentText,
              {
                color:
                  context && (context.financial_request || context.otp_request || context.urgency)
                    ? colors.danger
                    : colors.accent,
              },
            ]}
          >
            {context && (context.financial_request || context.otp_request || context.urgency)
              ? "⚠️ Sensitive / high-consequence request detected"
              : "🛡 No sensitive financial or credential intent detected"}
          </Text>
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
            LIVE TRANSCRIPT (PARTIAL)
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
  intentBanner: {
    borderWidth: 1,
    padding: 10,
    alignItems: "center",
  },
  intentText: {
    fontSize: 12,
    fontWeight: "600",
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
