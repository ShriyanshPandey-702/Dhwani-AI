import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, RISK_COLORS, RISK_LABELS, radius } from '../utils/theme';
import { RiskState } from '../types';

interface Props {
  state: RiskState;
  size?: 'sm' | 'md' | 'lg';
}

export const RiskStateBadge: React.FC<Props> = ({ state, size = 'md' }) => {
  const color = RISK_COLORS[state] || colors.watch;
  const label = RISK_LABELS[state] || 'Unknown';

  const sizeStyles = {
    sm: { paddingHorizontal: 8, paddingVertical: 3, fontSize: 11 },
    md: { paddingHorizontal: 12, paddingVertical: 5, fontSize: 13 },
    lg: { paddingHorizontal: 16, paddingVertical: 7, fontSize: 15 },
  }[size];

  return (
    <View style={[styles.badge, { borderColor: color, backgroundColor: `${color}22`,
      paddingHorizontal: sizeStyles.paddingHorizontal, paddingVertical: sizeStyles.paddingVertical }]}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.label, { color, fontSize: sizeStyles.fontSize }]}>{label}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.full,
    borderWidth: 1,
    gap: 5,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 999,
  },
  label: {
    fontWeight: '600',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
});
