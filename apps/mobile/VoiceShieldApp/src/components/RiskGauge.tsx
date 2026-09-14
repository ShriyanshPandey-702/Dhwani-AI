import React, { useEffect, useRef } from 'react';
import { View, Text, Animated, StyleSheet } from 'react-native';
import { colors, RISK_COLORS, RISK_LABELS } from '../utils/theme';
import { RiskState, RiskTrend } from '../types';

interface Props {
  score: number;
  state: RiskState;
  trend?: RiskTrend;
  size?: number;
}

const TREND_GLYPH: Record<RiskTrend, string> = {
  rising: '↑',
  falling: '↓',
  stable: '→',
};

const TREND_LABEL: Record<RiskTrend, string> = {
  rising: 'Risk increasing',
  falling: 'Risk decreasing',
  stable: 'Risk stable',
};

/**
 * Security Risk Index gauge — the headline figure on the live dashboard.
 * The value is whatever the backend last reported; nothing is computed here.
 */
export const RiskGauge: React.FC<Props> = ({ score, state, trend = 'stable', size = 200 }) => {
  const ringColor = RISK_COLORS[state] || colors.watch;
  const label = RISK_LABELS[state] || 'Monitoring';
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(progress, {
      toValue: Math.min(100, Math.max(0, score)),
      duration: 500,
      useNativeDriver: false,
    }).start();
  }, [score, progress]);

  const fillHeight = progress.interpolate({
    inputRange: [0, 100],
    outputRange: [0, size],
    extrapolate: 'clamp',
  });

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      {/* Track + level fill: the ring visibly fills as risk rises. */}
      <View
        style={[
          styles.track,
          { width: size, height: size, borderRadius: size / 2, borderColor: colors.bgElevated },
        ]}
      />
      <View
        style={[
          styles.fillClip,
          { width: size, height: size, borderRadius: size / 2 },
        ]}>
        <Animated.View
          style={[styles.fill, { height: fillHeight, backgroundColor: `${ringColor}22` }]}
        />
      </View>
      <View
        style={[
          styles.ring,
          { width: size, height: size, borderRadius: size / 2, borderColor: ringColor },
        ]}
      />

      <View style={styles.center}>
        <Text style={styles.caption}>SECURITY RISK INDEX</Text>
        <Text style={[styles.score, { color: ringColor }]}>{score}</Text>
        <Text style={styles.outOf}>/ 100</Text>
        <Text style={[styles.state, { color: ringColor }]}>
          {label.toUpperCase()} {TREND_GLYPH[trend]}
        </Text>
        <Text style={styles.trend}>{TREND_LABEL[trend]}</Text>
      </View>

      {(state === 'high' || state === 'critical') && (
        <PulseRing size={size} color={ringColor} />
      )}
    </View>
  );
};

const PulseRing: React.FC<{ size: number; color: string }> = ({ size, color }) => {
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1.08, duration: 800, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 1, duration: 800, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.pulse,
        {
          width: size + 20,
          height: size + 20,
          borderRadius: (size + 20) / 2,
          borderColor: color,
          transform: [{ scale: pulse }],
        },
      ]}
    />
  );
};

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
    position: 'relative',
  },
  track: { position: 'absolute', borderWidth: 3 },
  fillClip: { position: 'absolute', overflow: 'hidden', justifyContent: 'flex-end' },
  fill: { width: '100%' },
  ring: { position: 'absolute', borderWidth: 3, opacity: 0.9 },
  center: { alignItems: 'center' },
  caption: {
    fontSize: 9,
    fontWeight: '700',
    color: colors.textMuted,
    letterSpacing: 1.4,
    marginBottom: 2,
  },
  score: { fontSize: 52, fontWeight: '800', letterSpacing: -1, lineHeight: 56 },
  outOf: { fontSize: 11, color: colors.textMuted, marginTop: -4 },
  state: { fontSize: 13, fontWeight: '700', letterSpacing: 1, marginTop: 6 },
  trend: { fontSize: 10, color: colors.textMuted, marginTop: 1 },
  pulse: { position: 'absolute', borderWidth: 2, opacity: 0.3 },
});
