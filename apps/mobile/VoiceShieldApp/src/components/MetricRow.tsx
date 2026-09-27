import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "../utils/theme";

interface Props {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warn" | "bad" | "muted";
  fraction?: number | null;
}

export const MetricRow: React.FC<Props> = ({
  label,
  value,
  tone = "neutral",
  fraction = null,
}) => {
  const { colors, isDark } = useTheme();

  const toneColors = {
    neutral: colors.textPrimary,
    good: colors.success,
    warn: colors.warning,
    bad: colors.danger,
    muted: colors.textMuted,
  };

  const activeColor = toneColors[tone];

  return (
    <View style={styles.wrapper}>
      <View style={styles.row}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>{label}</Text>
        <Text style={[styles.value, { color: activeColor }]}>{value}</Text>
      </View>
      {fraction !== null && (
        <View
          style={[
            styles.track,
            { backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated },
          ]}
        >
          <View
            style={[
              styles.fill,
              {
                width: `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`,
                backgroundColor: activeColor,
              },
            ]}
          />
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: { gap: 4, marginVertical: 2 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  label: { fontSize: 13, flex: 1 },
  value: { fontSize: 13, fontWeight: "700", letterSpacing: 0.3 },
  track: {
    height: 4,
    borderRadius: 2,
    overflow: "hidden",
    marginTop: 2,
  },
  fill: { height: 4, borderRadius: 2 },
});
