import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { PanelCard } from './PanelCard';
import { colors, spacing } from '../utils/theme';
import { EventSeverity, EventStream, TimelineEntry } from '../types';

interface Props {
  events: TimelineEntry[];
  limit?: number;
}

const SEVERITY_COLOR: Record<EventSeverity, string> = {
  info: colors.info,
  warning: colors.suspicious,
  critical: colors.high,
};

const STREAM_LABEL: Record<EventStream, string> = {
  authenticity: 'VOICE',
  identity: 'ID',
  context: 'CONTEXT',
  risk: 'RISK',
  policy: 'POLICY',
  session: 'SESSION',
};

const formatTime = (at: number) => {
  const d = new Date(at);
  const pad = (n: number) => `${n}`.padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

/** Real-time event timeline — newest first, appended as events arrive. */
export const EventTimeline: React.FC<Props> = ({ events, limit = 12 }) => (
  <PanelCard
    title="DETECTED EVENTS"
    meta={events.length ? `${events.length} total` : undefined}>
    {events.length === 0 ? (
      <Text style={styles.empty}>No security events detected yet.</Text>
    ) : (
      events.slice(0, limit).map(event => (
        <View key={event.id} style={styles.row}>
          <Text style={styles.time}>{formatTime(event.at)}</Text>
          <View
            style={[
              styles.dot,
              { backgroundColor: SEVERITY_COLOR[event.severity] || colors.info },
            ]}
          />
          <View style={styles.body}>
            <Text style={styles.label}>{event.label}</Text>
            <Text style={styles.stream}>{STREAM_LABEL[event.stream] || 'EVENT'}</Text>
          </View>
        </View>
      ))
    )}
  </PanelCard>
);

const styles = StyleSheet.create({
  empty: { color: colors.textMuted, fontSize: 13, fontStyle: 'italic' },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  time: {
    fontSize: 11,
    color: colors.textMuted,
    fontVariant: ['tabular-nums'],
    width: 58,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  body: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  label: { flex: 1, fontSize: 13, color: colors.textPrimary },
  stream: {
    fontSize: 9,
    fontWeight: '700',
    color: colors.textMuted,
    letterSpacing: 0.8,
  },
});
