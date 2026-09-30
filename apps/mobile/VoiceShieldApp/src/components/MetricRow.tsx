import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "../utils/theme";

interface Props {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warn" | "bad" | "muted";
  fraction?: number | null;
  /** Show value as a pill badge instead of plain text */
  pill?: boolean;
}

export const MetricRow: React.FC<Props> = ({
  label,
  value,
  tone = "neutral",
  fraction = null,
  pill = false,
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
        <Text style={[styles.label, { color: colors.textSecondary }]}>
          {label}
        </Text>

        {pill ? (
          <View
            style={[
              styles.pillBadge,
              {
                backgroundColor: `${activeColor}18`,
                borderColor: `${activeColor}40`,
              },
            ]}
          >
            <Text style={[styles.pillText, { color: activeColor }]}>
              {value}
            </Text>
          </View>
        ) : (
          <Text style={[styles.value, { color: activeColor }]}>{value}</Text>
        )}
      </View>

      {fraction !== null && (
        <View
          style={[
            styles.track,
            {
              backgroundColor: isDark
                ? colors.surfaceElevated
                : colors.surfaceElevated,
            },
          ]}
        >
          <View
            style={[
              styles.fill,
              {
                width: `${Math.round(
                  Math.min(1, Math.max(0, fraction)) * 100
                )}%`,
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
  wrapper: { gap: 5, marginVertical: 1 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  label: { fontSize: 13, flex: 1, fontWeight: "500" },
  value: { fontSize: 13, fontWeight: "700", letterSpacing: 0.3 },
  pillBadge: {
    paddingHorizontal: 9,
    paddingVertical: 3,
    borderRadius: 99,
    borderWidth: 1,
    alignSelf: "flex-end",
  },
  pillText: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.4,
  },
  track: {
    height: 5,
    borderRadius: 3,
    overflow: "hidden",
    marginTop: 3,
  },
  fill: { height: 5, borderRadius: 3 },
});
