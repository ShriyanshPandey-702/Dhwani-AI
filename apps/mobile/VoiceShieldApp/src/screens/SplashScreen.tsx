import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated } from 'react-native';
import { colors } from '../utils/theme';

export const SplashScreen: React.FC<{ onFinish: () => void }> = ({ onFinish }) => {
  const opacity = useRef(new Animated.Value(0)).current;
  const scale = useRef(new Animated.Value(0.8)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.spring(scale, { toValue: 1, friction: 5, useNativeDriver: true }),
    ]).start(() => {
      setTimeout(onFinish, 1200);
    });
  }, []);

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.logoWrap, { opacity, transform: [{ scale }] }]}>
        <View style={styles.shieldOuter}>
          <View style={styles.shieldInner}>
            <Text style={styles.shieldIcon}>🛡</Text>
          </View>
        </View>
        <Text style={styles.appName}>VoiceShield</Text>
        <Text style={styles.tagline}>DETECT · SCORE · PROTECT</Text>
      </Animated.View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center' },
  logoWrap: { alignItems: 'center', gap: 20 },
  shieldOuter: {
    width: 100, height: 100, borderRadius: 28,
    backgroundColor: colors.brandDim,
    borderWidth: 1.5, borderColor: colors.brand,
    alignItems: 'center', justifyContent: 'center',
  },
  shieldInner: {
    width: 72, height: 72, borderRadius: 18,
    backgroundColor: `${colors.brand}22`,
    alignItems: 'center', justifyContent: 'center',
  },
  shieldIcon: { fontSize: 36 },
  appName: { fontSize: 32, fontWeight: '800', color: colors.textPrimary, letterSpacing: -0.5 },
  tagline: { fontSize: 11, fontWeight: '600', color: colors.textMuted, letterSpacing: 3 },
});
