import React from "react";
import { View, Text, StyleSheet, ViewStyle, StyleProp, TouchableOpacity } from "react-native";
import { useTheme } from "../utils/theme";

interface EvidenceCardProps {
  title: string;
  subtitle?: string;
  badge?: string;
  badgeColor?: string;
  accentColor?: string;
  children?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
}

export const EvidenceCard: React.FC<EvidenceCardProps> = ({
  title,
  subtitle,
  badge,
  badgeColor,
  accentColor,
  children,
  style,
  onPress,
}) => {
  const { colors, radius, isDark } = useTheme();

  const Container = onPress ? TouchableOpacity : View;

  return (
    <Container
      activeOpacity={onPress ? 0.75 : 1}
      onPress={onPress}
      style={[
        styles.card,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderColor: accentColor ? `${accentColor}55` : colors.border,
          borderRadius: radius.md,
          shadowColor: colors.cardShadow,
        },
        style,
      ]}
    >
      <View style={styles.headerRow}>
        <View style={styles.titleColumn}>
          <Text
            style={[
              styles.title,
              { color: colors.textPrimary },
            ]}
          >
            {title.toUpperCase()}
          </Text>
          {subtitle ? (
            <Text
              style={[
                styles.subtitle,
                { color: colors.textSecondary },
              ]}
            >
              {subtitle}
            </Text>
          ) : null}
        </View>

        {badge ? (
          <View
            style={[
              styles.badgeContainer,
              {
                backgroundColor: badgeColor ? `${badgeColor}18` : `${colors.accent}18`,
                borderColor: badgeColor ? `${badgeColor}44` : `${colors.accent}44`,
                borderRadius: radius.full,
              },
            ]}
          >
            <Text
              style={[
                styles.badgeText,
                { color: badgeColor || colors.accent },
              ]}
            >
              {badge}
            </Text>
          </View>
        ) : null}
      </View>

      {children ? <View style={styles.content}>{children}</View> : null}
    </Container>
  );
};

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    padding: 16,
    marginVertical: 6,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  titleColumn: {
    flex: 1,
  },
  title: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  subtitle: {
    fontSize: 11,
    marginTop: 2,
  },
  badgeContainer: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  content: {
    marginTop: 4,
  },
});
