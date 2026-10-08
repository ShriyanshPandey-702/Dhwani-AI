import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { useTheme } from "../utils/theme";

interface Props {
  title: string;
  meta?: string;
  children: React.ReactNode;
  accent?: string;
  /** Icon shown before the title */
  icon?: React.ReactNode;
}

/**
 * Glassmorphic panel card — shared chrome for all evidence panels.
 * Dark mode: subtle surface elevation + tinted border.
 * Accent: coloured left-stripe + border tint when a threat is active.
 */
export const PanelCard: React.FC<Props> = ({ title, meta, children, accent, icon }) => {
  const { colors, radius, isDark } = useTheme();

  const borderColor = accent ? `${accent}50` : colors.border;
  const stripeColor = accent ?? colors.accent;

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderColor,
          borderRadius: radius.lg,
        },
      ]}
    >
      {/* Coloured left accent stripe */}
      <View
        style={[
          styles.stripe,
          {
            backgroundColor: stripeColor,
            borderTopLeftRadius: radius.lg,
            borderBottomLeftRadius: radius.lg,
          },
        ]}
      />

      <View style={styles.inner}>
        {/* Header row */}
        <View style={styles.header}>
          <View style={styles.titleRow}>
            {typeof icon === "string" ? (
              <Text style={styles.icon}>{icon}</Text>
            ) : (
              icon
            )}
            <Text
              style={[
                styles.title,
                { color: accent ? accent : colors.textSecondary },
              ]}
            >
              {title}
            </Text>
          </View>
          {!!meta && (
            <View
              style={[
                styles.metaBadge,
                {
                  backgroundColor: accent
                    ? `${accent}20`
                    : `${colors.accent}18`,
                  borderColor: accent ? `${accent}40` : `${colors.accent}30`,
                },
              ]}
            >
              <Text
                style={[
                  styles.meta,
                  { color: accent ? accent : colors.accent },
                ]}
              >
                {meta}
              </Text>
            </View>
          )}
        </View>

        {/* Body */}
        <View style={styles.body}>{children}</View>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    marginVertical: 5,
    flexDirection: "row",
    overflow: "hidden",
    // shadow
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 6,
    elevation: 2,
  },
  stripe: {
    width: 3,
    alignSelf: "stretch",
  },
  inner: {
    flex: 1,
    padding: 14,
    gap: 10,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    flex: 1,
  },
  icon: {
    fontSize: 13,
  },
  title: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 1.4,
    textTransform: "uppercase",
    flexShrink: 1,
  },
  metaBadge: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 99,
    borderWidth: 1,
    marginLeft: 8,
  },
  meta: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  body: {
    gap: 6,
  },
});
