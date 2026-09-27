import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Animated,
} from "react-native";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import client from "../services/api/client";
import { ChallengeData } from "../types";
import { RootStackParamList } from "../navigation/AppNavigator";

type Nav = NativeStackNavigationProp<RootStackParamList>;
type Route = RouteProp<RootStackParamList, "Challenge">;

export const ChallengeScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const route = useRoute<Route>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const { sessionId } = route.params;
  const [challenge, setChallenge] = useState<ChallengeData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [responded, setResponded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Microphone wave pulse animation
  const waveAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(waveAnim, { toValue: 1.15, duration: 1000, useNativeDriver: true }),
        Animated.timing(waveAnim, { toValue: 1, duration: 1000, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [waveAnim]);

  useEffect(() => {
    fetchChallenge();
  }, []);

  const fetchChallenge = async () => {
    try {
      const { data } = await client.post<ChallengeData>(`/challenge/${sessionId}`);
      setChallenge(data);
    } catch (e) {
      setError("Could not issue an automated challenge for this session.");
    } finally {
      setIsLoading(false);
    }
  };

  const submitOutcome = async (outcome: "passed" | "failed") => {
    if (!challenge || responded) return;
    setResponded(true);
    try {
      await client.post(`/challenge/${sessionId}/${challenge.id}/result`, { outcome });
    } catch {
      // safe fallback
    }
    navigation.goBack();
  };

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
        },
      ]}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 16,
            paddingBottom: Math.max(insets.bottom, 24) + 16,
          },
        ]}
      >
        {/* Header (design.md Section 24) */}
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Live Challenge
          </Text>
          <Text style={[styles.subtitle, { color: colors.accent }]}>
            Verifying the caller with a live challenge
          </Text>
          <Text style={[styles.explanation, { color: colors.textSecondary }]}>
            Asking an unexpected question helps confirm whether this is a real person or a voice clone.
          </Text>
        </View>

        {/* Microphone / Wave visual */}
        <View style={styles.micVisualWrap}>
          <Animated.View
            style={[
              styles.waveCircle,
              {
                borderColor: `${colors.accent}44`,
                backgroundColor: `${colors.accent}12`,
                transform: [{ scale: waveAnim }],
              },
            ]}
          />
          <View
            style={[
              styles.micInner,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
              },
            ]}
          >
            <Text style={{ fontSize: 32 }}>🎙</Text>
          </View>
        </View>

        {/* Listening state indicator */}
        <View style={styles.listeningBadge}>
          <View style={[styles.listeningDot, { backgroundColor: colors.accent }]} />
          <Text style={[styles.listeningText, { color: colors.accent }]}>
            Listening for response…
          </Text>
        </View>

        {/* Challenge Prompt Card */}
        {isLoading ? (
          <ActivityIndicator color={colors.accent} size="large" style={{ marginVertical: 20 }} />
        ) : challenge ? (
          <View
            style={[
              styles.promptCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
                shadowColor: colors.cardShadow,
              },
            ]}
          >
            <Text style={[styles.promptLabel, { color: colors.textSecondary }]}>
              QUESTION BEING ASKED...
            </Text>
            <Text style={[styles.promptText, { color: colors.textPrimary }]}>
              "{challenge.challenge_text}"
            </Text>
          </View>
        ) : (
          <View
            style={[
              styles.promptCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
          >
            <Text style={[styles.promptLabel, { color: colors.textSecondary }]}>
              RECOMMENDED VERIFICATION PROMPT
            </Text>
            <Text style={[styles.promptText, { color: colors.textPrimary }]}>
              "For security, please tell me the last 4 digits of the project code or verify our agreed pass-phrase."
            </Text>
          </View>
        )}

        {/* Action Controls */}
        <View style={styles.actionColumn}>
          <TouchableOpacity
            style={[
              styles.actionBtn,
              {
                backgroundColor: colors.accent,
                borderRadius: radius.md,
              },
            ]}
            onPress={() => submitOutcome("passed")}
            accessibilityRole="button"
            accessibilityLabel="Continue Monitoring"
          >
            <Text style={styles.actionBtnText}>Continue Monitoring</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.holdBtn,
              {
                backgroundColor: `${colors.danger}18`,
                borderColor: `${colors.danger}55`,
                borderRadius: radius.md,
              },
            ]}
            onPress={() => submitOutcome("failed")}
            accessibilityRole="button"
            accessibilityLabel="Hold This Request"
          >
            <Text style={[styles.holdBtnText, { color: colors.danger }]}>
              Hold This Request
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.altBtn,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
            onPress={() => navigation.navigate("Verification", { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Alternative Verification"
          >
            <Text style={[styles.altBtnText, { color: colors.textSecondary }]}>
              Verify Through Trusted Channel →
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    paddingHorizontal: 20,
    gap: 16,
  },
  header: {
    gap: 6,
  },
  title: {
    fontSize: 24,
    fontWeight: "800",
    letterSpacing: -0.3,
  },
  subtitle: {
    fontSize: 14,
    fontWeight: "600",
  },
  explanation: {
    fontSize: 13,
    lineHeight: 18,
    marginTop: 2,
  },
  micVisualWrap: {
    alignItems: "center",
    justifyContent: "center",
    height: 120,
    marginVertical: 10,
  },
  waveCircle: {
    position: "absolute",
    width: 100,
    height: 100,
    borderRadius: 50,
    borderWidth: 2,
  },
  micInner: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
    elevation: 4,
  },
  listeningBadge: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  listeningDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  listeningText: {
    fontSize: 12,
    fontWeight: "600",
  },
  promptCard: {
    borderWidth: 1,
    padding: 18,
    gap: 8,
  },
  promptLabel: {
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  promptText: {
    fontSize: 16,
    fontWeight: "600",
    lineHeight: 22,
  },
  actionColumn: {
    gap: 10,
    marginTop: 10,
  },
  actionBtn: {
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  actionBtnText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700",
  },
  holdBtn: {
    borderWidth: 1,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  holdBtnText: {
    fontSize: 15,
    fontWeight: "700",
  },
  altBtn: {
    borderWidth: 1,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  altBtnText: {
    fontSize: 13,
    fontWeight: "600",
  },
});
