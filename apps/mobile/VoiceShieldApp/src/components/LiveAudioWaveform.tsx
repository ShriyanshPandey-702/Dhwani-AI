import React, { useEffect, useRef } from "react";
import { View, StyleSheet, Animated } from "react-native";
import { useTheme } from "../utils/theme";

interface LiveAudioWaveformProps {
  audioLevel?: number; // 0.0 to 1.0 (derived from real PCM RMS)
  isActive?: boolean;
  barCount?: number;
  height?: number;
  color?: string;
}

// Pre-computed vocal formants envelope weights (bell curve representing human speech spectrum)
const SPECTRUM_WEIGHTS = [
  0.15, 0.22, 0.35, 0.52, 0.70, 0.85, 0.95, 1.0, 0.98, 0.92, 0.88, 0.82,
  0.89, 0.97, 1.0, 0.94, 0.86, 0.78, 0.72, 0.80, 0.91, 0.85, 0.74, 0.62,
  0.50, 0.42, 0.35, 0.28, 0.22, 0.18, 0.15, 0.12, 0.10, 0.08, 0.07, 0.06,
];

export const LiveAudioWaveform: React.FC<LiveAudioWaveformProps> = ({
  audioLevel = 0.0,
  isActive = false,
  barCount = 36,
  height = 54,
  color,
}) => {
  const { colors } = useTheme();
  const activeColor = color || colors.accent;

  // Clamped real audio level
  const clampedLevel = Math.max(0.0, Math.min(1.0, audioLevel));

  // Animated values for smooth bar transitions
  const animatedLevel = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(animatedLevel, {
      toValue: isActive ? clampedLevel : 0,
      duration: 100,
      useNativeDriver: false,
    }).start();
  }, [clampedLevel, isActive, animatedLevel]);

  const bars = Array.from({ length: barCount }, (_, i) => {
    const weightIndex = Math.min(
      SPECTRUM_WEIGHTS.length - 1,
      Math.floor((i / barCount) * SPECTRUM_WEIGHTS.length)
    );
    const spectralWeight = SPECTRUM_WEIGHTS[weightIndex] ?? 0.5;

    // Minimum resting height = 4px, dynamic height scales up to (height - 6)px
    const minHeight = 4;
    const maxHeight = height - 6;

    const barHeight = animatedLevel.interpolate({
      inputRange: [0, 0.05, 0.2, 0.5, 1.0],
      outputRange: [
        minHeight,
        minHeight + 3 * spectralWeight,
        minHeight + (maxHeight * 0.35) * spectralWeight,
        minHeight + (maxHeight * 0.70) * spectralWeight,
        minHeight + maxHeight * spectralWeight,
      ],
      extrapolate: "clamp",
    });

    const barOpacity = animatedLevel.interpolate({
      inputRange: [0, 0.1, 1.0],
      outputRange: [0.28, 0.65, 0.95],
      extrapolate: "clamp",
    });

    return (
      <Animated.View
        key={i}
        style={[
          styles.bar,
          {
            height: barHeight,
            opacity: barOpacity,
            backgroundColor: activeColor,
          },
        ]}
      />
    );
  });

  return (
    <View style={[styles.container, { height }]}>
      <View style={styles.waveformRow}>{bars}</View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: "100%",
    justifyContent: "center",
    alignItems: "center",
    overflow: "hidden",
  },
  waveformRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    width: "100%",
    paddingHorizontal: 4,
  },
  bar: {
    flex: 1,
    marginHorizontal: 1.5,
    borderRadius: 2,
    minHeight: 4,
  },
});
