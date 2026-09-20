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
import { IncidentSummary, RiskState } from '../types';
import { useCallScreeningStore } from '../store/callScreeningStore';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const formatTime = (iso: string) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return '--:--';
  }
  const pad = (n: number) => `${n}`.padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

const asRiskState = (value: string | null): RiskState => {
  const allowed: RiskState[] = [
    'insufficient_evidence', 'low', 'suspicious', 'high', 'critical',
  ];
  return allowed.includes(value as RiskState)
    ? (value as RiskState)
    : 'insufficient_evidence';
};

/**
 * Home — Security Overview dashboard.
 *
 * Historical/aggregate counterpart to the live call dashboard. Figures come
 * from GET /incidents/stats/overview; when the backend has no data the screen
 * shows an explicit empty state rather than placeholder numbers.
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
  const activeAlert = useCallScreeningStore(s => s.activeAlert);

  // Refresh on focus, not just on mount: the navigator keeps this screen
  // mounted, so returning from a monitored call must re-pull the aggregates
  // and the new incident.
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

  const recent: IncidentSummary[] = overview?.recent ?? [];

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

        {/* ── Today's activity ─────────────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Today's Activity</Text>
        <View style={styles.statRow}>
          <StatCard value={overview?.total_calls_today ?? 0} label="Calls" />
          <StatCard
            value={overview?.active_alerts ?? 0}
            label="Alerts"
            tone={(overview?.active_alerts ?? 0) > 0 ? 'warn' : 'neutral'}
          />
        </View>
        <View style={styles.statRow}>
          <StatCard
            value={overview?.high_critical_calls ?? 0}
            label="High / Critical"
            tone={(overview?.high_critical_calls ?? 0) > 0 ? 'bad' : 'neutral'}
          />
          <StatCard
            value={overview?.safe_calls ?? 0}
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
          onPress={() => navigation.navigate('Settings')}
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
                {isRoleHeld ? 'Active' : 'Not enabled'}
              </Text>
            </View>
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

        {/* ── Start monitoring ─────────────────────────────────────────────── */}
        <TouchableOpacity
          style={[styles.startBtn, starting && styles.startBtnDisabled]}
          onPress={() => handleStartMonitoring('live')}
          disabled={starting}
          accessibilityLabel="Start monitoring a call with live microphone"
          accessibilityRole="button">
          {starting ? (
            <ActivityIndicator color={colors.white} />
          ) : (
            <Text style={styles.startBtnText}>▶  Start Live Monitoring</Text>
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

        {/* ── Recent monitored calls ───────────────────────────────────────── */}
        <Text style={styles.sectionTitle}>Recent Calls</Text>
        {recent.length === 0 ? (
          <View style={styles.emptyState}>
            <Text style={styles.emptyText}>
              No monitored calls recorded yet. Start monitoring to build your
              security history.
            </Text>
          </View>
        ) : (
          recent.map(incident => {
            const state = asRiskState(incident.peak_risk_state ?? incident.final_state);
            return (
              <TouchableOpacity
                key={incident.id}
                style={styles.callRow}
                onPress={() =>
                  navigation.navigate('IncidentDetail', { incidentId: incident.id })
                }
                accessibilityLabel={`Open incident from ${formatTime(incident.created_at)}`}
                accessibilityRole="button">
                <Text style={styles.callTime}>{formatTime(incident.created_at)}</Text>
                <View style={styles.callBody}>
                  <Text style={styles.callSession}>
                    Session {incident.session_id.slice(0, 8)}…
                  </Text>
                  <Text style={styles.callMeta}>
                    Risk {incident.peak_risk_score ?? 0}
                    {incident.action_taken ? ` · ${incident.action_taken.toUpperCase()}` : ''}
                  </Text>
                </View>
                <RiskStateBadge state={state} size="sm" />
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
  brand: { fontSize: 20, fontWeight: '800', color: colors.textPrimary, letterSpacing: 1.5 },
  subGreeting: { ...typography.small, marginTop: 2 },
  settingsBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: colors.bgElevated,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: colors.border,
  },
  settingsBtnText: { color: colors.textSecondary, fontSize: 13, fontWeight: '600' },
  sectionTitle: {
    ...typography.small,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1.2,
    marginTop: spacing.sm,
  },
  statRow: { flexDirection: 'row', gap: spacing.md },
  avgCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    alignItems: 'center',
    gap: 2,
  },
  avgLabel: {
    fontSize: 10,
    color: colors.textSecondary,
    letterSpacing: 1,
    textTransform: 'uppercase',
    fontWeight: '700',
  },
  avgValue: { fontSize: 34, fontWeight: '800', color: colors.textPrimary },
  avgSub: { fontSize: 11, color: colors.textMuted },
  startBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 15,
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  startBtnDisabled: { opacity: 0.6 },
  startBtnText: { color: colors.white, fontWeight: '700', fontSize: 16 },
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
    marginBottom: spacing.sm,
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
