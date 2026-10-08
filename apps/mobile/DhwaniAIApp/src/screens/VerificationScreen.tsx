import React, { useState, useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
  Animated,
  Alert,
} from "react-native";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import client from "../services/api/client";
import { VerificationData } from "../types";
import { RootStackParamList } from "../navigation/AppNavigator";
import { BackgroundWave } from "../components/BackgroundWave";
import { PhoneIcon } from "../components/Icons";

type Route = RouteProp<RootStackParamList, "Verification">;

export const VerificationScreen: React.FC = () => {
  const navigation = useNavigation();
  const route = useRoute<Route>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const { sessionId } = route.params;
  const [verification, setVerification] = useState<VerificationData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [resolving, setResolving] = useState(false);
  const [result, setResult] = useState<"approved" | "rejected" | null>(null);
  const countdown = useRef(120);
  const [timeLeft, setTimeLeft] = useState(120);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    requestVerification();
  }, []);

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.05, duration: 800, useNativeDriver: true }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
      ])
    ).start();

    const timer = setInterval(() => {
      countdown.current -= 1;
      setTimeLeft(countdown.current);
      if (countdown.current <= 0) {
        clearInterval(timer);
        setResult("rejected");
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [pulseAnim]);

  const requestVerification = async (method: string = "trusted_device") => {
    try {
      const { data } = await client.post<VerificationData>(`/verification/${sessionId}/request`, { method });
      setVerification(data);
      countdown.current = 120;
      setTimeLeft(120);
    } catch (e: any) {
      Alert.alert("Verification Error", e?.response?.data?.detail || "Could not request verification from server.");
    } finally {
      setIsLoading(false);
    }
  };

  const resolve = async (action: "approve" | "reject") => {
    if (!verification) {
      Alert.alert("Verification Error", "No active verification nonce found for this session.");
      return;
    }
    setResolving(true);
    try {
      await client.post(`/verification/${sessionId}/${action}`, { nonce: verification.nonce });
      setResult(action === "approve" ? "approved" : "rejected");
    } catch (e: any) {
      Alert.alert("Verification Error", e?.response?.data?.detail || "Could not complete verification on backend.");
    } finally {
      setResolving(false);
    }
  };

  const handleCallBack = () => {
    Alert.alert(
      "Call Back",
      "Request out-of-band phone callback on verified line?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Confirm",
          onPress: () => requestVerification("callback"),
        },
      ]
    );
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

      {/* Header */}
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
          Independent Verification
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
        <View style={styles.header}>
          <Text style={[styles.title, { color: colors.textPrimary }]}>
            Verify Through Trusted Channel
          </Text>
          <Text style={[styles.explanation, { color: colors.textSecondary }]}>
            This is a high-risk request. We recommend confirming through an independent channel.
          </Text>
        </View>

        {result ? (
          <View
            style={[
              styles.resultCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: result === "approved" ? colors.success : colors.danger,
                borderRadius: radius.xl,
                shadowColor: isDark ? "#000000" : colors.cardShadow,
              },
            ]}
          >
            <Text style={{ fontSize: 48, marginBottom: 8 }}>
              {result === "approved" ? "✅" : "❌"}
            </Text>
            <Text
              style={[
                styles.resultTitle,
                { color: result === "approved" ? colors.success : colors.danger },
              ]}
            >
              {result === "approved" ? "Verification Approved" : "Verification Rejected / Timed Out"}
            </Text>
            <Text style={[styles.resultSubtitle, { color: colors.textSecondary }]}>
              {result === "approved"
                ? "The independent check validated caller authenticity."
                : "The request has been held or denied for security."}
            </Text>
            <TouchableOpacity
              style={[styles.doneBtn, { backgroundColor: colors.accent, borderRadius: radius.md }]}
              onPress={() => navigation.goBack()}
            >
              <Text style={styles.doneBtnText}>Return to Live Session</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {/* 3 Trusted Channel Actions */}
            <View style={styles.channelsSection}>
              <Text style={[styles.channelsHeader, { color: colors.textSecondary }]}>
                INDEPENDENT CHANNELS
              </Text>

              {/* 1. Call Back */}
              <TouchableOpacity
                style={[
                  styles.channelCard,
                  {
                    backgroundColor: isDark ? colors.surface : colors.surface,
                    borderColor: colors.border,
                    borderRadius: radius.lg,
                  },
                ]}
                onPress={handleCallBack}
                accessibilityRole="button"
                accessibilityLabel="Call Back"
              >
                <View style={styles.channelIconBox}>
                  <PhoneIcon size={20} color={colors.accent} />
                </View>
                <View style={styles.channelTextBox}>
                  <Text style={[styles.channelTitle, { color: colors.textPrimary }]}>
                    Call Back
                  </Text>
                  <Text style={[styles.channelDesc, { color: colors.textSecondary }]}>
                    Trigger out-of-band carrier callback verification
                  </Text>
                </View>
                <Text style={[styles.channelArrow, { color: colors.textMuted }]}>›</Text>
              </TouchableOpacity>

              {/* 2. Send Verification Link (Unconfigured Gateway) */}
              <View
                style={[
                  styles.channelCard,
                  {
                    backgroundColor: isDark ? colors.surface : colors.surface,
                    borderColor: colors.border,
                    borderRadius: radius.lg,
                    opacity: 0.55,
                  },
                ]}
              >
                <View style={styles.channelIconBox}>
                  <Text style={{ fontSize: 20 }}>🔗</Text>
                </View>
                <View style={styles.channelTextBox}>
                  <Text style={[styles.channelTitle, { color: colors.textMuted }]}>
                    Send Verification Link (Gateway Unavailable)
                  </Text>
                  <Text style={[styles.channelDesc, { color: colors.textMuted }]}>
                    SMS/Email delivery gateway not configured on server
                  </Text>
                </View>
                <Text style={[styles.channelArrow, { color: colors.textMuted }]}>—</Text>
              </View>

              {/* 3. Notify Trusted Contact (Unconfigured Gateway) */}
              <View
                style={[
                  styles.channelCard,
                  {
                    backgroundColor: isDark ? colors.surface : colors.surface,
                    borderColor: colors.border,
                    borderRadius: radius.lg,
                    opacity: 0.55,
                  },
                ]}
              >
                <View style={styles.channelIconBox}>
                  <Text style={{ fontSize: 20 }}>👥</Text>
                </View>
                <View style={styles.channelTextBox}>
                  <Text style={[styles.channelTitle, { color: colors.textMuted }]}>
                    Notify Trusted Contact (Gateway Unavailable)
                  </Text>
                  <Text style={[styles.channelDesc, { color: colors.textMuted }]}>
                    Enterprise directory webhook not configured on server
                  </Text>
                </View>
                <Text style={[styles.channelArrow, { color: colors.textMuted }]}>—</Text>
              </View>
            </View>

            {/* Cryptographic Device Nonce Approval */}
            <View
              style={[
                styles.deviceVerificationBox,
                {
                  backgroundColor: isDark ? colors.surface : colors.surface,
                  borderColor: colors.border,
                  borderRadius: radius.xl,
                  shadowColor: isDark ? "#000000" : colors.cardShadow,
                },
              ]}
            >
              <View style={styles.timerWrap}>
                <Animated.View
                  style={[
                    styles.timerRing,
                    {
                      borderColor: timeLeft < 30 ? colors.danger : colors.accent,
                      transform: [{ scale: pulseAnim }],
                    },
                  ]}
                >
                  <Text style={[styles.timerValue, { color: colors.textPrimary }]}>
                    {timeLeft}s
                  </Text>
                  <Text style={[styles.timerSub, { color: colors.textMuted }]}>
                    timeout
                  </Text>
                </Animated.View>
              </View>

              {verification ? (
                <View style={styles.nonceContainer}>
                  <Text style={[styles.nonceHeader, { color: colors.textMuted }]}>
                    CHALLENGE NONCE
                  </Text>
                  <Text style={[styles.nonceCode, { color: colors.textPrimary }]}>
                    {verification.nonce}
                  </Text>
                </View>
              ) : null}

              <View style={styles.resolveButtonsRow}>
                <TouchableOpacity
                  style={[
                    styles.approveBtn,
                    { backgroundColor: colors.success, borderRadius: radius.md },
                  ]}
                  onPress={() => resolve("approve")}
                  disabled={resolving}
                  accessibilityRole="button"
                  accessibilityLabel="Approve Verification"
                >
                  {resolving ? (
                    <ActivityIndicator color="#FFFFFF" size="small" />
                  ) : (
                    <Text style={styles.btnText}>✓ Confirm Legitimacy</Text>
                  )}
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.rejectBtn,
                    {
                      backgroundColor: `${colors.danger}18`,
                      borderColor: `${colors.danger}55`,
                      borderRadius: radius.md,
                    },
                  ]}
                  onPress={() => resolve("reject")}
                  disabled={resolving}
                  accessibilityRole="button"
                  accessibilityLabel="Reject / Block Request"
                >
                  <Text style={[styles.rejectBtnText, { color: colors.danger }]}>
                    ✗ Reject & Block
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </>
        )}
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
  channelsSection: {
    gap: 8,
  },
  channelsHeader: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.8,
    marginBottom: 2,
  },
  channelCard: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    padding: 14,
  },
  channelIconBox: {
    width: 38,
    height: 38,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 12,
  },
  channelTextBox: {
    flex: 1,
  },
  channelTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  channelDesc: {
    fontSize: 11,
    marginTop: 2,
  },
  channelArrow: {
    fontSize: 20,
    fontWeight: "300",
  },
  deviceVerificationBox: {
    borderWidth: 1,
    padding: 18,
    alignItems: "center",
    gap: 14,
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  timerWrap: {
    alignItems: "center",
    marginVertical: 4,
  },
  timerRing: {
    width: 90,
    height: 90,
    borderRadius: 45,
    borderWidth: 2.5,
    alignItems: "center",
    justifyContent: "center",
  },
  timerValue: {
    fontSize: 24,
    fontWeight: "800",
  },
  timerSub: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  nonceContainer: {
    alignItems: "center",
    gap: 2,
  },
  nonceHeader: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1,
  },
  nonceCode: {
    fontSize: 13,
    fontFamily: "monospace",
    fontWeight: "600",
  },
  resolveButtonsRow: {
    flexDirection: "row",
    gap: 10,
    width: "100%",
  },
  approveBtn: {
    flex: 1,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  rejectBtn: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  btnText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  rejectBtnText: {
    fontSize: 13,
    fontWeight: "700",
  },
  resultCard: {
    borderWidth: 1.5,
    padding: 24,
    alignItems: "center",
    gap: 8,
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  resultTitle: {
    fontSize: 18,
    fontWeight: "800",
  },
  resultSubtitle: {
    fontSize: 13,
    textAlign: "center",
  },
  doneBtn: {
    marginTop: 12,
    paddingVertical: 12,
    paddingHorizontal: 20,
  },
  doneBtnText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
  },
});
