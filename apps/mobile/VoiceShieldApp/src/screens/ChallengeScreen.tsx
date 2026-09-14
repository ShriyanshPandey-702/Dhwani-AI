import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, ScrollView,
} from 'react-native';
import { useNavigation, useRoute, RouteProp } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors, spacing, radius, typography } from '../utils/theme';
import client from '../services/api/client';
import { ChallengeData } from '../types';
import { RootStackParamList } from '../navigation/AppNavigator';

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, 'Challenge'>;

export const ChallengeScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const { sessionId } = route.params;
  const [challenge, setChallenge] = useState<ChallengeData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [responded, setResponded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchChallenge();
  }, []);

  const fetchChallenge = async () => {
    try {
      const { data } = await client.post<ChallengeData>(`/challenge/${sessionId}`);
      setChallenge(data);
    } catch (e) {
      setError('Could not issue a challenge for this session.');
    } finally {
      setIsLoading(false);
    }
  };

  // The outcome is interactive evidence: it feeds back into the Risk Engine and
  // is pushed to the live dashboard over the WebSocket.
  const submitOutcome = async (outcome: 'passed' | 'failed') => {
    if (!challenge || responded) {
      return;
    }
    setResponded(true);
    try {
      await client.post(`/challenge/${sessionId}/${challenge.id}/result`, { outcome });
    } catch (e) {
      setError('Could not record the challenge outcome.');
    }
    navigation.goBack();
  };

  const typeIcon = { phrase: '🗣', question: '❓', sequence: '🔢' };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.headerSection}>
          <Text style={styles.topLabel}>⚡ ACTIVE CHALLENGE</Text>
          <Text style={styles.title}>Voice Challenge Required</Text>
          <Text style={styles.subtitle}>
            Please respond to verify you are a live human speaker.
            This challenge is a security measure, not a guaranteed proof.
          </Text>
        </View>

        {isLoading ? (
          <ActivityIndicator color={colors.brand} size="large" />
        ) : challenge ? (
          <View style={styles.challengeCard}>
            <Text style={styles.typeIcon}>
              {typeIcon[challenge.challenge_type as keyof typeof typeIcon] || '🎙'}
            </Text>
            <Text style={styles.challengeType}>
              {challenge.challenge_type.toUpperCase()}
            </Text>
            <Text style={styles.challengeText}>{challenge.challenge_text}</Text>
          </View>
        ) : (
          <Text style={styles.errorText}>Failed to load challenge. Please go back and try again.</Text>
        )}

        <View style={styles.accessibilityNote}>
          <Text style={styles.noteIcon}>♿</Text>
          <Text style={styles.noteText}>
            If you have a speech difficulty or are in a noisy environment, use the 'Use Alternative Verification' option below.
          </Text>
        </View>

        {!responded && challenge && (
          <>
            <TouchableOpacity
              style={styles.respondBtn}
              onPress={() => submitOutcome('passed')}
              accessibilityLabel="Caller answered the challenge correctly"
              accessibilityRole="button">
              <Text style={styles.respondBtnText}>✓ Caller Answered Correctly</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.failBtn}
              onPress={() => submitOutcome('failed')}
              accessibilityLabel="Caller failed the challenge"
              accessibilityRole="button">
              <Text style={styles.failBtnText}>✗ Caller Failed the Challenge</Text>
            </TouchableOpacity>
          </>
        )}

        {!!error && <Text style={styles.errorText}>{error}</Text>}

        <TouchableOpacity
          style={styles.altBtn}
          onPress={() => navigation.navigate('Verification', { sessionId })}
          accessibilityLabel="Use alternative verification"
          accessibilityRole="button">
          <Text style={styles.altBtnText}>Use Alternative Verification</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.lg },
  headerSection: { gap: spacing.sm },
  topLabel: { fontSize: 11, fontWeight: '700', color: colors.suspicious, letterSpacing: 2 },
  title: { ...typography.h2 },
  subtitle: { color: colors.textSecondary, fontSize: 14, lineHeight: 20 },
  challengeCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.md,
    borderWidth: 1.5,
    borderColor: colors.suspicious,
  },
  typeIcon: { fontSize: 48 },
  challengeType: { fontSize: 11, fontWeight: '700', color: colors.suspicious, letterSpacing: 2 },
  challengeText: {
    fontSize: 20,
    fontWeight: '700',
    color: colors.textPrimary,
    textAlign: 'center',
    lineHeight: 28,
  },
  accessibilityNote: {
    flexDirection: 'row',
    gap: spacing.sm,
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  noteIcon: { fontSize: 18 },
  noteText: { flex: 1, color: colors.textSecondary, fontSize: 13, lineHeight: 18 },
  respondBtn: {
    backgroundColor: colors.success,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
  },
  respondBtnText: { color: colors.white, fontWeight: '700', fontSize: 15 },
  failBtn: {
    backgroundColor: `${colors.error}18`,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1, borderColor: `${colors.error}44`,
  },
  failBtnText: { color: colors.error, fontWeight: '700', fontSize: 15 },
  altBtn: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1, borderColor: colors.border,
  },
  altBtnText: { color: colors.textSecondary, fontWeight: '600', fontSize: 14 },
  errorText: { color: colors.error, textAlign: 'center' },
});
