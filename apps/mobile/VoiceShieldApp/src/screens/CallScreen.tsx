import React, { useCallback, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';

import { colors, spacing, radius } from '../utils/theme';
import { useRiskStore } from '../store/riskStore';
import { useSessionStore } from '../store/sessionStore';
import { useRiskStream } from '../hooks/useRiskStream';
import { useAudioCapture } from '../hooks/useAudioCapture';
import { wsService } from '../services/websocket/wsService';

import { RiskGauge } from '../components/RiskGauge';
import { RiskSparkline } from '../components/RiskSparkline';
import { AuthenticityPanel } from '../components/AuthenticityPanel';
import { IdentityPanel } from '../components/IdentityPanel';
import { ContextPanel } from '../components/ContextPanel';
import { EventTimeline } from '../components/EventTimeline';
import { DecisionPanel } from '../components/DecisionPanel';
import { AlertCard } from '../components/AlertCard';
import { PipelineModeBanner } from '../components/PipelineModeBanner';
import { RootStackParamList } from '../navigation/AppNavigator';
import { SessionStatus } from '../types';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, 'Call'>;

const STATUS_TEXT: Record<SessionStatus, string> = {
  idle: 'IDLE',
  connecting: 'CONNECTING',
  monitoring: 'CALL MONITORED',
  reconnecting: 'RECONNECTING',
  ended: 'SESSION ENDED',
  error: 'CONNECTION FAILED',
};

const STATUS_COLOR: Record<SessionStatus, string> = {
  idle: colors.textMuted,
  connecting: colors.info,
  monitoring: colors.safe,
  reconnecting: colors.suspicious,
  ended: colors.textMuted,
  error: colors.error,
};

const SEVERITY_TO_CARD = {
  suspicious: 'warning',
  high: 'error',
  critical: 'critical',
} as const;

/**
 * Live Security Dashboard.
 *
 * Every value on this screen originates from a backend WebSocket event and is
 * read from the Zustand store. Nothing here polls, and nothing here computes a
 * risk figure of its own — the backend is authoritative.
 */
export const CallScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { sessionId, mode = 'mock' } = route.params;

  const stopSession = useSessionStore(s => s.stopSession);

  const riskScore = useRiskStore(s => s.riskScore);
  const riskState = useRiskStore(s => s.riskState);
  const riskTrend = useRiskStore(s => s.riskTrend);
  const riskHistory = useRiskStore(s => s.riskHistory);
  const evidenceConfidence = useRiskStore(s => s.evidenceConfidence);
  const authenticity = useRiskStore(s => s.authenticity);
  const identity = useRiskStore(s => s.identity);
  const context = useRiskStore(s => s.context);
  const audioQuality = useRiskStore(s => s.audioQuality);
  const audioActive = useRiskStore(s => s.audioActive);
  const decision = useRiskStore(s => s.decision);
  const decisionReasons = useRiskStore(s => s.decisionReasons);
  const recommendedAction = useRiskStore(s => s.recommendedAction);
  const detectedEvents = useRiskStore(s => s.detectedEvents);
  const alerts = useRiskStore(s => s.alerts);
  const challengeState = useRiskStore(s => s.challengeState);
  const verificationState = useRiskStore(s => s.verificationState);
  const sessionStatus = useRiskStore(s => s.sessionStatus);
  const pipelineMode = useRiskStore(s => s.pipelineMode);
  const lastError = useRiskStore(s => s.lastError);
  const dismissAlert = useRiskStore(s => s.dismissAlert);
  const reset = useRiskStore(s => s.reset);

  // Audio capture hook for live microphone mode
  const {
    isRecording: isMicRecording,
    permissionStatus: micPermission,
    error: micError,
    metrics: micMetrics,
    requestPermission: requestMicPermission,
    start: startMicCapture,
    stop: stopMicCapture,
  } = useAudioCapture(false);

  // Subscribe the store to the socket before the socket opens.
  useRiskStream(sessionId);

  useEffect(() => {
    let cancelled = false;

    // Clear any previous call's dashboard before this one starts.
    reset();

    wsService
      .connect(sessionId)
      .then(() => {
        // `connect` resolves only once the socket is OPEN, so this send cannot
        // be dropped. Kicks off the mock scenario in mock mode; in live mode,
        // audio chunks streamed from device/scripts drive the real pipeline.
        if (!cancelled && mode === 'mock') {
          wsService.startDemo();
        } else if (!cancelled && mode === 'live') {
          startMicCapture();
        }
      })
      .catch(() => {
        // The store's session status already reflects the failure.
      });

    return () => {
      cancelled = true;
      if (mode === 'live') {
        stopMicCapture();
      }
      wsService.disconnect();
      reset();
    };
  }, [sessionId, mode, reset, startMicCapture, stopMicCapture]);

  const handleEndSession = useCallback(() => {
    Alert.alert('End Session', 'Stop monitoring this call?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'End Session',
        style: 'destructive',
        onPress: async () => {
          if (mode === 'live') {
            await stopMicCapture();
          }
          wsService.disconnect();
          try {
            await stopSession(sessionId);
          } catch {
            // The session may already have ended server-side.
          }
          if (navigation.canGoBack()) {
            navigation.goBack();
          } else {
            navigation.navigate('Home');
          }
        },
      },
    ]);
  }, [sessionId, mode, stopMicCapture, stopSession, navigation]);

  const statusColor = STATUS_COLOR[sessionStatus];
  const latestAlert = alerts[0];

  return (
    <View style={styles.container}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          <View>
            <Text style={styles.brand}>VOICESHIELD</Text>
            <Text style={[styles.statusText, { color: statusColor }]}>
              {STATUS_TEXT[sessionStatus]}
            </Text>
          </View>
        </View>
        <TouchableOpacity
          onPress={handleEndSession}
          style={styles.endBtn}
          accessibilityLabel="End monitoring session"
          accessibilityRole="button">
          <Text style={styles.endBtnText}>End Session</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        <PipelineModeBanner mode={pipelineMode} />

        {mode === 'live' && (
          <View style={styles.liveMicCard}>
            <View style={styles.liveMicHeader}>
              <View
                style={[
                  styles.micDot,
                  { backgroundColor: isMicRecording ? colors.safe : colors.textMuted },
                ]}
              />
              <Text style={styles.liveMicTitle}>
                {isMicRecording ? 'LIVE MICROPHONE ACTIVE' : 'MICROPHONE STANDBY'}
              </Text>
            </View>
            <Text style={styles.liveMicSubtitle}>
              {isMicRecording
                ? `Streaming 16 kHz PCM · Chunks: ${micMetrics.chunksSent}${
                    micMetrics.chunksDropped > 0 ? ` (${micMetrics.chunksDropped} dropped)` : ''
                  }`
                : micPermission === 'denied' || micPermission === 'blocked'
                ? 'Microphone permission required to monitor speech.'
                : 'Connecting to device microphone…'}
            </Text>
            {(micPermission === 'denied' || micPermission === 'blocked') && (
              <TouchableOpacity
                style={styles.permBtn}
                onPress={requestMicPermission}
                accessibilityLabel="Grant microphone permission"
                accessibilityRole="button">
                <Text style={styles.permBtnText}>Grant Microphone Permission</Text>
              </TouchableOpacity>
            )}
            {micError && <Text style={styles.micErrorText}>⚠️ {micError}</Text>}
          </View>
        )}

        {sessionStatus === 'reconnecting' && (
          <View style={styles.notice}>
            <Text style={styles.noticeText}>
              Connection lost — reconnecting. The risk picture below may be stale.
            </Text>
          </View>
        )}

        {/* ── Overall security ─────────────────────────────────────────────── */}
        <RiskGauge score={riskScore} state={riskState} trend={riskTrend} size={200} />

        {/* ── Live risk graph ──────────────────────────────────────────────── */}
        <RiskSparkline history={riskHistory} />

        {/* ── Security decision ────────────────────────────────────────────── */}
        <DecisionPanel
          decision={decision}
          reasons={decisionReasons}
          recommendedAction={recommendedAction}
          evidenceConfidence={evidenceConfidence}
        />

        {/* ── Challenge / independent verification ─────────────────────────── */}
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.challengeBtn]}
            onPress={() => navigation.navigate('Challenge', { sessionId })}
            accessibilityLabel="Challenge the caller"
            accessibilityRole="button">
            <Text style={styles.actionText}>Challenge Caller</Text>
            {challengeState !== 'idle' && (
              <Text style={styles.actionState}>{challengeState.toUpperCase()}</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, styles.verifyBtn]}
            onPress={() => navigation.navigate('Verification', { sessionId })}
            accessibilityLabel="Start independent verification"
            accessibilityRole="button">
            <Text style={styles.actionText}>Independent Verification</Text>
            {verificationState !== 'idle' && (
              <Text style={styles.actionState}>{verificationState.toUpperCase()}</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* ── Active alert ─────────────────────────────────────────────────── */}
        {latestAlert && (
          <View>
            <AlertCard
              severity={SEVERITY_TO_CARD[latestAlert.severity] ?? 'warning'}
              title="Security Alert"
              message={latestAlert.message}
              recommendedAction={latestAlert.recommendedAction}
            />
            <TouchableOpacity
              onPress={() => dismissAlert(latestAlert.id)}
              accessibilityLabel="Dismiss alert"
              accessibilityRole="button">
              <Text style={styles.dismiss}>Dismiss</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* ── Independent evidence streams ─────────────────────────────────── */}
        <AuthenticityPanel authenticity={authenticity} />
        <IdentityPanel identity={identity} />
        <ContextPanel context={context} />

        {/* ── Live event timeline ──────────────────────────────────────────── */}
        <EventTimeline events={detectedEvents} />

        {/* ── Channel quality ──────────────────────────────────────────────── */}
        <View style={styles.audioRow}>
          <Text style={styles.audioLabel}>
            Audio {audioActive ? 'active' : 'idle'}
          </Text>
          <Text style={styles.audioValue}>
            {audioQuality
              ? `${audioQuality.quality} · SNR ${audioQuality.estimated_snr_db} dB`
              : 'no signal yet'}
          </Text>
        </View>

        {!!lastError && <Text style={styles.error}>{lastError}</Text>}

        <Text style={styles.sessionNote}>Session {sessionId.slice(0, 8)}…</Text>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    paddingTop: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  brand: { fontSize: 13, fontWeight: '800', color: colors.textPrimary, letterSpacing: 1.5 },
  statusText: { fontSize: 10, fontWeight: '700', letterSpacing: 1.2, marginTop: 1 },
  endBtn: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    backgroundColor: `${colors.error}22`,
    borderRadius: radius.full,
    borderWidth: 1,
    borderColor: `${colors.error}44`,
  },
  endBtnText: { color: colors.error, fontWeight: '700', fontSize: 13 },
  scroll: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  notice: {
    backgroundColor: `${colors.suspicious}18`,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: `${colors.suspicious}44`,
    padding: spacing.sm,
  },
  noticeText: { color: colors.suspicious, fontSize: 12 },
  actions: { flexDirection: 'row', gap: spacing.md },
  actionBtn: {
    flex: 1,
    borderRadius: radius.md,
    paddingVertical: 14,
    paddingHorizontal: 10,
    alignItems: 'center',
    gap: 2,
  },
  challengeBtn: { backgroundColor: colors.brand },
  verifyBtn: { backgroundColor: colors.high },
  actionText: {
    color: colors.white,
    fontWeight: '700',
    fontSize: 13,
    textAlign: 'center',
  },
  actionState: {
    color: colors.white,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1,
    opacity: 0.85,
  },
  dismiss: {
    color: colors.textMuted,
    fontSize: 12,
    textAlign: 'center',
    paddingVertical: spacing.sm,
  },
  audioRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: colors.bgCard,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  audioLabel: { fontSize: 12, color: colors.textSecondary },
  audioValue: { fontSize: 12, color: colors.textMuted, fontWeight: '600' },
  error: { color: colors.error, fontSize: 12, textAlign: 'center' },
  sessionNote: { textAlign: 'center', fontSize: 11, color: colors.textMuted },
  liveMicCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.xs,
  },
  liveMicHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  micDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  liveMicTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.textPrimary,
    letterSpacing: 1,
  },
  liveMicSubtitle: {
    fontSize: 11,
    color: colors.textSecondary,
  },
  permBtn: {
    marginTop: spacing.xs,
    paddingVertical: 8,
    paddingHorizontal: 12,
    backgroundColor: colors.brand,
    borderRadius: radius.sm,
    alignItems: 'center',
  },
  permBtnText: {
    color: colors.white,
    fontSize: 12,
    fontWeight: '700',
  },
  micErrorText: {
    color: colors.error,
    fontSize: 11,
    marginTop: spacing.xs,
  },
});
