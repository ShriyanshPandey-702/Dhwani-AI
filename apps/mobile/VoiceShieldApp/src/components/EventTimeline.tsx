import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { useTheme } from '../utils/theme';
import { EventSeverity, EventStream, TimelineEntry } from '../types';

interface Props {
  events: TimelineEntry[];
  limit?: number;
}

const STREAM_LABEL: Record<EventStream, string> = {
  authenticity: 'VOICE',
  identity: 'ID',
  context: 'CONTEXT',
  risk: 'RISK',
  policy: 'POLICY',
  session: 'SESSION',
};

const STREAM_ICON: Record<EventStream, string> = {
  authenticity: '🎙',
  identity: '👤',
  context: '💬',
  risk: '⚡',
  policy: '🔒',
  session: '📡',
};

const formatTime = (at: number) => {
  const d = new Date(at);
  const pad = (n: number) => `${n}`.padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

/** Real-time event timeline — newest first, appended as events arrive. */
export const EventTimeline: React.FC<Props> = ({ events, limit = 12 }) => {
  const { colors } = useTheme();

  const SEVERITY_COLOR: Record<EventSeverity, string> = {
    info: colors.accent,
    warning: colors.warning,
    critical: colors.danger,
  };

  return (
    <PanelCard
      title="DETECTED EVENTS"
      icon="📡"
      meta={events.length ? `${events.length} total` : undefined}
    >
      {events.length === 0 ? (
        <Text style={[styles.empty, { color: colors.textMuted }]}>
          No security events detected yet.
        </Text>
      ) : (
        events.slice(0, limit).map((event) => {
          const dotColor = SEVERITY_COLOR[event.severity] || colors.accent;
          const streamIcon = STREAM_ICON[event.stream] || '⚡';
          return (
            <View key={event.id} style={styles.row}>
              {/* Timeline dot + connecting line */}
              <View style={styles.dotCol}>
                <View style={[styles.dot, { backgroundColor: dotColor }]} />
              </View>

              {/* Content */}
              <View style={styles.content}>
                <View style={styles.topRow}>
                  <Text style={[styles.label, { color: colors.textPrimary }]}>
                    {event.label}
                  </Text>
                  <Text style={[styles.time, { color: colors.textMuted }]}>
                    {formatTime(event.at)}
                  </Text>
                </View>
                <View style={styles.bottomRow}>
                  <Text style={styles.streamIcon}>{streamIcon}</Text>
                  <Text style={[styles.stream, { color: colors.textMuted }]}>
                    {STREAM_LABEL[event.stream] || 'EVENT'}
                  </Text>
                  <View
                    style={[
                      styles.severityPill,
                      {
                        backgroundColor: `${dotColor}18`,
                        borderColor: `${dotColor}35`,
                      },
                    ]}
                  >
                    <Text style={[styles.severityText, { color: dotColor }]}>
                      {event.severity.toUpperCase()}
                    </Text>
                  </View>
                </View>
              </View>
            </View>
          );
        })
      )}
    </PanelCard>
  );
};

const styles = StyleSheet.create({
  empty: { fontSize: 13, fontStyle: 'italic' },
  row: {
    flexDirection: 'row',
    gap: 10,
    paddingVertical: 4,
  },
  dotCol: {
    alignItems: 'center',
    paddingTop: 4,
    width: 10,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  content: { flex: 1, gap: 3 },
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: 8,
  },
  label: { flex: 1, fontSize: 13, fontWeight: '600', lineHeight: 17 },
  time: {
    fontSize: 10,
    fontVariant: ['tabular-nums'],
    flexShrink: 0,
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  streamIcon: { fontSize: 10 },
  stream: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.8,
  },
  severityPill: {
    marginLeft: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 99,
    borderWidth: 1,
  },
  severityText: {
    fontSize: 8,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
});
