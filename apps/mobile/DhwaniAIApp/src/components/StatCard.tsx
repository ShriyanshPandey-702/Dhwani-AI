import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "../utils/theme";

interface Props {
  value: string | number;
  label: string;
  tone?: "neutral" | "good" | "warn" | "bad";
}

/** One tile in the Home screen today-activity grid. */
export const StatCard: React.FC<Props> = ({ value, label, tone = "neutral" }) => {
  const { colors, radius, isDark } = useTheme();

  const toneColors = {
    neutral: colors.textPrimary,
    good: colors.success,
    warn: colors.warning,
    bad: colors.danger,
  };

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderColor: colors.border,
          borderRadius: radius.md,
          shadowColor: colors.cardShadow,
        },
      ]}
    >
      <Text style={[styles.value, { color: toneColors[tone] }]}>{value}</Text>
      <Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 14,
    paddingHorizontal: 8,
    alignItems: "center",
    gap: 3,
    marginHorizontal: 4,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 1,
  },
  value: {
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.5,
  },
  label: {
    fontSize: 10,
    letterSpacing: 0.8,
    textTransform: "uppercase",
    fontWeight: "600",
  },
});
