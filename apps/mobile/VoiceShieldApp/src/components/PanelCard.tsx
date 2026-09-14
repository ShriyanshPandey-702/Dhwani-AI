import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, spacing, radius } from '../utils/theme';

interface Props {
  title: string;
  /** Small right-aligned annotation, e.g. a confidence figure. */
  meta?: string;
  children: React.ReactNode;
  accent?: string;
}

/** Shared chrome for the evidence panels so they read as one system. */
export const PanelCard: React.FC<Props> = ({ title, meta, children, accent }) => (
  <View style={[styles.card, accent ? { borderColor: `${accent}55` } : null]}>
    <View style={styles.header}>
      <Text style={styles.title}>{title}</Text>
      {!!meta && <Text style={styles.meta}>{meta}</Text>}
    </View>
    <View style={styles.body}>{children}</View>
  </View>
);

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { fontSize: 11, fontWeight: '700', color: colors.textSecondary, letterSpacing: 1.2 },
  meta: { fontSize: 10, color: colors.textMuted },
  body: { gap: spacing.sm },
});
