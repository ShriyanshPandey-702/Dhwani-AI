import React, { useEffect, useRef, useContext } from "react";
import { View, Text, StyleSheet, Animated, Image } from "react-native";
import { SafeAreaInsetsContext } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { BackgroundWave } from "../components/BackgroundWave";

export const SplashScreen: React.FC<{ onFinish: () => void }> = ({ onFinish }) => {
  const { colors, isDark } = useTheme();
  const insets = useContext(SafeAreaInsetsContext);

  const topInset = insets?.top ?? 20;
  const bottomInset = insets ? Math.max(insets.bottom, 24) : 24;

  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.9)).current;
  const glowAnim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 0.8, duration: 1200, useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0.4, duration: 1200, useNativeDriver: true }),
      ])
    ).start();

    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 6, tension: 40, useNativeDriver: true }),
    ]).start(() => {
      setTimeout(onFinish, 1500);
    });
  }, [opacity, scale, glowAnim, onFinish]);

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
          paddingTop: topInset,
          paddingBottom: bottomInset,
        },
      ]}
    >
      <BackgroundWave />

      <View style={styles.centerSection}>
        <Animated.View style={[styles.logoWrap, { opacity, transform: [{ scale }] }]}>
          {/* Logo with ambient glow */}
          <View style={styles.logoContainer}>
            <Animated.View
              style={[
                styles.logoGlow,
                {
                  backgroundColor: isDark ? colors.accent : `${colors.accent}44`,
                  opacity: glowAnim,
                },
              ]}
            />
            <Image
              source={require("../assets/logo.png")}
              style={styles.logoImage}
              resizeMode="contain"
              accessibilityRole="image"
              accessibilityLabel="Dhwani AI Logo"
            />
          </View>

          <Text style={[styles.appName, { color: colors.textPrimary }]}>
            Dhwani AI
          </Text>
          <Text style={[styles.subtitle, { color: colors.accent }]}>
            Real-Time Voice Protection
          </Text>
          <Text style={[styles.tagline, { color: colors.textSecondary }]}>
            Detect. Verify. Prevent.
          </Text>
        </Animated.View>
      </View>

      <View style={styles.footerSection}>
        <Text style={[styles.footerText, { color: colors.textMuted }]}>
          🇮🇳 Built for a Safer India
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "space-between",
  },
  centerSection: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  logoWrap: {
    alignItems: "center",
    paddingHorizontal: 24,
  },
  logoContainer: {
    width: 120,
    height: 120,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 20,
  },
  logoGlow: {
    position: "absolute",
    width: 110,
    height: 110,
    borderRadius: 55,
  },
  logoImage: {
    width: 100,
    height: 100,
  },
  appName: {
    fontSize: 34,
    fontWeight: "800",
    letterSpacing: -0.5,
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.6,
    marginBottom: 6,
    textTransform: "uppercase",
  },
  tagline: {
    fontSize: 14,
    fontWeight: "500",
    textAlign: "center",
    letterSpacing: 0.3,
  },
  footerSection: {
    paddingBottom: 12,
    alignItems: "center",
  },
  footerText: {
    fontSize: 12,
    fontWeight: "600",
    letterSpacing: 0.8,
  },
});
