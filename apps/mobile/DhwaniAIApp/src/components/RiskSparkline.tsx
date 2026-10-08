import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, RISK_COLORS, spacing, radius } from '../utils/theme';
import { RiskObservation } from '../types';

interface Props {
  history: RiskObservation[];
  /** Threshold guide lines drawn across the plot, e.g. {high: 65}. */
  thresholds?: { suspicious: number; high: number; critical: number };
  height?: number;
  /** How many of the most recent observations to draw. */
  window?: number;
}

const DEFAULT_THRESHOLDS = { suspicious: 40, high: 65, critical: 85 };

/**
 * Live risk time-series.
 *
 * Every column is one risk observation received over the WebSocket, coloured by
 * the risk state the backend assigned it. No values are generated locally: an
 * empty history renders an empty-state message rather than a fake curve.
 *
 * Drawn with plain Views so the dashboard carries no charting dependency.
 */
export const RiskSparkline: React.FC<Props> = ({
  history,
  thresholds = DEFAULT_THRESHOLDS,
  height = 120,
  window = 60,
}) => {
  const points = history.slice(-window);
  const latest = points.length ? points[points.length - 1] : null;

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>LIVE RISK GRAPH</Text>
        <Text style={styles.count}>
          {points.length > 0 ? `${points.length} obs` : 'awaiting data'}
        </Text>
      </View>

      <View style={[styles.plot, { height }]}>
        {/* Threshold guides */}
        {(['critical', 'high', 'suspicious'] as const).map(key => (
          <View
            key={key}
            style={[
              styles.guide,
              {
                bottom: (thresholds[key] / 100) * height,
                borderColor: `${RISK_COLORS[key]}55`,
              },
            ]}>
            <Text style={[styles.guideLabel, { color: `${RISK_COLORS[key]}AA` }]}>
              {thresholds[key]}
            </Text>
          </View>
        ))}

        {points.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>
              Waiting for the first risk observation…
            </Text>
          </View>
        ) : (
          <View style={styles.bars}>
            {points.map((point, index) => (
              <View
                key={`${point.at}-${index}`}
                style={[
                  styles.bar,
                  {
                    height: Math.max(2, (Math.min(100, Math.max(0, point.score)) / 100) * height),
                    backgroundColor: RISK_COLORS[point.state] || colors.watch,
                    opacity: index === points.length - 1 ? 1 : 0.75,
                  },
                ]}
              />
            ))}
          </View>
        )}
      </View>

      <View style={styles.axis}>
        <Text style={styles.axisLabel}>older</Text>
        <Text style={styles.axisLabel}>
          {latest ? `now · ${latest.score}` : 'now'}
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.textSecondary,
    letterSpacing: 1.2,
  },
  count: { fontSize: 11, color: colors.textMuted },
  plot: {
    position: 'relative',
    backgroundColor: colors.bg,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  guide: {
    position: 'absolute',
    left: 0,
    right: 0,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderStyle: 'dashed',
  },
  guideLabel: { fontSize: 9, marginLeft: 4, marginTop: -10 },
  bars: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 1,
    paddingHorizontal: 2,
  },
  bar: { flex: 1, minWidth: 2, borderTopLeftRadius: 2, borderTopRightRadius: 2 },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyText: { color: colors.textMuted, fontSize: 12, fontStyle: 'italic' },
  axis: { flexDirection: 'row', justifyContent: 'space-between' },
  axisLabel: { fontSize: 10, color: colors.textMuted },
});
