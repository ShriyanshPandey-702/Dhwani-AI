import React, { useEffect, useRef, useContext } from 'react';
import { View, Text, StyleSheet, Animated, Image } from 'react-native';
import { SafeAreaInsetsContext } from 'react-native-safe-area-context';
import { useTheme } from '../utils/theme';

export const SplashScreen: React.FC<{ onFinish: () => void }> = ({ onFinish }) => {
  const { colors, isDark } = useTheme();
  const insets = useContext(SafeAreaInsetsContext);

  const topInset = insets?.top ?? 20;
  const bottomInset = insets ? Math.max(insets.bottom, 24) : 24;

  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.88)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 600, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 6, tension: 40, useNativeDriver: true }),
    ]).start(() => {
      setTimeout(onFinish, 1400);
    });
  }, [opacity, scale, onFinish]);

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
      <View style={styles.centerSection}>
        <Animated.View style={[styles.logoWrap, { opacity, transform: [{ scale }] }]}>
          <Image
            source={require('../assets/logo.png')}
            style={styles.logoImage}
            resizeMode="contain"
            accessibilityRole="image"
            accessibilityLabel="Dhwani AI Logo"
          />
          <Text style={[styles.appName, { color: colors.textPrimary }]}>
            Dhwani AI
          </Text>
          <Text style={[styles.subtitle, { color: colors.accent }]}>
            Real-Time Voice Protection
          </Text>
          <Text style={[styles.tagline, { color: colors.textSecondary }]}>
            A safer tomorrow, for every conversation.
          </Text>
        </Animated.View>
      </View>

      <View style={styles.footerSection}>
        <Text style={[styles.footerText, { color: colors.textMuted }]}>
          Built for a Safer India
        </Text>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  centerSection: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoWrap: {
    alignItems: 'center',
    paddingHorizontal: 24,
  },
  logoImage: {
    width: 110,
    height: 110,
    marginBottom: 20,
  },
  appName: {
    fontSize: 34,
    fontWeight: '800',
    letterSpacing: -0.5,
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 15,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  tagline: {
    fontSize: 13,
    fontWeight: '400',
    textAlign: 'center',
    maxWidth: 280,
  },
  footerSection: {
    paddingBottom: 16,
    alignItems: 'center',
  },
  footerText: {
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
});
