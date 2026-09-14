import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius } from '../utils/theme';

interface Props {
  severity: 'info' | 'warning' | 'error' | 'critical';
  title: string;
  message: string;
  recommendedAction?: string;
}

const SEVERITY_CONFIG = {
  info:     { icon: 'ℹ', color: colors.info,      bg: `${colors.info}18` },
  warning:  { icon: '⚠', color: colors.warning,   bg: `${colors.warning}18` },
  error:    { icon: '🚨', color: colors.high,      bg: `${colors.high}18` },
  critical: { icon: '🔴', color: colors.critical,  bg: `${colors.critical}20` },
};

export const AlertCard: React.FC<Props> = ({ severity, title, message, recommendedAction }) => {
  const cfg = SEVERITY_CONFIG[severity];
  return (
    <View style={[styles.card, { backgroundColor: cfg.bg, borderColor: cfg.color }]}>
      <View style={styles.header}>
        <Text style={styles.icon}>{cfg.icon}</Text>
        <Text style={[styles.title, { color: cfg.color }]}>{title}</Text>
      </View>
      <Text style={styles.message}>{message}</Text>
      {recommendedAction && (
        <View style={[styles.actionRow, { borderColor: `${cfg.color}44` }]}>
          <Text style={[styles.actionLabel, { color: cfg.color }]}>
            Recommended: {recommendedAction.toUpperCase()}
          </Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  icon: { fontSize: 18 },
  title: {
    fontSize: 15,
    fontWeight: '700',
    flex: 1,
  },
  message: {
    fontSize: 14,
    color: colors.textSecondary,
    lineHeight: 20,
  },
  actionRow: {
    borderTopWidth: 1,
    paddingTop: spacing.sm,
    marginTop: spacing.xs,
  },
  actionLabel: {
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
});
