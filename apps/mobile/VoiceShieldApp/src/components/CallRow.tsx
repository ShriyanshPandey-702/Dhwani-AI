import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { useTheme } from "../utils/theme";
import { RiskBadge } from "./RiskBadge";
import { RiskState } from "../types";
import { PhoneIcon, MicIcon, FolderIcon } from "./Icons";

export interface CallRowProps {
  callerName?: string | null;
  callerMasked: string;
  timestamp: string | number;
  riskState: RiskState | string;
  riskScore?: number | null;
  decision?: string;
  category?: string;
  source?: "screened" | "incident" | "file" | "mic" | string;
  onPress: () => void;
}

const formatDisplayTime = (val: string | number) => {
  const d = typeof val === "number" ? new Date(val) : new Date(val);
  if (isNaN(d.getTime())) return "--:--";
  const hours = d.getHours();
  const minutes = d.getMinutes();
  const ampm = hours >= 12 ? "PM" : "AM";
  const h12 = hours % 12 || 12;
  const pad = (n: number) => (n < 10 ? `0${n}` : `${n}`);
  return `${h12}:${pad(minutes)} ${ampm}`;
};

export const CallRow: React.FC<CallRowProps> = ({
  callerName,
  callerMasked,
  timestamp,
  riskState,
  riskScore,
  decision,
  category = "Incoming SIM Call — Metadata Only",
  source,
  onPress,
}) => {
  const { colors, radius, isDark } = useTheme();

  const isFile = source === "file" || category.toLowerCase().includes("file");
  const isMic = source === "mic" || category.toLowerCase().includes("mic");

  return (
    <TouchableOpacity
      activeOpacity={0.7}
      onPress={onPress}
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderColor: colors.border,
          borderRadius: radius.md,
        },
      ]}
      accessibilityRole="button"
      accessibilityLabel={`Activity ${callerName || callerMasked}, risk ${riskState}`}
    >
      {/* Left Icon */}
      <View
        style={[
          styles.iconBox,
          {
            backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
            borderRadius: radius.sm,
          },
        ]}
      >
        {isFile ? (
          <FolderIcon size={16} color={colors.accent} />
        ) : isMic ? (
          <MicIcon size={16} color={colors.accent} />
        ) : (
          <PhoneIcon size={16} color={colors.accent} />
        )}
      </View>

      {/* Center Details */}
      <View style={styles.centerCol}>
        <Text
          style={[styles.primaryText, { color: colors.textPrimary }]}
          numberOfLines={1}
        >
          {callerName ? callerName : callerMasked}
        </Text>
        <Text
          style={[styles.subText, { color: colors.textSecondary }]}
          numberOfLines={1}
        >
          {callerName ? `${callerMasked} · ${category}` : category}
          {decision ? ` · ${decision.toUpperCase()}` : ""}
        </Text>
      </View>

      {/* Right Column: Badge & Time */}
      <View style={styles.rightCol}>
        <RiskBadge state={riskState} score={riskScore} size="sm" />
        <Text style={[styles.timeText, { color: colors.textMuted }]}>
          {formatDisplayTime(timestamp)}
        </Text>
      </View>
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    padding: 12,
    marginVertical: 4,
    borderWidth: 1,
  },
  iconBox: {
    width: 36,
    height: 36,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  centerCol: {
    flex: 1,
    justifyContent: "center",
    marginRight: 8,
  },
  primaryText: {
    fontSize: 14,
    fontWeight: "600",
    letterSpacing: 0.2,
  },
  subText: {
    fontSize: 11,
    marginTop: 2,
  },
  rightCol: {
    alignItems: "flex-end",
    justifyContent: "center",
    gap: 4,
  },
  timeText: {
    fontSize: 10,
    fontWeight: "500",
  },
});
