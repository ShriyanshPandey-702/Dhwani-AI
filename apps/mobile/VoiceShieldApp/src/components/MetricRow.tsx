import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing } from '../utils/theme';

interface Props {
  label: string;
  value: string;
  /** Tints the value; use for anomaly bands and detection states. */
  tone?: 'neutral' | 'good' | 'warn' | 'bad' | 'muted';
  /** Optional 0–1 bar rendered under the row. */
  fraction?: number | null;
}

const TONE_COLORS = {
  neutral: colors.textPrimary,
  good: colors.safe,
  warn: colors.suspicious,
  bad: colors.high,
  muted: colors.textMuted,
};

export const MetricRow: React.FC<Props> = ({ label, value, tone = 'neutral', fraction = null }) => (
  <View style={styles.wrapper}>
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, { color: TONE_COLORS[tone] }]}>{value}</Text>
    </View>
    {fraction !== null && (
      <View style={styles.track}>
        <View
          style={[
            styles.fill,
            {
              width: `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`,
              backgroundColor: TONE_COLORS[tone],
            },
          ]}
        />
      </View>
    )}
  </View>
);

const styles = StyleSheet.create({
  wrapper: { gap: 4 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  label: { fontSize: 13, color: colors.textSecondary, flex: 1 },
  value: { fontSize: 13, fontWeight: '700', letterSpacing: 0.3 },
  track: {
    height: 4,
    backgroundColor: colors.bgElevated,
    borderRadius: 2,
    overflow: 'hidden',
  },
  fill: { height: 4, borderRadius: 2 },
});
