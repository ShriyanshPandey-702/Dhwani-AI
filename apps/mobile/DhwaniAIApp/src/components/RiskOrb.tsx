import React, { useEffect, useRef } from "react";
import { View, Text, Animated, StyleSheet, Easing } from "react-native";
import { useTheme } from "../utils/theme";
import { RiskState, RiskTrend } from "../types";

interface RiskOrbProps {
  score: number;
  state: RiskState;
  isActive?: boolean;
  trend?: RiskTrend;
  size?: number;
  sublabel?: string;
  audioLevel?: number;
}

const DISPLAY_LABELS: Record<RiskState, string> = {
  insufficient_evidence: "INSUFFICIENT EVIDENCE",
  low: "LOW RISK",
  suspicious: "SUSPICIOUS",
  high: "HIGH RISK",
  critical: "CRITICAL",
};

export const RiskOrb: React.FC<RiskOrbProps> = ({
  score,
  state,
  isActive = false,
  trend = "stable",
  size = 200,
  sublabel,
  audioLevel = 0.0,
}) => {
  const { colors, riskColors, isDark } = useTheme();
  const themeRiskColor = riskColors[state] || riskColors.insufficient_evidence;
  const label = DISPLAY_LABELS[state] || "INSUFFICIENT EVIDENCE";

  // Animation values
  const animatedScore = useRef(new Animated.Value(score)).current;
  const pulseScale = useRef(new Animated.Value(1)).current;
  const pulseOpacity = useRef(new Animated.Value(0.25)).current;
  const waveScale = useRef(new Animated.Value(1)).current;
  const spinValue = useRef(new Animated.Value(0)).current;
  const audioRingScale = useRef(new Animated.Value(1)).current;

  // Track score transitions
  useEffect(() => {
    Animated.timing(animatedScore, {
      toValue: Math.min(100, Math.max(0, score)),
      duration: 600,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [score, animatedScore]);

  // Audio level reactive scale (without changing score calculation)
  useEffect(() => {
    const clamped = Math.max(0, Math.min(1, audioLevel));
    Animated.timing(audioRingScale, {
      toValue: isActive ? 1 + clamped * 0.18 : 1,
      duration: 120,
      useNativeDriver: true,
    }).start();
  }, [audioLevel, isActive, audioRingScale]);

  // Orbital continuous rotation
  useEffect(() => {
    if (!isActive) {
      spinValue.setValue(0);
      return;
    }
    const spinAnim = Animated.loop(
      Animated.timing(spinValue, {
        toValue: 1,
        duration: 8000,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    );
    spinAnim.start();
    return () => spinAnim.stop();
  }, [isActive, spinValue]);

  // Active pulse animation when session is live
  useEffect(() => {
    if (!isActive) {
      Animated.parallel([
        Animated.timing(pulseScale, { toValue: 1, duration: 400, useNativeDriver: true }),
        Animated.timing(pulseOpacity, { toValue: 0.15, duration: 400, useNativeDriver: true }),
        Animated.timing(waveScale, { toValue: 1, duration: 400, useNativeDriver: true }),
      ]).start();
      return;
    }

    const isElevated = state === "high" || state === "critical";
    const pulseDuration = isElevated ? 900 : 1600;
    const maxPulseScale = isElevated ? 1.14 : 1.08;

    const pulseAnimation = Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(pulseScale, {
            toValue: maxPulseScale,
            duration: pulseDuration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(pulseScale, {
            toValue: 1,
            duration: pulseDuration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(pulseOpacity, {
            toValue: 0.45,
            duration: pulseDuration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
          Animated.timing(pulseOpacity, {
            toValue: 0.15,
            duration: pulseDuration,
            easing: Easing.inOut(Easing.sin),
            useNativeDriver: true,
          }),
        ]),
        Animated.sequence([
          Animated.timing(waveScale, {
            toValue: maxPulseScale * 1.05,
            duration: pulseDuration * 1.2,
            easing: Easing.out(Easing.quad),
            useNativeDriver: true,
          }),
          Animated.timing(waveScale, {
            toValue: 1,
            duration: pulseDuration * 1.2,
            easing: Easing.in(Easing.quad),
            useNativeDriver: true,
          }),
        ]),
      ])
    );

    pulseAnimation.start();
    return () => pulseAnimation.stop();
  }, [isActive, state, pulseScale, pulseOpacity, waveScale]);

  const clampedScore = Math.round(Math.min(100, Math.max(0, score)));

  const spin = spinValue.interpolate({
    inputRange: [0, 1],
    outputRange: ["0deg", "360deg"],
  });

  return (
    <View style={[styles.outerContainer, { width: size + 44, height: size + 44 }]}>
      {/* 1. Outermost Glowing Ambient Halo */}
      <Animated.View
        style={[
          styles.ambientGlow,
          {
            width: size + 36,
            height: size + 36,
            borderRadius: (size + 36) / 2,
            backgroundColor: `${themeRiskColor}10`,
            borderColor: `${themeRiskColor}22`,
            opacity: pulseOpacity,
            transform: [{ scale: pulseScale }],
          },
        ]}
      />

      {/* 2. Audio-reactive resonance ring */}
      <Animated.View
        style={[
          styles.audioRing,
          {
            width: size + 20,
            height: size + 20,
            borderRadius: (size + 20) / 2,
            borderColor: `${themeRiskColor}33`,
            transform: [{ scale: audioRingScale }],
          },
        ]}
      />

      {/* 3. Secondary Animated Orbital Ring */}
      <Animated.View
        style={[
          styles.waveRing,
          {
            width: size + 8,
            height: size + 8,
            borderRadius: (size + 8) / 2,
            borderColor: `${themeRiskColor}55`,
            opacity: isActive ? 0.75 : 0.25,
            transform: [{ rotate: spin }],
          },
        ]}
      />

      {/* 4. Base Outer Geometric Circle */}
      <View
        style={[
          styles.baseCircle,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            backgroundColor: isDark ? colors.surface : colors.surface,
            borderColor: `${themeRiskColor}66`,
            shadowColor: themeRiskColor,
          },
        ]}
      >
        {/* Inner subtle glow ring */}
        <View
          style={[
            styles.innerRing,
            {
              width: size - 16,
              height: size - 16,
              borderRadius: (size - 16) / 2,
              backgroundColor: isDark ? colors.surfaceElevated : "#FFFFFF",
              borderColor: `${themeRiskColor}33`,
            },
          ]}
        >
          {/* Core Content */}
          <View style={styles.contentColumn}>
            {sublabel ? (
              <Text style={[styles.sublabel, { color: colors.textSecondary }]}>
                {sublabel.toUpperCase()}
              </Text>
            ) : null}

            <Text style={[styles.scoreText, { color: themeRiskColor }]}>
              {clampedScore}
            </Text>

            <Text style={[styles.stateLabel, { color: themeRiskColor }]}>
              {label}
            </Text>

            {isActive && trend ? (
              <Text style={[styles.trendText, { color: colors.textMuted }]}>
                {trend === "rising" ? "↑ Risk rising" : trend === "falling" ? "↓ Risk easing" : "→ Risk steady"}
              </Text>
            ) : null}
          </View>
        </View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  outerContainer: {
    alignItems: "center",
    justifyContent: "center",
    alignSelf: "center",
    marginVertical: 12,
  },
  ambientGlow: {
    position: "absolute",
    borderWidth: 1,
  },
  audioRing: {
    position: "absolute",
    borderWidth: 1.5,
    borderStyle: "solid",
  },
  waveRing: {
    position: "absolute",
    borderWidth: 1.5,
    borderStyle: "dashed",
  },
  baseCircle: {
    position: "absolute",
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    elevation: 5,
  },
  innerRing: {
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  contentColumn: {
    alignItems: "center",
    justifyContent: "center",
  },
  sublabel: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.2,
    marginBottom: 2,
  },
  scoreText: {
    fontSize: 54,
    fontWeight: "800",
    letterSpacing: -1.5,
    lineHeight: 58,
  },
  stateLabel: {
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 1,
    marginTop: 2,
    textAlign: "center",
  },
  trendText: {
    fontSize: 10,
    fontWeight: "500",
    marginTop: 3,
  },
});
