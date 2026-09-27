import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "../utils/theme";
import { RiskState } from "../types";

interface Props {
  state: RiskState | string | undefined | null;
  size?: "sm" | "md" | "lg";
  showDot?: boolean;
  variant?: "pill" | "subtle" | "outline";
}

const normalizeState = (raw: string | undefined | null): RiskState => {
  const s = raw?.toLowerCase();
  if (s === "low") return "low";
  if (s === "suspicious") return "suspicious";
  if (s === "high") return "high";
  if (s === "critical") return "critical";
  return "insufficient_evidence";
};

const DISPLAY_LABELS: Record<RiskState, string> = {
  insufficient_evidence: "INSUFFICIENT EVIDENCE",
  low: "LOW RISK",
  suspicious: "SUSPICIOUS",
  high: "HIGH RISK",
  critical: "CRITICAL",
};

export const RiskBadge: React.FC<Props> = ({
  state,
  size = "md",
  showDot = true,
  variant = "pill",
}) => {
  const { riskColors, radius } = useTheme();
  const normalized = normalizeState(state);
  const color = riskColors[normalized];
  const label = DISPLAY_LABELS[normalized];

  const sizeMetrics = {
    sm: { px: 8, py: 3, font: 10, dot: 5 },
    md: { px: 10, py: 4, font: 11, dot: 6 },
    lg: { px: 14, py: 6, font: 13, dot: 7 },
  }[size];

  const bgColor =
    variant === "outline"
      ? "transparent"
      : `${color}18`;

  return (
    <View
      style={[
        styles.badge,
        {
          paddingHorizontal: sizeMetrics.px,
          paddingVertical: sizeMetrics.py,
          borderRadius: radius.full,
          borderColor: `${color}44`,
          backgroundColor: bgColor,
        },
      ]}
      accessibilityRole="text"
      accessibilityLabel={`Risk state: ${label}`}
    >
      {showDot && (
        <View
          style={[
            styles.dot,
            {
              width: sizeMetrics.dot,
              height: sizeMetrics.dot,
              borderRadius: sizeMetrics.dot / 2,
              backgroundColor: color,
            },
          ]}
        />
      )}
      <Text
        style={[
          styles.text,
          {
            color,
            fontSize: sizeMetrics.font,
          },
        ]}
      >
        {label}
      </Text>
    </View>
  );
};

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    alignSelf: "flex-start",
  },
  dot: {
    marginRight: 5,
  },
  text: {
    fontWeight: "700",
    letterSpacing: 0.6,
  },
});
