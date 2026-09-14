import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius } from '../utils/theme';

interface Props {
  value: string | number;
  label: string;
  tone?: 'neutral' | 'good' | 'warn' | 'bad';
}

const TONE_COLORS = {
  neutral: colors.textPrimary,
  good: colors.safe,
  warn: colors.suspicious,
  bad: colors.high,
};

/** One tile in the Home screen's today-activity grid. */
export const StatCard: React.FC<Props> = ({ value, label, tone = 'neutral' }) => (
  <View style={styles.card}>
    <Text style={[styles.value, { color: TONE_COLORS[tone] }]}>{value}</Text>
    <Text style={styles.label}>{label}</Text>
  </View>
);

const styles = StyleSheet.create({
  card: {
    flex: 1,
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.md,
    alignItems: 'center',
    gap: 2,
  },
  value: { fontSize: 26, fontWeight: '800', letterSpacing: -0.5 },
  label: {
    fontSize: 10,
    color: colors.textSecondary,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    fontWeight: '600',
  },
});
