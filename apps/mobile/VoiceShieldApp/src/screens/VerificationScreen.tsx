import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView, Animated,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { colors, spacing, radius, typography } from '../utils/theme';
import client from '../services/api/client';
import { VerificationData } from '../types';
import { RootStackParamList } from '../navigation/AppNavigator';

type Route = RouteProp<RootStackParamList, 'Verification'>;

export const VerificationScreen: React.FC = () => {
  const navigation = useNavigation();
  const route = useRoute<Route>();
  const { sessionId } = route.params;
  const [verification, setVerification] = useState<VerificationData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [result, setResult] = useState<'approved' | 'rejected' | null>(null);
  const countdown = useRef(120);
  const [timeLeft, setTimeLeft] = useState(120);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    requestVerification();
  }, []);

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.05, duration: 800, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
      ])
    ).start();

    const timer = setInterval(() => {
      countdown.current -= 1;
      setTimeLeft(countdown.current);
      if (countdown.current <= 0) {
        clearInterval(timer);
        setResult('rejected');
      }
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const requestVerification = async () => {
    try {
      const { data } = await client.post<VerificationData>(`/verification/${sessionId}/request`);
      setVerification(data);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  const resolve = async (action: 'approve' | 'reject') => {
    if (!verification) return;
    setResolving(true);
    try {
      await client.post(`/verification/${sessionId}/${action}`, { nonce: verification.nonce });
      setResult(action === 'approve' ? 'approved' : 'rejected');
    } catch (e) {
      console.error(e);
    } finally {
      setResolving(false);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.topLabel}>🔐 INDEPENDENT TRUST CHANNEL</Text>
        <Text style={styles.title}>Verification Required</Text>
        <Text style={styles.subtitle}>
          This action requires approval from your trusted device — separate from the
          suspected call channel.
        </Text>

        {isLoading ? (
          <ActivityIndicator color={colors.brand} size="large" />
        ) : result ? (
          <View style={[styles.resultCard, { borderColor: result === 'approved' ? colors.safe : colors.error }]}>
            <Text style={styles.resultIcon}>{result === 'approved' ? '✅' : '❌'}</Text>
            <Text style={[styles.resultText, { color: result === 'approved' ? colors.safe : colors.error }]}>
              {result === 'approved' ? 'Verification Approved' : 'Verification Rejected / Timed Out'}
            </Text>
            <TouchableOpacity style={styles.doneBtn} onPress={() => navigation.goBack()}>
              <Text style={styles.doneBtnText}>Return to Call</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {/* Timer */}
            <View style={styles.timerSection}>
              <Animated.View style={[styles.timerRing, { transform: [{ scale: pulseAnim }],
                borderColor: timeLeft < 30 ? colors.error : colors.brand }]}>
                <Text style={[styles.timerText, { color: timeLeft < 30 ? colors.error : colors.textPrimary }]}>
                  {timeLeft}s
                </Text>
                <Text style={styles.timerLabel}>remaining</Text>
              </Animated.View>
            </View>

            {/* Nonce */}
            {verification && (
              <View style={styles.nonceBox}>
                <Text style={styles.nonceLabel}>Verification Nonce (show on trusted device)</Text>
                <Text style={styles.nonceValue} numberOfLines={2} selectable>
                  {verification.nonce}
                </Text>
              </View>
            )}

            {/* Action Buttons */}
            <TouchableOpacity
              style={styles.approveBtn}
              onPress={() => resolve('approve')}
              disabled={resolving}
              accessibilityLabel="Approve verification"
              accessibilityRole="button">
              {resolving ? <ActivityIndicator color={colors.white} /> :
                <Text style={styles.approveBtnText}>✓ Approve on This Device</Text>}
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.rejectBtn}
              onPress={() => resolve('reject')}
              disabled={resolving}
              accessibilityLabel="Reject verification"
              accessibilityRole="button">
              <Text style={styles.rejectBtnText}>✗ Reject — Block Action</Text>
            </TouchableOpacity>
          </>
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.lg },
  topLabel: { fontSize: 11, fontWeight: '700', color: colors.brand, letterSpacing: 2 },
  title: { ...typography.h2 },
  subtitle: { color: colors.textSecondary, fontSize: 14, lineHeight: 20 },
  timerSection: { alignItems: 'center', paddingVertical: spacing.md },
  timerRing: {
    width: 120, height: 120, borderRadius: 60,
    borderWidth: 3,
    alignItems: 'center', justifyContent: 'center',
    backgroundColor: colors.bgCard,
  },
  timerText: { fontSize: 32, fontWeight: '800' },
  timerLabel: { fontSize: 11, color: colors.textMuted, marginTop: -4 },
  nonceBox: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 6,
    borderWidth: 1, borderColor: colors.border,
  },
  nonceLabel: { fontSize: 11, color: colors.textMuted, fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1 },
  nonceValue: { ...typography.mono, fontSize: 13 },
  approveBtn: {
    backgroundColor: colors.safe,
    borderRadius: radius.md,
    paddingVertical: 14, alignItems: 'center',
  },
  approveBtnText: { color: colors.white, fontWeight: '700', fontSize: 15 },
  rejectBtn: {
    backgroundColor: `${colors.error}18`,
    borderRadius: radius.md,
    paddingVertical: 14, alignItems: 'center',
    borderWidth: 1, borderColor: `${colors.error}44`,
  },
  rejectBtnText: { color: colors.error, fontWeight: '700', fontSize: 15 },
  resultCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.md,
    borderWidth: 1.5,
  },
  resultIcon: { fontSize: 52 },
  resultText: { fontSize: 18, fontWeight: '700', textAlign: 'center' },
  doneBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 12, paddingHorizontal: 24,
    marginTop: spacing.sm,
  },
  doneBtnText: { color: colors.white, fontWeight: '700', fontSize: 14 },
});
