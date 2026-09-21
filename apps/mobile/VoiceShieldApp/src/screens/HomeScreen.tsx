import React, { useCallback, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useFocusEffect, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { colors, spacing, radius, typography } from '../utils/theme';
import { useSessionStore } from '../store/sessionStore';
import { StatCard } from '../components/StatCard';
import { RiskStateBadge } from '../components/RiskStateBadge';
import { RootStackParamList } from '../navigation/AppNavigator';
import { RiskState } from '../types';
import { useCallScreeningStore } from '../store/callScreeningStore';
import { ScreenedCallEvent } from '../types/telecom';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const formatTime = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return '--:--';
  }
  const pad = (n: number) => `${n}`.padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/**
 * Maps a native riskState string to the RiskState union used by RiskStateBadge.
 * Falls back to 'insufficient_evidence' for unknown values.
 */
const asCallRiskState = (riskState: string | undefined | null): RiskState => {
  switch (riskState) {
    case 'safe':   return 'low';
    case 'low':    return 'low';
    case 'suspicious': return 'suspicious';
    case 'high':   return 'high';
    case 'critical': return 'critical';
    default:       return 'insufficient_evidence';
  }
};

const asRiskState = (value: string | null): RiskState => {
  const allowed: RiskState[] = [
    'insufficient_evidence', 'low', 'suspicious', 'high', 'critical',
  ];
  return allowed.includes(value as RiskState)
    ? (value as RiskState)
    : 'insufficient_evidence';
};

type FeedItem =
  | {
      kind: 'incident';
      id: string;
      timeMs: number;
      timeIso: string;
      sessionId: string;
      riskScore: number;
      action?: string;
      state: RiskState;
    }
  | {
      kind: 'screened';
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

/**
 * Home — Security Overview dashboard.
 *
 * Provides a unified, idempotent security overview:
 * 1. Automatic SIM Call Screening (independent Android Telecom path).
 * 2. On-Demand Live Audio Analysis (microphone path).
 */
export const HomeScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const overview = useSessionStore(s => s.overview);
  const isRefreshing = useSessionStore(s => s.isRefreshing);
  const refreshHome = useSessionStore(s => s.refreshHome);
  const createSession = useSessionStore(s => s.createSession);
  const startSession = useSessionStore(s => s.startSession);
  const [starting, setStarting] = useState(false);
  const insets = useSafeAreaInsets();

  const isRoleHeld = useCallScreeningStore(s => s.isRoleHeld);
  const checkRoleStatus = useCallScreeningStore(s => s.checkRoleStatus);
  const loadRecentCalls = useCallScreeningStore(s => s.loadRecentCalls);
  const recentCalls = useCallScreeningStore(s => s.recentCalls);
  const activeAlert = useCallScreeningStore(s => s.activeAlert);
  const requestRole = useCallScreeningStore(s => s.requestRole);

  useFocusEffect(
    useCallback(() => {
      refreshHome();
      checkRoleStatus();
      loadRecentCalls();
    }, [refreshHome, checkRoleStatus, loadRecentCalls]),
  );

  const handleStartMonitoring = useCallback(
    async (mode: 'live' | 'mock' = 'live') => {
      setStarting(true);
      try {
        const session = await createSession();
        if (session) {
          await startSession(session.id);
          navigation.navigate('Call', { sessionId: session.id, mode });
        }
      } catch {
        // createSession surfaces the error through the store.
      } finally {
        setStarting(false);
      }
    },
    [createSession, startSession, navigation],
  );

  // Idempotent reconciliation:
  // 1 SIM call = 1 screened record in native storage; 1 live session = 1 backend session
  const startOfTodayMs = React.useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  }, []);

  const screenedToday = React.useMemo(() => {
    return recentCalls.filter(c => c.timestamp >= startOfTodayMs);
  }, [recentCalls, startOfTodayMs]);

  const screenedSafeCount = React.useMemo(() => {
    return screenedToday.filter(c => c.riskState === 'safe' || c.riskState === 'low').length;
  }, [screenedToday]);

  const screenedAlertsCount = React.useMemo(() => {
    return screenedToday.filter(c => c.riskState === 'suspicious' || c.riskState === 'high' || c.riskState === 'critical').length;
  }, [screenedToday]);

  const screenedHighCount = React.useMemo(() => {
    return screenedToday.filter(c => c.riskState === 'high' || c.riskState === 'critical').length;
  }, [screenedToday]);

  const totalCalls = (overview?.total_calls_today ?? 0) + screenedToday.length;
  const totalAlerts = (overview?.active_alerts ?? 0) + screenedAlertsCount;
  const totalHighCritical = (overview?.high_critical_calls ?? 0) + screenedHighCount;
  const totalSafe = (overview?.safe_calls ?? 0) + screenedSafeCount;

  // Unified recent activity feed combining screened SIM calls and live audio sessions
  const feedItems: FeedItem[] = React.useMemo(() => {
    const items: FeedItem[] = [];

    (overview?.recent ?? []).forEach(inc => {
      const ms = new Date(inc.created_at).getTime();
      items.push({
        kind: 'incident',
        id: inc.id,
        timeMs: isNaN(ms) ? 0 : ms,
        timeIso: inc.created_at,
        sessionId: inc.session_id,
        riskScore: inc.peak_risk_score ?? 0,
        action: inc.action_taken ?? undefined,
        state: asRiskState(inc.peak_risk_state ?? inc.final_state),
      });
    });

    recentCalls.forEach(sc => {
      items.push({
        kind: 'screened',
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
    return items.slice(0, 25);
  }, [overview?.recent, recentCalls]);

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={[styles.scroll, { paddingTop: insets.top + spacing.md }]}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={refreshHome}
            tintColor={colors.brand}
          />
        }>
        {/* ── Header ───────────────────────────────────────────────────────── */}
        <View style={styles.header}>
          <View>
            <Text style={styles.brand}>VOICESHIELD</Text>
            <Text style={styles.subGreeting}>
              Security Overview · Real-Time Active Protection
            </Text>
          </View>
          <TouchableOpacity
            onPress={() => navigation.navigate('Settings')}
            style={styles.settingsBtn}
            accessibilityLabel="Open settings"
            accessibilityRole="button">
            <Text style={styles.settingsBtnText}>⚙️ Settings</Text>
          </TouchableOpacity>
        </View>

        {/* ── Backend offline banner ────────────────────────────────────────── */}
        {overview === null && (
          <View style={styles.offlineBanner}>
            <Text style={styles.offlineBannerText}>
              ⚡ Backend offline (FastAPI port 8000) · Local call screening active
            </Text>
          </View>
        )}

        {/* ── Today's activity (Reconciled) ─────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Today's Activity</Text>
        <View style={styles.statRow}>
          <StatCard value={totalCalls} label="Calls" />
          <StatCard
            value={totalAlerts}
            label="Alerts"
            tone={totalAlerts > 0 ? 'warn' : 'neutral'}
          />
        </View>
        <View style={styles.statRow}>
          <StatCard
            value={totalHighCritical}
            label="High / Critical"
            tone={totalHighCritical > 0 ? 'bad' : 'neutral'}
          />
          <StatCard
            value={totalSafe}
            label="Safe"
            tone="good"
          />
        </View>

        <View style={styles.avgCard}>
          <Text style={styles.avgLabel}>Average Risk</Text>
          <Text style={styles.avgValue}>{overview?.average_risk ?? 0}</Text>
          <Text style={styles.avgSub}>
            {overview?.suspicious_calls ?? 0} suspicious call
            {(overview?.suspicious_calls ?? 0) === 1 ? '' : 's'} in the last 24h
          </Text>
        </View>

        {/* ── Call Screening Status ─────────────────────────────────────────── */}
        <TouchableOpacity
          style={styles.screeningCard}
          onPress={() => {
            if (!isRoleHeld) {
              requestRole();
            } else {
              navigation.navigate('Settings');
            }
          }}
          accessibilityLabel="Call Screening Status"
          accessibilityRole="button">
          <View style={styles.screeningHeaderRow}>
            <Text style={styles.screeningTitle}>VoiceShield Call Screening</Text>
            <View style={styles.screeningStatusBadge}>
              <Text
                style={[
                  styles.statusDot,
                  isRoleHeld ? styles.screeningStatusDotActive : styles.screeningStatusDotInactive,
                ]}>
                {isRoleHeld ? '●' : '○'}
              </Text>
              <Text
                style={[
                  styles.screeningStatusText,
                  isRoleHeld ? styles.screeningActiveText : styles.screeningInactiveText,
                ]}>
                {isRoleHeld ? 'Active' : 'Inactive'}
              </Text>
            </View>
          </View>
          <View style={styles.screeningActionRow}>
            <Text style={styles.screeningDesc}>
              {isRoleHeld
                ? 'Incoming cellular calls are screened automatically via Android Telecom.'
                : 'Role required to screen incoming cellular calls.'}
            </Text>
            <Text style={styles.screeningActionText}>
              {isRoleHeld ? 'Manage Call Screening →' : 'Enable Call Screening →'}
            </Text>
          </View>
          {activeAlert ? (
            <View style={styles.screeningAlertBox}>
              <Text style={styles.screeningAlertTitle}>⚠️ Recent Security Warning</Text>
              <Text style={styles.screeningAlertDesc}>
                {activeAlert.warningType === 'VERIFICATION_FAILED'
                  ? `Caller verification failed for ${activeAlert.callerMasked}`
                  : activeAlert.warningType === 'UNVERIFIED_CALLER'
                  ? `Unverified caller: ${activeAlert.callerMasked}`
                  : activeAlert.warningType === 'BLOCKLIST_MATCH'
                  ? `Blocked caller: ${activeAlert.callerMasked}`
                  : `Restricted number screened`}
              </Text>
            </View>
          ) : null}
        </TouchableOpacity>

        {/* ── Start Live Audio Analysis ───────────────────────────────────── */}
        <TouchableOpacity
          style={[styles.startBtn, starting && styles.startBtnDisabled]}
          onPress={() => handleStartMonitoring('live')}
          disabled={starting}
          accessibilityLabel="Start live audio analysis with microphone"
          accessibilityRole="button">
          {starting ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <Text style={styles.startBtnText}>▶  Start Live Audio Analysis</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.demoBtn}
          onPress={() => handleStartMonitoring('mock')}
          disabled={starting}
          accessibilityLabel="Run simulated demo scenario"
          accessibilityRole="button">
          <Text style={styles.demoBtnText}>🧪  Run Demo Scenario (Mock Audio)</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.manualBtn}
          onPress={() => navigation.navigate('ManualAnalysis')}
          accessibilityLabel="Analyze pre-recorded audio file"
          accessibilityRole="button">
          <Text style={styles.manualBtnText}>📁  Analyze Audio File (Manual Analysis)</Text>
        </TouchableOpacity>

        {/* ── Recent Activity Feed ────────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Recent Activity</Text>
        {feedItems.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>
              No call screening or live audio sessions recorded yet.
            </Text>
          </View>
        ) : (
          feedItems.map(item => {
            if (item.kind === 'screened') {
              return (
                <TouchableOpacity
                  key={`screened_${item.id}`}
                  style={styles.callRow}
                  onPress={() =>
                    navigation.navigate('CallSecurityDetails', { callRecord: item.record })
                  }
                  accessibilityLabel={`View security details for call from ${item.callerMasked}`}
                  accessibilityRole="button">
                  <Text style={styles.callTime}>{formatTime(item.timeIso)}</Text>
                  <View style={styles.callBody}>
                    <Text style={styles.callSession}>
                      📞 {item.callerName ? item.callerName : 'SIM Call'}: {item.callerMasked}
                    </Text>
                    <Text style={styles.callMeta}>
                      {item.decision} · {item.riskState !== 'safe' && item.riskState !== 'low' ? item.warningType : 'Low risk'}
                    </Text>
                  </View>
                  <RiskStateBadge state={item.state} size="sm" />
                </TouchableOpacity>
              );
            }
            return (
              <TouchableOpacity
                key={`incident_${item.id}`}
                style={styles.callRow}
                onPress={() =>
                  navigation.navigate('IncidentDetail', { incidentId: item.id })
                }
                accessibilityLabel={`Open incident from ${formatTime(item.timeIso)}`}
                accessibilityRole="button">
                <Text style={styles.callTime}>{formatTime(item.timeIso)}</Text>
                <View style={styles.callBody}>
                  <Text style={styles.callSession}>
                    🎙️ Audio Session {item.sessionId.slice(0, 8)}…
                  </Text>
                  <Text style={styles.callMeta}>
                    Risk {item.riskScore}
                    {item.action ? ` · ${item.action.toUpperCase()}` : ''}
                  </Text>
                </View>
                <RiskStateBadge state={item.state} size="sm" />
              </TouchableOpacity>
            );
          })
        )}

        {/* ── Quick actions ────────────────────────────────────────────────── */}
        <View style={styles.quickActions}>
          <TouchableOpacity
            style={styles.quickCard}
            onPress={() => navigation.navigate('Incidents')}
            accessibilityLabel="View incident history"
            accessibilityRole="button">
            <Text style={styles.quickIcon}>📋</Text>
            <Text style={styles.quickLabel}>Incidents</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.quickCard}
            onPress={() => navigation.navigate('Devices')}
            accessibilityLabel="Manage trusted devices"
            accessibilityRole="button">
            <Text style={styles.quickIcon}>📱</Text>
            <Text style={styles.quickLabel}>Devices</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={styles.quickCard}
            onPress={() => navigation.navigate('Settings')}
            accessibilityLabel="Open settings"
            accessibilityRole="button">
            <Text style={styles.quickIcon}>⚙️</Text>
            <Text style={styles.quickLabel}>Settings</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.sm,
  },
  offlineBanner: {
    backgroundColor: `${colors.warning}22`,
    borderColor: `${colors.warning}55`,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  offlineBannerText: {
    fontSize: 12,
    color: colors.warning,
    fontWeight: '600',
    textAlign: 'center',
  },
  brand: {
    ...typography.h3,
    color: colors.brand,
    letterSpacing: 1.5,
  },
  subGreeting: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
  },
  settingsBtn: {
    backgroundColor: colors.bgElevated,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border,
  },
  settingsBtnText: {
    fontSize: 12,
    color: colors.textSecondary,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginTop: spacing.xs,
  },
  statRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  avgCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
  },
  avgLabel: {
    fontSize: 12,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontWeight: '600',
  },
  avgValue: {
    fontSize: 36,
    fontWeight: '800',
    color: colors.textPrimary,
    marginVertical: 2,
  },
  avgSub: {
    fontSize: 12,
    color: colors.textSecondary,
  },
  startBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 16,
    alignItems: 'center',
    shadowColor: colors.brand,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  startBtnDisabled: {
    opacity: 0.6,
  },
  startBtnText: {
    color: colors.white,
    fontSize: 16,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  demoBtn: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    paddingVertical: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  demoBtnText: {
    color: colors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
  },
  manualBtn: {
    backgroundColor: colors.brandDim,
    borderRadius: radius.md,
    paddingVertical: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.brand,
  },
  manualBtnText: {
    color: colors.brand,
    fontSize: 13,
    fontWeight: '700',
  },
  emptyState: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.lg,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyText: { color: colors.textMuted, textAlign: 'center', fontSize: 13, lineHeight: 19 },
  callRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  callTime: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.textSecondary,
    fontVariant: ['tabular-nums'],
  },
  callBody: { flex: 1 },
  callSession: { ...typography.body, fontWeight: '600', fontSize: 14 },
  callMeta: { ...typography.small, fontSize: 12, marginTop: 1 },
  quickActions: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.sm },
  quickCard: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  quickIcon: { fontSize: 24 },
  quickLabel: { ...typography.small, fontWeight: '600', color: colors.textPrimary },
  screeningCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.xs,
  },
  screeningHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  screeningTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary,
  },
  screeningStatusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: {
    fontSize: 12,
  },
  screeningStatusDotActive: {
    color: colors.success,
  },
  screeningStatusDotInactive: {
    color: colors.textMuted,
  },
  screeningStatusText: {
    fontSize: 13,
    fontWeight: '700',
  },
  screeningActiveText: {
    color: colors.success,
  },
  screeningInactiveText: {
    color: colors.textMuted,
  },
  screeningActionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xs,
    paddingTop: spacing.xs,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  screeningDesc: {
    fontSize: 12,
    color: colors.textMuted,
    flex: 1,
  },
  screeningActionText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.brand,
    marginLeft: spacing.sm,
  },
  screeningAlertBox: {
    marginTop: spacing.sm,
    padding: spacing.sm,
    backgroundColor: `${colors.warning}18`,
    borderColor: `${colors.warning}44`,
    borderWidth: 1,
    borderRadius: radius.sm,
  },
  screeningAlertTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.warning,
  },
  screeningAlertDesc: {
    fontSize: 12,
    color: colors.textSecondary,
    marginTop: 2,
  },
});
