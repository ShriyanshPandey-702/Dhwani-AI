import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { useTheme } from '../utils/theme';

export interface LiveAudioWaveformProps {
  audioLevel?: number; // 0.0 to 1.0 (derived from real PCM RMS)
  isActive?: boolean;
  barCount?: number;
  height?: number;
  color?: string;
  isSilence?: boolean;
  bars?: number[]; // Real spectral amplitudes for each bar [0.0 to 1.0]
}

// Pre-computed vocal formants envelope weights (bell curve representing human speech spectrum fallback)
const SPECTRUM_WEIGHTS = [
  0.15, 0.22, 0.35, 0.52, 0.70, 0.85, 0.95, 1.0, 0.98, 0.92, 0.88, 0.82,
  0.89, 0.97, 1.0, 0.94, 0.86, 0.78, 0.72, 0.80, 0.91, 0.85, 0.74, 0.62,
  0.50, 0.42, 0.35, 0.28, 0.22, 0.18, 0.15, 0.12, 0.10, 0.08, 0.07, 0.06,
];

export const LiveAudioWaveform: React.FC<LiveAudioWaveformProps> = ({
  audioLevel = 0.0,
  isActive = false,
  barCount = 36,
  height = 44,
  color,
  isSilence = false,
  bars: dynamicBars,
}) => {
  const { colors, isDark } = useTheme();
  const activeColor = color || colors.accent;

  // Determine whether audio is currently silent
  const hasDynamicBars = Array.isArray(dynamicBars) && dynamicBars.length > 0;
  const barsActive = hasDynamicBars ? dynamicBars.some((v) => v > 0.01) : false;
  const isCurrentlySilent =
    isSilence ||
    !isActive ||
    (!barsActive && (audioLevel === undefined || audioLevel < 0.015));

  // Clamped real audio level
  const clampedLevel = Math.max(0.0, Math.min(1.0, audioLevel));
  const animatedLevel = useRef(new Animated.Value(0)).current;

  // Fade transition between active bars and flat silence line
  const silenceOpacity = useRef(new Animated.Value(isCurrentlySilent ? 1 : 0)).current;

  useEffect(() => {
    Animated.timing(animatedLevel, {
      toValue: isCurrentlySilent ? 0 : clampedLevel,
      duration: 100,
      useNativeDriver: false,
    }).start();
  }, [clampedLevel, isCurrentlySilent, animatedLevel]);

  useEffect(() => {
    Animated.timing(silenceOpacity, {
      toValue: isCurrentlySilent ? 1 : 0,
      duration: 180,
      useNativeDriver: true,
    }).start();
  }, [isCurrentlySilent, silenceOpacity]);

  // Render when silent: ONE CLEAN CONTINUOUS HORIZONTAL LINE
  if (isCurrentlySilent) {
    return (
      <View style={[styles.container, { height }]}>
        <View style={styles.flatLineWrapper}>
          <View
            style={[
              styles.flatLine,
              {
                backgroundColor: isDark ? `${activeColor}55` : `${activeColor}40`,
              },
            ]}
          />
        </View>
      </View>
    );
  }

  // Render when audio is active: DYNAMIC AUDIO-RESPONSIVE BARS
  const maxHeight = Math.max(16, height - 6);

  const barElements = Array.from({ length: barCount }, (_, i) => {
    let barVal = 0;

    if (hasDynamicBars) {
      // Direct acoustic spectral data from real audio
      const barIdx = Math.min(dynamicBars.length - 1, Math.floor((i / barCount) * dynamicBars.length));
      const rawVal = Math.max(0.0, Math.min(1.0, dynamicBars[barIdx] ?? 0));
      // Dynamic compression so vocal harmonics and formants are visually prominent:
      const compressed = Math.pow(rawVal, 0.42);
      const weightIndex = Math.min(
        SPECTRUM_WEIGHTS.length - 1,
        Math.floor((i / barCount) * SPECTRUM_WEIGHTS.length)
      );
      const formantWeight = 0.5 + 0.5 * (SPECTRUM_WEIGHTS[weightIndex] ?? 0.5);
      barVal = Math.max(0.06, Math.min(1.0, (compressed * 0.75 + clampedLevel * 0.35) * formantWeight));
    } else {
      // Fallback: real RMS scaled by spectral weights
      const weightIndex = Math.min(
        SPECTRUM_WEIGHTS.length - 1,
        Math.floor((i / barCount) * SPECTRUM_WEIGHTS.length)
      );
      const spectralWeight = SPECTRUM_WEIGHTS[weightIndex] ?? 0.5;
      barVal = clampedLevel * spectralWeight;
    }

    // Dynamic height and opacity based on actual audio energy
    const dynamicBarHeight = Math.max(3, Math.round(barVal * maxHeight));
    const dynamicOpacity = Math.max(0.4, Math.min(0.95, 0.4 + barVal * 0.55));

    return (
      <View
        key={i}
        style={[
          styles.bar,
          {
            height: dynamicBarHeight,
            opacity: dynamicOpacity,
            backgroundColor: activeColor,
          },
        ]}
      />
    );
  });

  return (
    <View style={[styles.container, { height }]}>
      <View style={styles.waveformRow}>{barElements}</View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    width: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    overflow: 'hidden',
    paddingHorizontal: 4,
  },
  flatLineWrapper: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 12,
  },
  flatLine: {
    width: '100%',
    height: 2,
    borderRadius: 1,
  },
  waveformRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
    height: '100%',
  },
  bar: {
    flex: 1,
    marginHorizontal: 1.2,
    borderRadius: 2,
    alignSelf: 'center',
  },
});
