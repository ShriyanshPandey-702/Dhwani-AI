import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "../utils/theme";

interface Props {
  title: string;
  meta?: string;
  children: React.ReactNode;
  accent?: string;
}

/** Shared chrome for the evidence panels so they read as one system. */
export const PanelCard: React.FC<Props> = ({ title, meta, children, accent }) => {
  const { colors, radius, spacing, isDark } = useTheme();

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderColor: accent ? `${accent}55` : colors.border,
          borderRadius: radius.md,
          shadowColor: colors.cardShadow,
        },
      ]}
    >
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.textSecondary }]}>{title}</Text>
        {!!meta && <Text style={[styles.meta, { color: colors.textMuted }]}>{meta}</Text>}
      </View>
      <View style={styles.body}>{children}</View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    padding: 16,
    gap: 12,
    marginVertical: 4,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 2,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  title: {
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1.2,
  },
  meta: {
    fontSize: 10,
    fontWeight: "500",
  },
  body: {
    gap: 8,
  },
});
