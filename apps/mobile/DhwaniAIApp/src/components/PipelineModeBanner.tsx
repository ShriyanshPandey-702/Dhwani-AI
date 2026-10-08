import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius } from '../utils/theme';
import { PipelineMode } from '../types';

interface Props {
  mode: PipelineMode;
}

/**
 * States plainly whether the dashboard is driven by mock audio or by live
 * device audio. Mock results must never be mistaken for real detection.
 */
export const PipelineModeBanner: React.FC<Props> = ({ mode }) => {
  const isMock = mode === 'mock';
  return (
    <View
      style={[
        styles.banner,
        {
          backgroundColor: isMock ? `${colors.warning}18` : `${colors.brand}18`,
          borderColor: isMock ? `${colors.warning}55` : `${colors.brand}55`,
        },
      ]}>
      <Text style={[styles.text, { color: isMock ? colors.warning : colors.brand }]}>
        {isMock
          ? 'DEMO MODE · Source: Simulation · Not AI detection results'
          : 'LIVE AUDIO · Source: Device microphone · Not caller audio'}
      </Text>
      <Text style={styles.subtext}>
        {isMock
          ? 'Running synthetic scenario through the multimodal risk pipeline.'
          : 'Cellular call audio is not available to third-party apps on this device.'}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  banner: {
    borderRadius: radius.sm,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: 2,
  },
  text: { fontSize: 12, fontWeight: '700', letterSpacing: 0.3, lineHeight: 16 },
  subtext: { fontSize: 11, color: colors.textSecondary, lineHeight: 15 },
});
