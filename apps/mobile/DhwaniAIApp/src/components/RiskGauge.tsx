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
  const label = RISK_LABELS[state] || 'Insufficient Evidence';
  const progress = useRef(new Animated.Value(0)).current;
  const orbScale = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(progress, {
        toValue: Math.min(100, Math.max(0, score)),
        duration: 500,
        useNativeDriver: false,
      }),
      Animated.spring(orbScale, {
        toValue: 1 + Math.min(1, Math.max(0, score / 100)) * 0.08,
        friction: 6,
        tension: 40,
        useNativeDriver: true,
      }),
    ]).start();
  }, [score, progress, orbScale]);

  const fillHeight = progress.interpolate({
    inputRange: [0, 100],
    outputRange: [0, size],
    extrapolate: 'clamp',
  });

  return (
    <View style={[styles.container, { width: size + 24, height: size + 24 }]}>
      {/* Outer Glow Halo */}
      <View
        style={[
          styles.glowHalo,
          {
            width: size + 16,
            height: size + 16,
            borderRadius: (size + 16) / 2,
            backgroundColor: `${ringColor}12`,
            borderColor: `${ringColor}33`,
          },
        ]}
      />

      {/* Base Track Ring */}
      <View
        style={[
          styles.track,
          { width: size, height: size, borderRadius: size / 2, borderColor: colors.bgElevated },
        ]}
      />

      {/* Dynamic Fill Clip */}
      <View
        style={[
          styles.fillClip,
          { width: size, height: size, borderRadius: size / 2 },
        ]}>
        <Animated.View
          style={[styles.fill, { height: fillHeight, backgroundColor: `${ringColor}28` }]}
        />
      </View>

      {/* Outer Border Ring */}
      <View
        style={[
          styles.ring,
          { width: size, height: size, borderRadius: size / 2, borderColor: ringColor },
        ]}
      />

      {/* Inner Central Orb */}
      <Animated.View
        style={[
          styles.innerOrb,
          {
            width: size - 36,
            height: size - 36,
            borderRadius: (size - 36) / 2,
            backgroundColor: colors.bgCard,
            borderColor: `${ringColor}44`,
            transform: [{ scale: orbScale }],
          },
        ]}>
        <View style={styles.center}>
          <Text style={styles.caption}>SECURITY RISK INDEX</Text>
          <Text style={[styles.score, { color: ringColor }]}>{score}</Text>
          <Text style={styles.outOf}>/ 100</Text>
          <Text style={[styles.state, { color: ringColor }]}>
            {label.toUpperCase()} {TREND_GLYPH[trend]}
          </Text>
          <Text style={styles.trend}>{TREND_LABEL[trend]}</Text>
        </View>
      </Animated.View>

      {(state === 'suspicious' || state === 'high' || state === 'critical') && (
        <PulseRing size={size} color={ringColor} state={state} />
      )}
    </View>
  );
};

const PulseRing: React.FC<{ size: number; color: string; state: RiskState }> = ({ size, color, state }) => {
  const pulse = useRef(new Animated.Value(1)).current;
  const opacity = useRef(new Animated.Value(0.4)).current;

  const duration = state === 'critical' ? 600 : state === 'high' ? 900 : 1400;
  const maxScale = state === 'critical' ? 1.15 : state === 'high' ? 1.10 : 1.05;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(pulse, { toValue: maxScale, duration, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(opacity, { toValue: 0.1, duration, useNativeDriver: true }),
          Animated.timing(opacity, { toValue: 0.4, duration, useNativeDriver: true }),
        ]),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [pulse, opacity, duration, maxScale]);

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
          opacity,
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
    marginVertical: 8,
  },
  glowHalo: {
    position: 'absolute',
    borderWidth: 1,
  },
  track: { position: 'absolute', borderWidth: 3 },
  fillClip: { position: 'absolute', overflow: 'hidden', justifyContent: 'flex-end' },
  fill: { width: '100%' },
  ring: { position: 'absolute', borderWidth: 3.5, opacity: 0.95 },
  innerOrb: {
    position: 'absolute',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
  },
  center: { alignItems: 'center' },
  caption: {
    fontSize: 9,
    fontWeight: '700',
    color: colors.textMuted,
    letterSpacing: 1.4,
    marginBottom: 2,
  },
  score: { fontSize: 48, fontWeight: '800', letterSpacing: -1, lineHeight: 52 },
  outOf: { fontSize: 11, color: colors.textMuted, marginTop: -2 },
  state: { fontSize: 11, fontWeight: '700', letterSpacing: 0.8, marginTop: 4, textAlign: 'center' },
  trend: { fontSize: 10, color: colors.textMuted, marginTop: 1 },
  pulse: { position: 'absolute', borderWidth: 2 },
});
