import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useTheme } from '../utils/theme';
import { PlaybackStatus } from '../hooks/useLiveDemoPlayback';

interface DemoPlaybackControlsProps {
  playbackStatus: PlaybackStatus;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onRestart: () => void;
  onStop: () => void;
}

export const DemoPlaybackControls: React.FC<DemoPlaybackControlsProps> = ({
  playbackStatus,
  onStart,
  onPause,
  onResume,
  onRestart,
  onStop,
}) => {
  const { colors, radius, isDark } = useTheme();

  const isPlaying = playbackStatus === 'playing';
  const isPaused = playbackStatus === 'paused';
  const isIdle = playbackStatus === 'idle' || playbackStatus === 'ended';

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.surface : '#FFFFFF',
          borderColor: colors.border,
          borderRadius: radius.xl,
          shadowColor: isDark ? '#000000' : colors.cardShadow,
        },
      ]}
    >
      {/* Top Banner with status badge */}
      <View style={styles.topRow}>
        <View style={styles.demoBadge}>
          <View
            style={[
              styles.statusDot,
              {
                backgroundColor: isPlaying
                  ? colors.success
                  : isPaused
                  ? colors.warning
                  : colors.textMuted,
              },
            ]}
          />
          <Text style={[styles.demoBadgeText, { color: colors.textPrimary }]}>
            {isPlaying
              ? 'DEMO PLAYBACK ACTIVE'
              : isPaused
              ? 'PLAYBACK PAUSED (FREEZE)'
              : 'DEMO READY'}
          </Text>
        </View>

        <Text style={[styles.sourceNote, { color: colors.textMuted }]}>
          Source: final_audio.mp3
        </Text>
      </View>

      {/* Primary Action Buttons Row */}
      <View style={styles.buttonsRow}>
        {/* Play / Pause / Resume */}
        {isPlaying ? (
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={onPause}
            style={[
              styles.primaryBtn,
              {
                backgroundColor: `${colors.warning}18`,
                borderColor: `${colors.warning}50`,
                borderRadius: radius.lg,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="Pause demo playback"
          >
            <Text style={[styles.btnIcon, { color: colors.warning }]}>⏸</Text>
            <Text style={[styles.btnText, { color: colors.warning }]}>PAUSE</Text>
          </TouchableOpacity>
        ) : isPaused ? (
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={onResume}
            style={[
              styles.primaryBtn,
              {
                backgroundColor: colors.accent,
                borderColor: colors.accent,
                borderRadius: radius.lg,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="Resume demo playback"
          >
            <Text style={[styles.btnIcon, { color: '#FFFFFF' }]}>▶</Text>
            <Text style={[styles.btnText, { color: '#FFFFFF' }]}>RESUME</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity
            activeOpacity={0.8}
            onPress={onStart}
            style={[
              styles.primaryBtn,
              {
                backgroundColor: colors.accent,
                borderColor: colors.accent,
                borderRadius: radius.lg,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="Start live analysis demo"
          >
            <Text style={[styles.btnIcon, { color: '#FFFFFF' }]}>▶</Text>
            <Text style={[styles.btnText, { color: '#FFFFFF' }]}>START DEMO</Text>
          </TouchableOpacity>
        )}

        {/* Restart Button */}
        <TouchableOpacity
          activeOpacity={0.8}
          onPress={onRestart}
          style={[
            styles.secondaryBtn,
            {
              backgroundColor: isDark ? colors.surfaceElevated : '#F5EFEA',
              borderColor: colors.border,
              borderRadius: radius.lg,
            },
          ]}
          accessibilityRole="button"
          accessibilityLabel="Restart demo from beginning"
        >
          <Text style={[styles.secondaryBtnIcon, { color: colors.textPrimary }]}>↺</Text>
          <Text style={[styles.secondaryBtnText, { color: colors.textPrimary }]}>
            RESTART
          </Text>
        </TouchableOpacity>

        {/* Reset / Stop Button */}
        <TouchableOpacity
          activeOpacity={0.8}
          onPress={onStop}
          disabled={isIdle}
          style={[
            styles.stopBtn,
            {
              backgroundColor: `${colors.danger}12`,
              borderColor: `${colors.danger}35`,
              borderRadius: radius.lg,
              opacity: isIdle ? 0.45 : 1.0,
            },
          ]}
          accessibilityRole="button"
          accessibilityLabel="Stop demo"
        >
          <Text style={[styles.secondaryBtnIcon, { color: colors.danger }]}>⏹</Text>
          <Text style={[styles.secondaryBtnText, { color: colors.danger }]}>STOP</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    padding: 12,
    gap: 10,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  demoBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
  },
  demoBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.6,
  },
  sourceNote: {
    fontSize: 9,
    fontWeight: '500',
  },
  buttonsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  primaryBtn: {
    flex: 2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 11,
    paddingHorizontal: 12,
    borderWidth: 1,
    gap: 6,
  },
  btnIcon: {
    fontSize: 14,
    fontWeight: '800',
  },
  btnText: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.6,
  },
  secondaryBtn: {
    flex: 1.2,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 11,
    paddingHorizontal: 8,
    borderWidth: 1,
    gap: 5,
  },
  secondaryBtnIcon: {
    fontSize: 14,
    fontWeight: '800',
  },
  secondaryBtnText: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  stopBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 11,
    paddingHorizontal: 8,
    borderWidth: 1,
    gap: 4,
  },
});
