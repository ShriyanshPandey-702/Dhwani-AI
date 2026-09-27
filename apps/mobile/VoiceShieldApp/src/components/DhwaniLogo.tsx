import React from "react";
import { View, Image, Text, StyleSheet, ImageStyle, ViewStyle } from "react-native";
import { useTheme } from "../utils/theme";

interface DhwaniLogoProps {
  size?: "sm" | "md" | "lg" | "hero" | number;
  showText?: boolean;
  tagline?: boolean;
  style?: ViewStyle;
}

const SIZE_MAP = {
  sm: 26,
  md: 40,
  lg: 64,
  hero: 96,
};

export const DhwaniLogo: React.FC<DhwaniLogoProps> = ({
  size = "md",
  showText = false,
  tagline = false,
  style,
}) => {
  const { colors, typography } = useTheme();
  const dimension = typeof size === "number" ? size : SIZE_MAP[size];

  return (
    <View style={[styles.container, style]}>
      <Image
        source={require("../assets/logo.png")}
        style={{
          width: dimension,
          height: dimension,
          resizeMode: "contain",
        }}
        accessibilityRole="image"
        accessibilityLabel="Dhwani AI Logo"
      />
      {showText && (
        <View style={styles.textContainer}>
          <Text
            style={[
              typography.h2,
              { color: colors.textPrimary, letterSpacing: 0.5, fontWeight: "800" },
            ]}
          >
            Dhwani AI
          </Text>
          {tagline && (
            <Text
              style={[
                typography.caption,
                { color: colors.textSecondary, letterSpacing: 0.4 },
              ]}
            >
              Secure Calls. Trusted People.
            </Text>
          )}
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
  },
  textContainer: {
    marginLeft: 10,
    justifyContent: "center",
  },
});
