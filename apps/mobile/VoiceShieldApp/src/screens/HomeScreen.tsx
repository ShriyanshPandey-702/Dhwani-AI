import React, { useCallback, useState, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
} from "react-native";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "../utils/theme";
import { useSessionStore } from "../store/sessionStore";
import { useCallScreeningStore } from "../store/callScreeningStore";
import { useRiskStore } from "../store/riskStore";

import { RootStackParamList } from "../navigation/AppNavigator";
import { RiskState } from "../types";
import { ScreenedCallEvent } from "../types/telecom";

import { DhwaniLogo } from "../components/DhwaniLogo";
import { RiskOrb } from "../components/RiskOrb";
import { CallRow } from "../components/CallRow";
import { BottomNavigation } from "../components/BottomNavigation";
import { AuthenticityPanel } from "../components/AuthenticityPanel";
import { IdentityPanel } from "../components/IdentityPanel";
import { ActiveLivenessPanel } from "../components/ActiveLivenessPanel";
import { ConsequencesPanel } from "../components/ConsequencesPanel";
import { BackgroundWave } from "../components/BackgroundWave";
import {
  BellIcon,
  UserIcon,
  ShieldIcon,
  AlertTriangleIcon,
  MicIcon,
  FolderIcon,
  CodeIcon,
} from "../components/Icons";

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
      riskScore: number | null;
      action?: string;
      state: RiskState;
      callerMasked: string;
      callerName: string | null;
      category: string;
      sourceType: "phone" | "mic" | "file";
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
      riskScore: number | null;
      warningType: string;
      explanation: string;
      category: string;
      state: RiskState;
      record: ScreenedCallEvent;
      sourceType: "phone";
    };

export const HomeScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

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
  const openSettings = useCallScreeningStore((s) => s.openSettings);

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
        // Handled in store
      } finally {
        setStarting(false);
      }
    },
    [createSession, startSession, navigation]
  );

  // Reconciled real-time metrics
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
  const totalHolds = (overview?.hold_calls ?? 0) + screenedHoldCount;

  // Unified real-time feed
  const feedItems: FeedItem[] = useMemo(() => {
    const items: FeedItem[] = [];

    (overview?.recent ?? []).forEach((inc) => {
      const ms = new Date(inc.created_at).getTime();
      const isAudioFile =
        inc.source?.toLowerCase().includes("file") || Boolean(inc.filename);
      const callerTitle = isAudioFile
        ? inc.filename || `Audio File ${inc.id.slice(0, 6)}`
        : inc.caller_name || `Session ${inc.session_id?.slice(0, 8) || inc.id.slice(0, 8)}`;
      const categoryText = isAudioFile
        ? "Forensic Audio File Analysis"
        : inc.caller_number
        ? `${inc.caller_number} · Live Audio Stream`
        : "Device Microphone · Live Audio";

      items.push({
        kind: "incident",
        id: inc.id,
        timeMs: isNaN(ms) ? 0 : ms,
        timeIso: inc.created_at,
        sessionId: inc.session_id,
        callerMasked: callerTitle,
        callerName: isAudioFile ? null : inc.caller_name || null,
        category: categoryText,
        sourceType: isAudioFile ? "file" : "mic",
        riskScore: inc.peak_risk_score !== undefined ? inc.peak_risk_score : null,
        action: inc.action_taken ?? undefined,
        state: asRiskState(inc.peak_risk_state ?? inc.final_state),
      });
    });

    recentCalls.forEach((sc) => {
      const isKnownContact = sc.contactStatus === "IN_CONTACTS";
      items.push({
        kind: "screened",
        id: sc.eventId,
        timeMs: sc.timestamp,
        timeIso: new Date(sc.timestamp).toISOString(),
        callerMasked: sc.callerMasked,
        callerName: sc.callerName || (isKnownContact ? null : "Unknown Caller"),
        decision: sc.decision,
        riskLevel: sc.riskLevel,
        riskState: sc.riskState,
        riskScore: sc.riskScore !== undefined ? sc.riskScore : null,
        warningType: sc.warningType,
        explanation: sc.explanation,
        category: isKnownContact
          ? "Saved Contact · SIM Metadata"
          : "Incoming SIM Call · Metadata Only",
        sourceType: "phone",
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
      <BackgroundWave />

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 16,
            paddingBottom: 24,
          },
        ]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={refreshHome}
            tintColor={colors.accent}
          />
        }
      >
        {/* ── Top Bar Header (design.md Section 11) ────────────────────────── */}
        <View style={styles.topBar}>
          <DhwaniLogo size="md" showText tagline={false} />
          <View style={styles.topActions}>
            <TouchableOpacity
              onPress={() => navigation.navigate("IntegrationHub")}
              style={[
                styles.iconBtn,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Integration Hub & APIs"
            >
              <CodeIcon size={18} color={colors.accent} strokeWidth={2.2} />
            </TouchableOpacity>

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
              <BellIcon size={18} color={colors.textPrimary} />
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
              <UserIcon size={18} color={colors.textPrimary} />
            </TouchableOpacity>
          </View>
        </View>

        {/* ── Status Banner (design.md Section 11) ────────────────────────── */}
        <View style={styles.greetingSection}>
          <Text style={[styles.greetingTitle, { color: colors.textPrimary }]}>
            Dhwani AI Voice Analysis
          </Text>
          <Text style={[styles.greetingSubtitle, { color: colors.textSecondary }]}>
            Your calls are being protected in real time.
          </Text>
        </View>

        {/* ── Protection Status Card (design.md Section 11) ───────────────── */}
        <View
          style={[
            styles.protectionCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: isRoleHeld ? `${colors.accent}44` : colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
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
              {isRoleHeld ? (
                <ShieldIcon size={22} color={colors.accent} />
              ) : (
                <AlertTriangleIcon size={22} color={colors.warning} />
              )}
            </View>
            <View style={styles.protectionTextCol}>
              <Text style={[styles.protectionTitle, { color: colors.textPrimary }]}>
                {isRoleHeld ? "Protection Active" : "Protection Disabled"}
              </Text>
              <Text style={[styles.protectionSubtitle, { color: colors.textSecondary }]}>
                {isRoleHeld
                  ? "Monitoring incoming calls"
                  : "Tap below to enable call screening"}
              </Text>
            </View>
          </View>

          {isRoleHeld ? (
            <TouchableOpacity
              onPress={() => openSettings()}
              style={[
                styles.protectionActionBtn,
                { borderColor: colors.border, backgroundColor: "transparent" },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Manage call screening in system settings"
            >
              <Text style={[styles.protectionActionText, { color: colors.textSecondary }]}>
                Manage
              </Text>
            </TouchableOpacity>
          ) : (
            <TouchableOpacity
              onPress={() => requestRole()}
              style={[
                styles.protectionActionBtn,
                { borderColor: colors.accent, backgroundColor: `${colors.accent}18` },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Enable call screening protection"
            >
              <Text style={[styles.protectionActionText, { color: colors.accent }]}>
                Enable
              </Text>
            </TouchableOpacity>
          )}
        </View>

        {/* ── Summary Metrics (design.md Section 11) ──────────────────────── */}
        <View style={styles.summaryRow}>
          <View
            style={[
              styles.metricCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.lg,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
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
                borderRadius: radius.lg,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
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
                borderRadius: radius.lg,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
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

        {/* ── Section: Current Analysis (design.md Section 11) ────────────── */}
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
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
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
                  {currentAuthenticity ? `${currentAuthenticity.score}%` : "UNAVAILABLE"}
                </Text>
              </View>

              <View style={[styles.subScoreDivider, { backgroundColor: colors.border }]} />

              <View style={styles.subScoreItem}>
                <Text style={[styles.subScoreLabel, { color: colors.textSecondary }]}>
                  Identity
                </Text>
                <Text style={[styles.subScoreValue, { color: colors.textPrimary }]}>
                  {currentIdentity?.enrollment_status === "NOT_ENROLLED"
                    ? "NOT ENROLLED"
                    : currentIdentity?.match_score !== null && currentIdentity?.match_score !== undefined
                    ? `${currentIdentity.match_score}%`
                    : "UNAVAILABLE"}
                </Text>
              </View>

              <View style={[styles.subScoreDivider, { backgroundColor: colors.border }]} />

              <View style={styles.subScoreItem}>
                <Text style={[styles.subScoreLabel, { color: colors.textSecondary }]}>
                  Context
                </Text>
                <Text style={[styles.subScoreValue, { color: colors.textPrimary }]}>
                  {currentContext?.transcript ? `${currentContext.score}` : "NO SPEECH"}
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
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
              },
            ]}
          >
            {/* The shield logo sits naturally directly on the card background with NO green/teal circle */}
            <View style={styles.idleLogoContainer}>
              <DhwaniLogo size={68} showText={false} />
            </View>
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
                <View style={styles.btnContentRow}>
                  <MicIcon size={16} color="#FFFFFF" />
                  <Text style={styles.idleBtnText}>
                    {starting ? "Starting..." : "Start Live Analysis"}
                  </Text>
                </View>
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
                <View style={styles.btnContentRow}>
                  <FolderIcon size={16} color={colors.textPrimary} />
                  <Text style={[styles.idleBtnSecondaryText, { color: colors.textPrimary }]}>
                    Analyze File
                  </Text>
                </View>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* ── Section: Integration Hub Banner ────────────────────────────── */}
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => navigation.navigate("IntegrationHub")}
          style={[
            styles.hubCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
            },
          ]}
          accessibilityRole="button"
          accessibilityLabel="Open Platform and Integration APIs Hub"
        >
          <View style={styles.hubHeader}>
            <View style={[styles.hubIconBox, { backgroundColor: `${colors.accent}18` }]}>
              <CodeIcon size={18} color={colors.accent} strokeWidth={2.2} />
            </View>
            <View style={styles.hubTextCol}>
              <View style={styles.hubTitleRow}>
                <Text style={[styles.hubTitle, { color: colors.textPrimary }]}>
                  Platform & Integration APIs
                </Text>
                <View style={[styles.hubLiveBadge, { backgroundColor: "rgba(16,185,129,0.12)" }]}>
                  <View style={[styles.hubDot, { backgroundColor: "#10B981" }]} />
                  <Text style={[styles.hubLiveText, { color: "#10B981" }]}>READY</Text>
                </View>
              </View>
              <Text style={[styles.hubSubtitle, { color: colors.textSecondary }]}>
                REST · WebSocket · SDK · SIP · Core Banking · Contact Center
              </Text>
            </View>
          </View>
          <View style={[styles.hubDivider, { backgroundColor: colors.border }]} />
          <View style={styles.hubBottomRow}>
            <Text style={[styles.hubActionText, { color: colors.accent }]}>
              Explore APIs & Integration Connectors →
            </Text>
          </View>
        </TouchableOpacity>

        {/* ── Section: Evidence Cards (design.md Section 11 & 22) ─────────── */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
            Security Evidence
          </Text>
          <Text style={[styles.evidenceNote, { color: colors.textMuted }]}>
            Multi-modal telemetry
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

        {/* ── Section: Recent Calls (design.md Section 11 & 12) ───────────── */}
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
                  riskScore={item.riskScore}
                  source={item.sourceType}
                  decision={item.decision}
                  category={item.category}
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
                  callerName={item.callerName}
                  callerMasked={item.callerMasked}
                  timestamp={item.timeMs}
                  riskState={item.state}
                  riskScore={item.riskScore}
                  source={item.sourceType}
                  decision={item.action}
                  category={item.category}
                  onPress={() =>
                    navigation.navigate("IncidentDetail", { incidentId: item.id })
                  }
                />
              );
            }
          })
        )}
      </ScrollView>

      {/* ── Bottom Navigation ──────────────────────────────────────────────── */}
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
    marginBottom: 16,
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
    lineHeight: 19,
  },
  protectionCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    padding: 16,
    borderWidth: 1,
    marginBottom: 16,
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
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
  protectionActionBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    minWidth: 76,
  },
  protectionActionText: {
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  summaryRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 20,
  },
  metricCard: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 14,
    paddingHorizontal: 12,
    elevation: 2,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 5,
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
  evidenceNote: {
    fontSize: 11,
    fontWeight: "500",
  },
  seeAllLink: {
    fontSize: 13,
    fontWeight: "700",
  },
  activeAnalysisCard: {
    borderWidth: 1,
    padding: 16,
    marginBottom: 14,
    alignItems: "center",
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  analysisHeader: {
    alignItems: "center",
    marginBottom: 4,
  },
  analysisCaller: {
    fontSize: 16,
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
    width: "100%",
    paddingTop: 12,
    marginTop: 6,
  },
  subScoreItem: {
    alignItems: "center",
    flex: 1,
  },
  subScoreLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  subScoreValue: {
    fontSize: 13,
    fontWeight: "800",
    marginTop: 3,
  },
  subScoreDivider: {
    width: 1,
    height: 24,
  },
  idleCard: {
    borderWidth: 1,
    padding: 20,
    alignItems: "center",
    marginBottom: 14,
    elevation: 2,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
  },
  idleLogoContainer: {
    alignItems: "center",
    justifyContent: "center",
    marginVertical: 10,
  },
  idleTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  idleSubtitle: {
    fontSize: 13,
    textAlign: "center",
    marginTop: 4,
    marginBottom: 16,
    paddingHorizontal: 10,
  },
  idleActionsRow: {
    flexDirection: "row",
    gap: 10,
    width: "100%",
  },
  btnContentRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  idleBtn: {
    flex: 1,
    paddingVertical: 12,
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
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  idleBtnSecondaryText: {
    fontSize: 13,
    fontWeight: "600",
  },
  emptyCallsBox: {
    borderWidth: 1,
    padding: 24,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14,
  },
  emptyCallsText: {
    fontSize: 13,
  },
  hubCard: {
    borderWidth: 1,
    padding: 14,
    marginBottom: 16,
  },
  hubHeader: {
    flexDirection: "row",
    alignItems: "center",
  },
  hubIconBox: {
    width: 38,
    height: 38,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
  },
  hubTextCol: {
    flex: 1,
  },
  hubTitleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  hubTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  hubLiveBadge: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 10,
    gap: 4,
  },
  hubDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  hubLiveText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.4,
  },
  hubSubtitle: {
    fontSize: 11,
    marginTop: 2,
  },
  hubDivider: {
    height: 1,
    marginVertical: 10,
  },
  hubBottomRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
  },
  hubActionText: {
    fontSize: 11,
    fontWeight: "700",
  },
});
