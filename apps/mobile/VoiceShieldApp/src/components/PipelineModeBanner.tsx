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
          backgroundColor: isMock ? `${colors.warning}18` : `${colors.safe}18`,
          borderColor: isMock ? `${colors.warning}55` : `${colors.safe}55`,
        },
      ]}>
      <Text style={[styles.text, { color: isMock ? colors.warning : colors.safe }]}>
        {isMock
          ? 'DEMO — mock audio through the real pipeline. Not AI detection results.'
          : 'LIVE AUDIO — streamed from this device.'}
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
  },
  text: { fontSize: 11, fontWeight: '700', letterSpacing: 0.3, lineHeight: 15 },
});
