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
import { BackgroundWave } from "../components/BackgroundWave";
import { MicIcon } from "../components/Icons";

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
  const [, setError] = useState<string | null>(null);

  // Microphone wave pulse animation
  const waveAnim = useRef(new Animated.Value(1)).current;
  const waveOpacity = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.parallel([
        Animated.sequence([
          Animated.timing(waveAnim, { toValue: 1.25, duration: 1100, useNativeDriver: true }),
          Animated.timing(waveAnim, { toValue: 1, duration: 1100, useNativeDriver: true }),
        ]),
        Animated.sequence([
          Animated.timing(waveOpacity, { toValue: 0.1, duration: 1100, useNativeDriver: true }),
          Animated.timing(waveOpacity, { toValue: 0.4, duration: 1100, useNativeDriver: true }),
        ]),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [waveAnim, waveOpacity]);

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
      <BackgroundWave />

      {/* Top Header */}
      <View
        style={[
          styles.topBar,
          {
            paddingTop: insets.top + 8,
            borderBottomColor: colors.border,
            backgroundColor: isDark ? colors.surface : colors.surface,
          },
        ]}
      >
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backBtn}
          accessibilityRole="button"
          accessibilityLabel="Back"
        >
          <Text style={[styles.backText, { color: colors.textSecondary }]}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={[styles.topBarTitle, { color: colors.textPrimary }]}>
          Live Challenge
        </Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: 16,
            paddingBottom: Math.max(insets.bottom, 24) + 16,
          },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Header / Intro (design.md Section 15) */}
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Verifying caller with a live challenge
          </Text>
          <Text style={[styles.explanation, { color: colors.textSecondary }]}>
            Asking an unexpected question helps confirm whether this is a real person or a voice clone.
          </Text>
        </View>

        {/* Hero: Microphone / Flowing Wave Visual (design.md Section 15) */}
        <View style={styles.micVisualWrap}>
          {/* Outermost wave */}
          <Animated.View
            style={[
              styles.waveCircleOuter,
              {
                borderColor: colors.accent,
                backgroundColor: `${colors.accent}08`,
                opacity: waveOpacity,
                transform: [{ scale: waveAnim }],
              },
            ]}
          />
          {/* Inner wave */}
          <View
            style={[
              styles.waveCircleInner,
              {
                borderColor: `${colors.accent}40`,
                backgroundColor: `${colors.accent}14`,
              },
            ]}
          />
          {/* Central Mic Icon Button */}
          <View
            style={[
              styles.micInner,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surface,
                borderColor: colors.accent,
                shadowColor: colors.accent,
              },
            ]}
          >
            <MicIcon size={34} color={colors.accent} strokeWidth={2.5} />
          </View>
        </View>

        {/* Listening state indicator */}
        <View
          style={[
            styles.listeningBadge,
            {
              backgroundColor: `${colors.accent}14`,
              borderColor: `${colors.accent}33`,
              borderRadius: radius.full,
            },
          ]}
        >
          <View style={[styles.listeningDot, { backgroundColor: colors.accent }]} />
          <Text style={[styles.listeningText, { color: colors.accent }]}>
            Listening for caller response…
          </Text>
        </View>

        {/* Challenge Prompt Card (design.md Section 15) */}
        {isLoading ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator color={colors.accent} size="large" />
            <Text style={[styles.loadingText, { color: colors.textSecondary }]}>
              Generating contextual challenge question…
            </Text>
          </View>
        ) : challenge ? (
          <View
            style={[
              styles.promptCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.accent,
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
              },
            ]}
          >
            <View style={styles.promptHeaderRow}>
              <Text style={[styles.promptLabel, { color: colors.accent }]}>
                QUESTION BEING ASKED
              </Text>
              <View
                style={[
                  styles.challengeChip,
                  {
                    backgroundColor: `${colors.accent}18`,
                    borderColor: `${colors.accent}44`,
                  },
                ]}
              >
                <Text style={[styles.challengeChipText, { color: colors.accent }]}>
                  ACTIVE
                </Text>
              </View>
            </View>

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
                borderRadius: radius.xl,
              },
            ]}
          >
            <Text style={[styles.promptLabel, { color: colors.textSecondary }]}>
              RECOMMENDED VERIFICATION PROMPT
            </Text>
            <Text style={[styles.promptText, { color: colors.textPrimary }]}>
              "For security, please verify the agreed project code or confirm the shared reference phrase."
            </Text>
          </View>
        )}

        {/* Action Controls (design.md Section 15) */}
        <View style={styles.actionColumn}>
          <TouchableOpacity
            style={[
              styles.actionBtn,
              {
                backgroundColor: colors.accent,
                borderRadius: radius.lg,
              },
            ]}
            onPress={() => submitOutcome("passed")}
            accessibilityRole="button"
            accessibilityLabel="Continue Monitoring"
          >
            <Text style={styles.actionBtnText}>✓ Continue Monitoring</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.holdBtn,
              {
                backgroundColor: `${colors.danger}18`,
                borderColor: `${colors.danger}55`,
                borderRadius: radius.lg,
              },
            ]}
            onPress={() => submitOutcome("failed")}
            accessibilityRole="button"
            accessibilityLabel="Hold This Request"
          >
            <Text style={[styles.holdBtnText, { color: colors.danger }]}>
              ⚠️ Hold / Flag This Call
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.altBtn,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderColor: colors.border,
                borderRadius: radius.lg,
              },
            ]}
            onPress={() => navigation.navigate("Verification", { sessionId })}
            accessibilityRole="button"
            accessibilityLabel="Alternative Verification"
          >
            <Text style={[styles.altBtnText, { color: colors.textSecondary }]}>
              🔐 Verify Through Trusted Channel →
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.cancelBtn,
              {
                borderColor: colors.border,
                borderRadius: radius.lg,
              },
            ]}
            onPress={() => navigation.goBack()}
            accessibilityRole="button"
            accessibilityLabel="Cancel Challenge"
          >
            <Text style={[styles.cancelBtnText, { color: colors.textMuted }]}>
              Cancel Challenge
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
  topBar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
  },
  backBtn: {
    paddingVertical: 4,
    paddingRight: 10,
  },
  backText: {
    fontSize: 16,
    fontWeight: "600",
  },
  topBarTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  scroll: {
    paddingHorizontal: 20,
    gap: 16,
  },
  header: {
    gap: 6,
    marginTop: 4,
  },
  title: {
    fontSize: 22,
    fontWeight: "800",
    letterSpacing: -0.3,
    lineHeight: 28,
  },
  explanation: {
    fontSize: 13,
    lineHeight: 19,
  },
  micVisualWrap: {
    alignItems: "center",
    justifyContent: "center",
    height: 140,
    marginVertical: 4,
  },
  waveCircleOuter: {
    position: "absolute",
    width: 130,
    height: 130,
    borderRadius: 65,
    borderWidth: 2,
  },
  waveCircleInner: {
    position: "absolute",
    width: 100,
    height: 100,
    borderRadius: 50,
    borderWidth: 1.5,
  },
  micInner: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
    elevation: 6,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  listeningBadge: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 7,
    paddingHorizontal: 16,
    alignSelf: "center",
    borderWidth: 1,
  },
  listeningDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  listeningText: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.2,
  },
  loadingWrap: {
    paddingVertical: 24,
    alignItems: "center",
    gap: 10,
  },
  loadingText: {
    fontSize: 12,
    fontWeight: "500",
  },
  promptCard: {
    borderWidth: 1.5,
    padding: 18,
    gap: 10,
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  promptHeaderRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  promptLabel: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.8,
  },
  challengeChip: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 99,
    borderWidth: 1,
  },
  challengeChipText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  promptText: {
    fontSize: 17,
    fontWeight: "700",
    lineHeight: 24,
    letterSpacing: -0.2,
  },
  actionColumn: {
    gap: 10,
    marginTop: 6,
  },
  actionBtn: {
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    elevation: 2,
  },
  actionBtnText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700",
  },
  holdBtn: {
    borderWidth: 1,
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  holdBtnText: {
    fontSize: 14,
    fontWeight: "700",
  },
  altBtn: {
    borderWidth: 1,
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  altBtnText: {
    fontSize: 13,
    fontWeight: "600",
  },
  cancelBtn: {
    borderWidth: 1,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  cancelBtnText: {
    fontSize: 13,
    fontWeight: "600",
  },
});
