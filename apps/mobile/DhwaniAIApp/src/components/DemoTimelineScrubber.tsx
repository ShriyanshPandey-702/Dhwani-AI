import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { useTheme } from '../utils/theme';
import { DEMO_TOTAL_DURATION, getDemoPhase, DemoPhase } from '../utils/demoLiveEngine';

interface DemoTimelineScrubberProps {
  currentTime: number;
  totalDuration?: number;
  onSeek?: (timeSeconds: number) => void;
}

interface SegmentDef {
  id: DemoPhase | 'SILENCE_1' | 'SILENCE_2';
  label: string;
  start: number;
  end: number;
  colorType: 'safe' | 'muted' | 'warning' | 'critical';
}

const SEGMENTS: SegmentDef[] = [
  { id: 'HUMAN', label: 'HUMAN', start: 0, end: 13, colorType: 'safe' },
  { id: 'SILENCE_1', label: 'SILENCE', start: 13, end: 16, colorType: 'muted' },
  { id: 'AI_CLONED', label: 'CLONED', start: 16, end: 33, colorType: 'warning' },
  { id: 'SILENCE_2', label: 'SILENCE', start: 33, end: 36, colorType: 'muted' },
  { id: 'AI_GENERATED', label: 'AI GENERATED', start: 36, end: 45.632, colorType: 'critical' },
];

function formatTime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const mins = Math.floor(s / 60);
  const secs = s % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export const DemoTimelineScrubber: React.FC<DemoTimelineScrubberProps> = ({
  currentTime,
  totalDuration = DEMO_TOTAL_DURATION,
  onSeek,
}) => {
  const { colors, radius, isDark } = useTheme();
  const currentPhase = getDemoPhase(currentTime);
  const progressPercent = Math.min(100, Math.max(0, (currentTime / totalDuration) * 100));

  const getColor = (colorType: SegmentDef['colorType']) => {
    switch (colorType) {
      case 'safe':
        return colors.success;
      case 'warning':
        return colors.warning;
      case 'critical':
        return colors.danger;
      case 'muted':
      default:
        return colors.textMuted;
    }
  };

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.surface : '#FFFFFF',
          borderColor: colors.border,
          borderRadius: radius.lg,
        },
      ]}
    >
      {/* Header with current phase badge and time elapsed */}
      <View style={styles.topRow}>
        <View style={styles.phaseBadgeRow}>
          <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>
            DEMO TIMELINE
          </Text>
          <View
            style={[
              styles.currentPhaseChip,
              {
                backgroundColor:
                  currentPhase === 'HUMAN'
                    ? `${colors.success}18`
                    : currentPhase === 'AI_CLONED'
                    ? `${colors.warning}18`
                    : currentPhase === 'AI_GENERATED'
                    ? `${colors.danger}18`
                    : `${colors.textMuted}18`,
                borderColor:
                  currentPhase === 'HUMAN'
                    ? `${colors.success}40`
                    : currentPhase === 'AI_CLONED'
                    ? `${colors.warning}40`
                    : currentPhase === 'AI_GENERATED'
                    ? `${colors.danger}40`
                    : `${colors.textMuted}30`,
              },
            ]}
          >
            <View
              style={[
                styles.phaseDot,
                {
                  backgroundColor:
                    currentPhase === 'HUMAN'
                      ? colors.success
                      : currentPhase === 'AI_CLONED'
                      ? colors.warning
                      : currentPhase === 'AI_GENERATED'
                      ? colors.danger
                      : colors.textMuted,
                },
              ]}
            />
            <Text
              style={[
                styles.currentPhaseText,
                {
                  color:
                    currentPhase === 'HUMAN'
                      ? colors.success
                      : currentPhase === 'AI_CLONED'
                      ? colors.warning
                      : currentPhase === 'AI_GENERATED'
                      ? colors.danger
                      : colors.textMuted,
                },
              ]}
            >
              {currentPhase === 'HUMAN'
                ? 'PHASE 1: REAL HUMAN'
                : currentPhase === 'AI_CLONED'
                ? 'PHASE 2: AI CLONED'
                : currentPhase === 'AI_GENERATED'
                ? 'PHASE 3: AI GENERATED'
                : 'INTER-PHASE SILENCE'}
            </Text>
          </View>
        </View>

        <Text style={[styles.timeText, { color: colors.textSecondary }]}>
          {formatTime(currentTime)} / {formatTime(totalDuration)}
        </Text>
      </View>

      {/* Segmented Timeline Track */}
      <View style={[styles.trackContainer, { backgroundColor: isDark ? colors.surfaceElevated : '#EAE5E0' }]}>
        {SEGMENTS.map((seg, idx) => {
          const segWidth = ((seg.end - seg.start) / totalDuration) * 100;
          const isSegActive = currentTime >= seg.start && currentTime < seg.end;
          const segColor = getColor(seg.colorType);

          return (
            <TouchableOpacity
              key={idx}
              activeOpacity={0.7}
              disabled={!onSeek}
              onPress={() => onSeek && onSeek(seg.start)}
              style={[
                styles.segmentTrack,
                {
                  width: `${segWidth}%`,
                  borderRightWidth: idx < SEGMENTS.length - 1 ? 1 : 0,
                  borderRightColor: isDark ? '#00000030' : '#FFFFFF60',
                },
              ]}
            >
              <View
                style={[
                  styles.segmentFill,
                  {
                    backgroundColor: isSegActive ? `${segColor}30` : 'transparent',
                  },
                ]}
              />
            </TouchableOpacity>
          );
        })}

        {/* Dynamic Progress Fill and Cursor */}
        <View
          style={[
            styles.progressFill,
            {
              width: `${progressPercent}%`,
              backgroundColor: `${colors.accent}40`,
            },
          ]}
        />
        <View
          style={[
            styles.cursor,
            {
              left: `${progressPercent}%`,
              backgroundColor: colors.accent,
            },
          ]}
        />
      </View>

      {/* Segment Labels Row */}
      <View style={styles.labelsRow}>
        {SEGMENTS.map((seg, idx) => {
          const segWidth = ((seg.end - seg.start) / totalDuration) * 100;
          const isSegActive = currentTime >= seg.start && currentTime < seg.end;
          const segColor = getColor(seg.colorType);

          return (
            <View key={idx} style={{ width: `${segWidth}%`, alignItems: 'center' }}>
              <Text
                numberOfLines={1}
                style={[
                  styles.segLabel,
                  {
                    color: isSegActive ? segColor : colors.textMuted,
                    fontWeight: isSegActive ? '800' : '600',
                  },
                ]}
              >
                {seg.label}
              </Text>
              <Text style={[styles.segTime, { color: colors.textMuted }]}>
                {Math.round(seg.start)}s
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    padding: 10,
    gap: 8,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  phaseBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
  },
  sectionTitle: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  currentPhaseChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 99,
    borderWidth: 1,
    gap: 5,
  },
  phaseDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
  },
  currentPhaseText: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
  timeText: {
    fontSize: 10,
    fontWeight: '700',
    fontVariant: ['tabular-nums'],
  },
  trackContainer: {
    height: 10,
    borderRadius: 5,
    position: 'relative',
    overflow: 'hidden',
    flexDirection: 'row',
  },
  segmentTrack: {
    height: '100%',
  },
  segmentFill: {
    width: '100%',
    height: '100%',
  },
  progressFill: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    left: 0,
    borderRadius: 5,
  },
  cursor: {
    position: 'absolute',
    top: -1,
    bottom: -1,
    width: 3,
    borderRadius: 1.5,
    marginLeft: -1.5,
  },
  labelsRow: {
    flexDirection: 'row',
    width: '100%',
  },
  segLabel: {
    fontSize: 8,
    letterSpacing: 0.2,
    textAlign: 'center',
  },
  segTime: {
    fontSize: 7,
    marginTop: 1,
    textAlign: 'center',
  },
});
