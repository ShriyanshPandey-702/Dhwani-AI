import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { useTheme } from "../utils/theme";
import { ThemeMode } from "../store/themeStore";

interface ThemeToggleProps {
  compact?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ compact = false }) => {
  const { mode, setMode, colors, radius, isDark } = useTheme();

  const options: { mode: ThemeMode; label: string; icon: string }[] = [
    { mode: "light", label: "Light", icon: "☀" },
    { mode: "dark", label: "Dark", icon: "☾" },
    { mode: "system", label: "System", icon: "⚙" },
  ];

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
          borderColor: colors.border,
          borderRadius: radius.md,
        },
      ]}
    >
      {options.map((opt) => {
        const isSelected = mode === opt.mode;
        return (
          <TouchableOpacity
            key={opt.mode}
            activeOpacity={0.7}
            onPress={() => setMode(opt.mode)}
            style={[
              styles.segment,
              {
                borderRadius: radius.sm,
                backgroundColor: isSelected ? colors.surface : "transparent",
                borderColor: isSelected ? colors.border : "transparent",
              },
            ]}
            accessibilityRole="radio"
            accessibilityState={{ selected: isSelected }}
            accessibilityLabel={`${opt.label} theme`}
          >
            <Text style={{ fontSize: 13, marginRight: 4 }}>{opt.icon}</Text>
            {!compact && (
              <Text
                style={[
                  styles.label,
                  {
                    color: isSelected ? colors.textPrimary : colors.textSecondary,
                    fontWeight: isSelected ? "700" : "500",
                  },
                ]}
              >
                {opt.label}
              </Text>
            )}
          </TouchableOpacity>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    padding: 3,
    borderWidth: 1,
    alignSelf: "stretch",
  },
  segment: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 7,
    borderWidth: 1,
  },
  label: {
    fontSize: 12,
  },
});
