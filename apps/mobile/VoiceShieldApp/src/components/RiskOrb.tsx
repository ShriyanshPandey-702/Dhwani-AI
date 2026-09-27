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
}) => {
  const { colors, riskColors, isDark } = useTheme();
  const themeRiskColor = riskColors[state] || riskColors.insufficient_evidence;
  const label = DISPLAY_LABELS[state] || "INSUFFICIENT EVIDENCE";

  // Animation values
  const animatedScore = useRef(new Animated.Value(score)).current;
  const pulseScale = useRef(new Animated.Value(1)).current;
  const pulseOpacity = useRef(new Animated.Value(0.25)).current;
  const waveScale = useRef(new Animated.Value(1)).current;
  const orbFloat = useRef(new Animated.Value(1)).current;

  // Track score transitions
  useEffect(() => {
    Animated.timing(animatedScore, {
      toValue: Math.min(100, Math.max(0, score)),
      duration: 600,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [score, animatedScore]);

  // Active Siri-like pulse animation when session is live
  useEffect(() => {
    if (!isActive) {
      // Settle smoothly to resting state when idle
      Animated.parallel([
        Animated.timing(pulseScale, { toValue: 1, duration: 400, useNativeDriver: true }),
        Animated.timing(pulseOpacity, { toValue: 0.15, duration: 400, useNativeDriver: true }),
        Animated.timing(waveScale, { toValue: 1, duration: 400, useNativeDriver: true }),
        Animated.timing(orbFloat, { toValue: 1, duration: 400, useNativeDriver: true }),
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
  }, [isActive, state, pulseScale, pulseOpacity, waveScale, orbFloat]);

  const clampedScore = Math.round(Math.min(100, Math.max(0, score)));

  return (
    <View style={[styles.outerContainer, { width: size + 36, height: size + 36 }]}>
      {/* 1. Outermost Glowing Ambient Halo */}
      <Animated.View
        style={[
          styles.ambientGlow,
          {
            width: size + 28,
            height: size + 28,
            borderRadius: (size + 28) / 2,
            backgroundColor: `${themeRiskColor}12`,
            borderColor: `${themeRiskColor}22`,
            opacity: pulseOpacity,
            transform: [{ scale: pulseScale }],
          },
        ]}
      />

      {/* 2. Secondary Animated Wave Ring (Visible during active analysis) */}
      <Animated.View
        style={[
          styles.waveRing,
          {
            width: size + 12,
            height: size + 12,
            borderRadius: (size + 12) / 2,
            borderColor: `${themeRiskColor}44`,
            opacity: isActive ? pulseOpacity : 0.2,
            transform: [{ scale: waveScale }],
          },
        ]}
      />

      {/* 3. Base Outer Geometric Circle */}
      <View
        style={[
          styles.baseCircle,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            backgroundColor: isDark ? colors.surface : colors.surface,
            borderColor: `${themeRiskColor}55`,
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
              backgroundColor: isDark ? colors.surfaceElevated : "#FDFBFA",
              borderColor: `${themeRiskColor}33`,
            },
          ]}
        >
          {/* Core Content */}
          <View style={styles.contentColumn}>
            {sublabel ? (
              <Text
                style={[
                  styles.sublabel,
                  { color: colors.textSecondary },
                ]}
              >
                {sublabel.toUpperCase()}
              </Text>
            ) : null}

            <Text
              style={[
                styles.scoreText,
                { color: themeRiskColor },
              ]}
            >
              {clampedScore}
            </Text>

            <Text
              style={[
                styles.stateLabel,
                { color: themeRiskColor },
              ]}
            >
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
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 16,
    elevation: 4,
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
