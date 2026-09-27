import React, { useCallback, useState, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  Switch,
  Platform,
} from "react-native";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "../utils/theme";
import { useSessionStore } from "../store/sessionStore";
import { useCallScreeningStore } from "../store/callScreeningStore";
import { useRiskStore } from "../store/riskStore";
import { useAuthStore } from "../store/authStore";
import { RootStackParamList } from "../navigation/AppNavigator";
import { RiskState } from "../types";
import { ScreenedCallEvent } from "../types/telecom";

import { DhwaniLogo } from "../components/DhwaniLogo";
import { RiskOrb } from "../components/RiskOrb";
import { RiskBadge } from "../components/RiskBadge";
import { CallRow } from "../components/CallRow";
import { BottomNavigation } from "../components/BottomNavigation";
import { AuthenticityPanel } from "../components/AuthenticityPanel";
import { IdentityPanel } from "../components/IdentityPanel";
import { ActiveLivenessPanel } from "../components/ActiveLivenessPanel";
import { ConsequencesPanel } from "../components/ConsequencesPanel";

type Nav = NativeStackNavigationProp<RootStackParamList>;

const asCallRiskState = (riskState: string | undefined | null): RiskState => {
  switch (riskState?.toLowerCase()) {
    case "insufficient_evidence":
      return "insufficient_evidence";
    case "safe":
      return "insufficient_evidence";
    case "low":
      return "low";
    case "suspicious":
      return "suspicious";
    case "high":
      return "high";
    case "critical":
      return "critical";
    default:
      return "insufficient_evidence";
  }
};

const asRiskState = (value: string | null): RiskState => {
  const allowed: RiskState[] = [
    "insufficient_evidence",
    "low",
    "suspicious",
    "high",
    "critical",
  ];
  return allowed.includes(value as RiskState)
    ? (value as RiskState)
    : "insufficient_evidence";
};

type FeedItem =
  | {
      kind: "incident";
      id: string;
      timeMs: number;
      timeIso: string;
      sessionId: string;
      riskScore: number;
      action?: string;
      state: RiskState;
    }
  | {
      kind: "screened";
      id: string;
      timeMs: number;
      timeIso: string;
      callerMasked: string;
      callerName: string | null;
      decision: string;
      riskLevel: string;
      riskState: string;
      warningType: string;
      explanation: string;
      state: RiskState;
      record: ScreenedCallEvent;
    };

export const HomeScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, riskColors, radius, isDark } = useTheme();

  // Stores
  const user = useAuthStore((s) => s.user);
  const overview = useSessionStore((s) => s.overview);
  const isRefreshing = useSessionStore((s) => s.isRefreshing);
  const refreshHome = useSessionStore((s) => s.refreshHome);
  const createSession = useSessionStore((s) => s.createSession);
  const startSession = useSessionStore((s) => s.startSession);

  const isRoleHeld = useCallScreeningStore((s) => s.isRoleHeld);
  const checkRoleStatus = useCallScreeningStore((s) => s.checkRoleStatus);
  const loadRecentCalls = useCallScreeningStore((s) => s.loadRecentCalls);
  const recentCalls = useCallScreeningStore((s) => s.recentCalls);
  const requestRole = useCallScreeningStore((s) => s.requestRole);

  const sessionStatus = useRiskStore((s) => s.sessionStatus);
  const currentRiskScore = useRiskStore((s) => s.riskScore);
  const currentRiskState = useRiskStore((s) => s.riskState);
  const currentRiskTrend = useRiskStore((s) => s.riskTrend);
  const currentAuthenticity = useRiskStore((s) => s.authenticity);
  const currentIdentity = useRiskStore((s) => s.identity);
  const currentContext = useRiskStore((s) => s.context);
  const currentChallengeState = useRiskStore((s) => s.challengeState);
  const currentChallengeText = useRiskStore((s) => s.challengeText);
  const currentVerificationState = useRiskStore((s) => s.verificationState);
  const currentAudioActive = useRiskStore((s) => s.audioActive);
  const currentSessionId = useRiskStore((s) => s.sessionId);

  const [starting, setStarting] = useState(false);

  useFocusEffect(
    useCallback(() => {
      refreshHome();
      checkRoleStatus();
      loadRecentCalls();
    }, [refreshHome, checkRoleStatus, loadRecentCalls])
  );

  const handleStartMonitoring = useCallback(
    async (mode: "live" | "mock" = "live") => {
      setStarting(true);
      try {
        const session = await createSession();
        if (session) {
          await startSession(session.id);
          navigation.navigate("Call", { sessionId: session.id, mode });
        }
      } catch {
        // createSession handles error surfacing
      } finally {
        setStarting(false);
      }
    },
    [createSession, startSession, navigation]
  );

  // Time-based greeting
  const greeting = useMemo(() => {
    const hour = new Date().getHours();
    if (hour < 12) return "Good Morning";
    if (hour < 17) return "Good Afternoon";
    return "Good Evening";
  }, []);

  const userName = user?.full_name || "Shriyansh";

  // Reconciled metrics
  const startOfTodayMs = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  }, []);

  const screenedToday = useMemo(() => {
    return recentCalls.filter((c) => c.timestamp >= startOfTodayMs);
  }, [recentCalls, startOfTodayMs]);

  const screenedAlertsCount = useMemo(() => {
    return screenedToday.filter(
      (c) =>
        c.riskState === "suspicious" ||
        c.riskState === "high" ||
        c.riskState === "critical"
    ).length;
  }, [screenedToday]);

  const screenedHoldCount = useMemo(() => {
    return screenedToday.filter(
      (c) =>
        c.decision?.toUpperCase() === "HOLD" ||
        c.decision?.toUpperCase() === "REJECT" ||
        c.decision?.toUpperCase() === "SILENCE"
    ).length;
  }, [screenedToday]);

  const totalCallsToday = (overview?.total_calls_today ?? 0) + screenedToday.length;
  const totalAlerts = (overview?.active_alerts ?? 0) + screenedAlertsCount;
  const totalHolds = (overview?.high_critical_calls ?? 0) + screenedHoldCount;

  // Unified recent calls feed
  const feedItems: FeedItem[] = useMemo(() => {
    const items: FeedItem[] = [];

    (overview?.recent ?? []).forEach((inc) => {
      const ms = new Date(inc.created_at).getTime();
      items.push({
        kind: "incident",
        id: inc.id,
        timeMs: isNaN(ms) ? 0 : ms,
        timeIso: inc.created_at,
        sessionId: inc.session_id,
        riskScore: inc.peak_risk_score ?? 0,
        action: inc.action_taken ?? undefined,
        state: asRiskState(inc.peak_risk_state ?? inc.final_state),
      });
    });

    recentCalls.forEach((sc) => {
      items.push({
        kind: "screened",
        id: sc.eventId,
        timeMs: sc.timestamp,
        timeIso: new Date(sc.timestamp).toISOString(),
        callerMasked: sc.callerMasked,
        callerName: sc.callerName,
        decision: sc.decision,
        riskLevel: sc.riskLevel,
        riskState: sc.riskState,
        warningType: sc.warningType,
        explanation: sc.explanation,
        state: asCallRiskState(sc.riskState),
        record: sc,
      });
    });

    items.sort((a, b) => b.timeMs - a.timeMs);
    return items.slice(0, 10);
  }, [overview?.recent, recentCalls]);

  const isSessionActive = sessionStatus === "monitoring";

  return (
    <View
      style={[
        styles.screen,
        { backgroundColor: isDark ? colors.background : colors.background },
      ]}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 16,
            paddingBottom: 24,
          },
        ]}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={refreshHome}
            tintColor={colors.accent}
          />
        }
      >
        {/* ── Top Bar Header (design.md Section 17) ────────────────────────── */}
        <View style={styles.topBar}>
          <DhwaniLogo size="md" showText tagline={false} />
          <View style={styles.topActions}>
            <TouchableOpacity
              onPress={() => navigation.navigate("Incidents")}
              style={[
                styles.iconBtn,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Notifications"
            >
              <Text style={{ fontSize: 16 }}>🔔</Text>
            </TouchableOpacity>

            <TouchableOpacity
              onPress={() => navigation.navigate("Settings")}
              style={[
                styles.iconBtn,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Profile and Settings"
            >
              <Text style={{ fontSize: 16 }}>👤</Text>
            </TouchableOpacity>
          </View>
        </View>

        {/* ── Greeting ─────────────────────────────────────────────────────── */}
        <View style={styles.greetingSection}>
          <Text style={[styles.greetingTitle, { color: colors.textPrimary }]}>
            {greeting + ", " + userName + " 👋"}
          </Text>
          <Text style={[styles.greetingSubtitle, { color: colors.textSecondary }]}>
            Your calls are being protected in real time.
          </Text>
        </View>

        {/* ── Protection Status Card (Section 17.1) ─────────────────────────── */}
        <View
          style={[
            styles.protectionCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.lg,
              shadowColor: colors.cardShadow,
            },
          ]}
        >
          <View style={styles.protectionLeft}>
            <View
              style={[
                styles.shieldBadge,
                {
                  backgroundColor: isRoleHeld ? `${colors.accent}18` : `${colors.warning}18`,
                  borderColor: isRoleHeld ? `${colors.accent}44` : `${colors.warning}44`,
                  borderRadius: radius.md,
                },
              ]}
            >
              <Text style={{ fontSize: 22 }}>{isRoleHeld ? "🛡" : "⚠️"}</Text>
            </View>
            <View style={styles.protectionTextCol}>
              <Text style={[styles.protectionTitle, { color: colors.textPrimary }]}>
                {isRoleHeld ? "Protection Active" : "Protection Disabled"}
              </Text>
              <Text style={[styles.protectionSubtitle, { color: colors.textSecondary }]}>
                {isRoleHeld
                  ? "Monitoring incoming calls"
                  : "Designate as Call Screening app"}
              </Text>
            </View>
          </View>
          <Switch
            value={isRoleHeld}
            onValueChange={() => {
              if (!isRoleHeld) {
                requestRole();
              }
            }}
            trackColor={{ false: colors.border, true: colors.accent }}
            thumbColor={Platform.OS === "android" ? "#FFFFFF" : undefined}
          />
        </View>

        {/* ── Summary Metrics (Section 17.2) ────────────────────────────────── */}
        <View style={styles.summaryRow}>
          <View
            style={[
              styles.metricCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
                shadowColor: colors.cardShadow,
              },
            ]}
          >
            <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>
              Calls Today
            </Text>
            <Text style={[styles.metricValue, { color: colors.textPrimary }]}>
              {totalCallsToday}
            </Text>
          </View>

          <View
            style={[
              styles.metricCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
                shadowColor: colors.cardShadow,
              },
            ]}
          >
            <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>
              Alerts
            </Text>
            <Text
              style={[
                styles.metricValue,
                { color: totalAlerts > 0 ? colors.warning : colors.textPrimary },
              ]}
            >
              {totalAlerts}
            </Text>
          </View>

          <View
            style={[
              styles.metricCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
                shadowColor: colors.cardShadow,
              },
            ]}
          >
            <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>
              Holds
            </Text>
            <Text
              style={[
                styles.metricValue,
                { color: totalHolds > 0 ? colors.danger : colors.textPrimary },
              ]}
            >
              {totalHolds}
            </Text>
          </View>
        </View>

        {/* ── Section: Current Analysis (Section 18) ────────────────────────── */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
            Current Analysis
          </Text>
          {isSessionActive && (
            <TouchableOpacity
              onPress={() =>
                currentSessionId &&
                navigation.navigate("Call", { sessionId: currentSessionId, mode: "live" })
              }
            >
              <Text style={[styles.seeAllLink, { color: colors.accent }]}>
                Open Live View →
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {isSessionActive ? (
          <View
            style={[
              styles.activeAnalysisCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.lg,
                shadowColor: colors.cardShadow,
              },
            ]}
          >
            <View style={styles.analysisHeader}>
              <Text style={[styles.analysisCaller, { color: colors.textPrimary }]}>
                Live Speech Stream
              </Text>
              <Text style={[styles.analysisSubtitle, { color: colors.accent }]}>
                Live Analysis in Progress
              </Text>
            </View>

            <RiskOrb
              score={currentRiskScore}
              state={currentRiskState}
              isActive={true}
              trend={currentRiskTrend}
              size={190}
            />

            {/* Sub-scores Row: Authenticity, Identity, Context */}
            <View style={styles.subScoresRow}>
              <View style={styles.subScoreItem}>
                <Text style={[styles.subScoreLabel, { color: colors.textSecondary }]}>
                  Authenticity
                </Text>
                <Text style={[styles.subScoreValue, { color: colors.textPrimary }]}>
                  {currentAuthenticity ? currentAuthenticity.score : "--"}
                </Text>
              </View>

              <View style={styles.subScoreDivider} />

              <View style={styles.subScoreItem}>
                <Text style={[styles.subScoreLabel, { color: colors.textSecondary }]}>
                  Identity
                </Text>
                <Text style={[styles.subScoreValue, { color: colors.textPrimary }]}>
                  {currentIdentity ? `${currentIdentity.match_score}%` : "--"}
                </Text>
              </View>

              <View style={styles.subScoreDivider} />

              <View style={styles.subScoreItem}>
                <Text style={[styles.subScoreLabel, { color: colors.textSecondary }]}>
                  Context
                </Text>
                <Text style={[styles.subScoreValue, { color: colors.textPrimary }]}>
                  {currentContext ? currentContext.score : "--"}
                </Text>
              </View>
            </View>
          </View>
        ) : (
          <View
            style={[
              styles.idleCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.lg,
                shadowColor: colors.cardShadow,
              },
            ]}
          >
            <Text style={{ fontSize: 32, marginBottom: 8 }}>🎙</Text>
            <Text style={[styles.idleTitle, { color: colors.textPrimary }]}>
              No active call analysis
            </Text>
            <Text style={[styles.idleSubtitle, { color: colors.textSecondary }]}>
              Start a live microphone session or analyze an audio file.
            </Text>

            <View style={styles.idleActionsRow}>
              <TouchableOpacity
                onPress={() => handleStartMonitoring("live")}
                disabled={starting}
                style={[
                  styles.idleBtn,
                  { backgroundColor: colors.accent, borderRadius: radius.md },
                ]}
                accessibilityRole="button"
                accessibilityLabel="Start live microphone analysis"
              >
                <Text style={styles.idleBtnText}>
                  {starting ? "Starting..." : "🎙 Start Live Analysis"}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => navigation.navigate("ManualAnalysis")}
                style={[
                  styles.idleBtnSecondary,
                  {
                    borderColor: colors.border,
                    backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                    borderRadius: radius.md,
                  },
                ]}
                accessibilityRole="button"
                accessibilityLabel="Analyze audio file"
              >
                <Text style={[styles.idleBtnSecondaryText, { color: colors.textPrimary }]}>
                  📁 Analyze File
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* ── Section: Evidence Cards (Section 19) ─────────────────────────── */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
            Security Evidence
          </Text>
          <Text style={[styles.evidenceNote, { color: colors.textMuted }]}>
            Persistent multi-modal telemetry
          </Text>
        </View>

        <AuthenticityPanel authenticity={currentAuthenticity} />
        <IdentityPanel identity={currentIdentity} />
        <ActiveLivenessPanel
          challengeState={currentChallengeState}
          challengeText={currentChallengeText}
          verificationState={currentVerificationState}
          audioActive={currentAudioActive}
        />
        <ConsequencesPanel context={currentContext} />

        {/* ── Section: Recent Calls (Section 20) ───────────────────────────── */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
            Recent Calls
          </Text>
          <TouchableOpacity onPress={() => navigation.navigate("Incidents")}>
            <Text style={[styles.seeAllLink, { color: colors.accent }]}>
              See All
            </Text>
          </TouchableOpacity>
        </View>

        {feedItems.length === 0 ? (
          <View
            style={[
              styles.emptyCallsBox,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
          >
            <Text style={[styles.emptyCallsText, { color: colors.textSecondary }]}>
              No calls yet
            </Text>
          </View>
        ) : (
          feedItems.slice(0, 5).map((item) => {
            if (item.kind === "screened") {
              return (
                <CallRow
                  key={item.id}
                  callerName={item.callerName}
                  callerMasked={item.callerMasked}
                  timestamp={item.timeMs}
                  riskState={item.state}
                  decision={item.decision}
                  category="Incoming SIM Call — Metadata Only"
                  onPress={() =>
                    navigation.navigate("CallSecurityDetails", {
                      callRecord: item.record,
                    })
                  }
                />
              );
            } else {
              return (
                <CallRow
                  key={item.id}
                  callerMasked={`Session ${item.sessionId.slice(0, 8)}`}
                  timestamp={item.timeMs}
                  riskState={item.state}
                  decision={item.action}
                  category="Device Microphone — Live Audio"
                  onPress={() =>
                    navigation.navigate("IncidentDetail", { incidentId: item.id })
                  }
                />
              );
            }
          })
        )}
      </ScrollView>

      {/* ── Section 28: Bottom Navigation ──────────────────────────────────── */}
      <BottomNavigation activeTab="home" />
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  scroll: {
    paddingHorizontal: 18,
  },
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 20,
  },
  topActions: {
    flexDirection: "row",
    gap: 8,
  },
  iconBtn: {
    width: 38,
    height: 38,
    borderWidth: 1,
    borderRadius: 19,
    alignItems: "center",
    justifyContent: "center",
  },
  greetingSection: {
    marginBottom: 18,
  },
  greetingTitle: {
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: -0.4,
    lineHeight: 32,
  },
  greetingSubtitle: {
    fontSize: 14,
    marginTop: 4,
  },
  protectionCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 16,
    borderWidth: 1,
    marginBottom: 16,
    elevation: 2,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
  },
  protectionLeft: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
    marginRight: 12,
  },
  shieldBadge: {
    width: 44,
    height: 44,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 14,
  },
  protectionTextCol: {
    flex: 1,
  },
  protectionTitle: {
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.2,
  },
  protectionSubtitle: {
    fontSize: 12,
    marginTop: 2,
  },
  summaryRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 22,
  },
  metricCard: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 14,
    paddingHorizontal: 12,
    elevation: 1,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
  },
  metricLabel: {
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 0.4,
  },
  metricValue: {
    fontSize: 24,
    fontWeight: "800",
    marginTop: 6,
    letterSpacing: -0.5,
  },
  sectionHeaderRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 8,
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: "700",
    letterSpacing: 0.2,
  },
  seeAllLink: {
    fontSize: 13,
    fontWeight: "600",
  },
  evidenceNote: {
    fontSize: 11,
  },
  activeAnalysisCard: {
    borderWidth: 1,
    padding: 16,
    marginBottom: 16,
    elevation: 2,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  analysisHeader: {
    alignItems: "center",
    marginBottom: 4,
  },
  analysisCaller: {
    fontSize: 15,
    fontWeight: "700",
  },
  analysisSubtitle: {
    fontSize: 12,
    fontWeight: "600",
    marginTop: 2,
  },
  subScoresRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    borderTopWidth: 1,
    borderTopColor: "rgba(128,128,128,0.2)",
    paddingTop: 12,
    marginTop: 8,
  },
  subScoreItem: {
    alignItems: "center",
    flex: 1,
  },
  subScoreDivider: {
    width: 1,
    height: 24,
    backgroundColor: "rgba(128,128,128,0.2)",
  },
  subScoreLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  subScoreValue: {
    fontSize: 16,
    fontWeight: "700",
    marginTop: 2,
  },
  idleCard: {
    borderWidth: 1,
    padding: 22,
    alignItems: "center",
    marginBottom: 16,
    elevation: 1,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
  },
  idleTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  idleSubtitle: {
    fontSize: 12,
    marginTop: 4,
    textAlign: "center",
  },
  idleActionsRow: {
    flexDirection: "row",
    gap: 10,
    marginTop: 16,
    width: "100%",
  },
  idleBtn: {
    flex: 1,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  idleBtnText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  idleBtnSecondary: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  idleBtnSecondaryText: {
    fontSize: 13,
    fontWeight: "600",
  },
  emptyCallsBox: {
    borderWidth: 1,
    padding: 20,
    alignItems: "center",
    marginVertical: 4,
  },
  emptyCallsText: {
    fontSize: 13,
  },
});
