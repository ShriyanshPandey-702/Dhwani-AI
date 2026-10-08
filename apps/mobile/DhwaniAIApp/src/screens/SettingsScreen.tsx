import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Switch,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  Alert,
} from "react-native";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { RootStackParamList } from "../navigation/AppNavigator";
import { ThemeToggle } from "../components/ThemeToggle";
import { BottomNavigation } from "../components/BottomNavigation";
import { BackgroundWave } from "../components/BackgroundWave";
import {
  useConnectionStore,
  getApiBaseUrl,
  getWsBaseUrl,
} from "../store/connectionStore";
import { useCallScreeningStore } from "../store/callScreeningStore";
import { useAuthStore } from "../store/authStore";
import { callScreeningService } from "../services/telecom/callScreeningService";
import { DhwaniLogo } from "../components/DhwaniLogo";
import { UserIcon, CodeIcon, ShieldIcon } from "../components/Icons";

type Nav = NativeStackNavigationProp<RootStackParamList>;

const SettingRow: React.FC<{
  label: string;
  description?: string;
  children: React.ReactNode;
}> = ({ label, description, children }) => {
  const { colors } = useTheme();
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingTextCol}>
        <Text style={[styles.settingLabel, { color: colors.textPrimary }]}>{label}</Text>
        {description ? (
          <Text style={[styles.settingDesc, { color: colors.textSecondary }]}>
            {description}
          </Text>
        ) : null}
      </View>
      <View style={styles.settingControlCol}>{children}</View>
    </View>
  );
};

export const SettingsScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  // Notification toggles
  const [notifyIncoming, setNotifyIncoming] = useState(true);
  const [notifyAlerts, setNotifyAlerts] = useState(true);
  const [notifyEmail, setNotifyEmail] = useState(false);

  // Analysis toggles
  const [riskUpdates, setRiskUpdates] = useState(true);
  const [liveTranscript, setLiveTranscript] = useState(true);
  const [audioRetention, setAudioRetention] = useState(false);

  const isRoleHeld = useCallScreeningStore((s) => s.isRoleHeld);
  const checkRoleStatus = useCallScreeningStore((s) => s.checkRoleStatus);
  const requestRole = useCallScreeningStore((s) => s.requestRole);
  const isRoleLoading = useCallScreeningStore((s) => s.isLoading);

  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  useFocusEffect(
    React.useCallback(() => {
      checkRoleStatus();
    }, [checkRoleStatus])
  );

  const handleTestNotification = async () => {
    try {
      await callScreeningService.testSecurityNotification();
      Alert.alert("Notification Sent", "A local test security alert was dispatched to your notification shade.");
    } catch (err: any) {
      Alert.alert("Notification Test Failed", err?.message || "Could not send test notification.");
    }
  };

  const {
    mode,
    wifiHost,
    wifiPort,
    connectionStatus,
    statusMessage,
    setMode,
    setWifiHost,
    setWifiPort,
    testConnection,
  } = useConnectionStore();

  const activeApiUrl = getApiBaseUrl();
  const activeWsUrl = getWsBaseUrl();

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

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 16,
            paddingBottom: Math.max(insets.bottom, 20) + 16,
          },
        ]}
        showsVerticalScrollIndicator={false}
      >
        <Text style={[styles.title, { color: colors.textPrimary }]}>Settings</Text>

        {/* ── User Profile Card (design.md Section 19) ────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <View style={styles.profileRow}>
            <View
              style={[
                styles.avatarCircle,
                {
                  backgroundColor: isDark ? `${colors.accent}20` : `${colors.accent}14`,
                  borderColor: `${colors.accent}40`,
                },
              ]}
            >
              <UserIcon size={22} color={colors.accent} />
            </View>
            <View style={styles.profileInfo}>
              <Text style={[styles.profileName, { color: colors.textPrimary }]}>
                {user?.full_name || "Security Administrator"}
              </Text>
              <Text style={[styles.profileEmail, { color: colors.textSecondary }]}>
                {user?.email || "dhwani.ai@security.local"}
              </Text>
            </View>
            <View
              style={[
                styles.verifiedPill,
                {
                  backgroundColor: `${colors.success}18`,
                  borderColor: `${colors.success}44`,
                },
              ]}
            >
              <Text style={[styles.verifiedText, { color: colors.success }]}>
                ENROLLED
              </Text>
            </View>
          </View>
        </View>

        {/* ── Section: Appearance (design.md Section 19) ─────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            APPEARANCE & THEME
          </Text>
          <Text style={[styles.cardSubtext, { color: colors.textMuted }]}>
            Select Light mode, Dark mode, or follow system default.
          </Text>
          <ThemeToggle />
        </View>

        {/* ── Section: Notifications ───────────────────────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            NOTIFICATIONS
          </Text>

          <SettingRow
            label="Incoming Calls"
            description="Display heads-up alert banner on screened incoming calls"
          >
            <Switch
              value={notifyIncoming}
              onValueChange={setNotifyIncoming}
              trackColor={{ false: colors.border, true: colors.accent }}
            />
          </SettingRow>

          <SettingRow
            label="Security Alerts"
            description="High-priority alerts when deepfake or fraud is detected"
          >
            <Switch
              value={notifyAlerts}
              onValueChange={setNotifyAlerts}
              trackColor={{ false: colors.border, true: colors.accent }}
            />
          </SettingRow>

          <SettingRow
            label="Email Alerts"
            description="Send incident summary report to registered email"
          >
            <Switch
              value={notifyEmail}
              onValueChange={setNotifyEmail}
              trackColor={{ false: colors.border, true: colors.accent }}
            />
          </SettingRow>
        </View>

        {/* ── Section: Analysis & Privacy ─────────────────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            ANALYSIS & PRIVACY
          </Text>

          <SettingRow
            label="Risk Updates"
            description="Continuous multi-modal score calculation during speech"
          >
            <Switch
              value={riskUpdates}
              onValueChange={setRiskUpdates}
              trackColor={{ false: colors.border, true: colors.accent }}
            />
          </SettingRow>

          <SettingRow
            label="Live Transcript"
            description="Show partial speech recognition transcript during call"
          >
            <Switch
              value={liveTranscript}
              onValueChange={setLiveTranscript}
              trackColor={{ false: colors.border, true: colors.accent }}
            />
          </SettingRow>

          <SettingRow
            label="Audio Retention"
            description="Temporarily save raw audio chunks for forensic replay (disabled by default)"
          >
            <Switch
              value={audioRetention}
              onValueChange={setAudioRetention}
              trackColor={{ false: colors.border, true: colors.accent }}
            />
          </SettingRow>
        </View>

        {/* ── Section: Call Screening ─────────────────────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            TELECOM CALL SCREENING
          </Text>

          <View style={styles.roleRow}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.settingLabel, { color: colors.textPrimary }]}>
                Screening Service Status
              </Text>
              <Text style={[styles.settingDesc, { color: colors.textSecondary }]}>
                {isRoleHeld
                  ? "Dhwani AI is active as your Android Call Screening app."
                  : "Requires user designation in Android System Settings."}
              </Text>
            </View>
            <View
              style={[
                styles.statusBadge,
                {
                  backgroundColor: isRoleHeld ? `${colors.success}18` : `${colors.warning}18`,
                  borderColor: isRoleHeld ? `${colors.success}44` : `${colors.warning}44`,
                },
              ]}
            >
              <Text
                style={[
                  styles.statusBadgeText,
                  { color: isRoleHeld ? colors.success : colors.warning },
                ]}
              >
                {isRoleHeld ? "ACTIVE" : "NOT CONFIGURED"}
              </Text>
            </View>
          </View>

          {!isRoleHeld && (
            <TouchableOpacity
              style={[styles.actionBtn, { backgroundColor: colors.accent, borderRadius: radius.md }]}
              onPress={requestRole}
              disabled={isRoleLoading}
            >
              <Text style={styles.actionBtnText}>
                {isRoleLoading ? "Requesting..." : "Enable Call Screening"}
              </Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[
              styles.secondaryBtn,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
            onPress={handleTestNotification}
          >
            <Text style={[styles.secondaryBtnText, { color: colors.textPrimary }]}>
              🔔 Test Security Alert Notification
            </Text>
          </TouchableOpacity>
        </View>

        {/* ── Section: Platform & Integration APIs ─────────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            PLATFORM & INTEGRATION APIS
          </Text>

          <View style={styles.integrationCardRow}>
            <View style={[styles.integrationIconBox, { backgroundColor: `${colors.accent}18` }]}>
              <CodeIcon size={20} color={colors.accent} strokeWidth={2.2} />
            </View>
            <View style={styles.integrationTextCol}>
              <Text style={[styles.integrationTitle, { color: colors.textPrimary }]}>
                Dhwani AI Integration Hub
              </Text>
              <Text style={[styles.integrationSubtitle, { color: colors.textSecondary }]}>
                REST, WebSocket, SDK, SIP, Banking & Contact Center APIs
              </Text>
            </View>
          </View>

          <TouchableOpacity
            style={[
              styles.integrationBtn,
              {
                backgroundColor: colors.accent,
                borderRadius: radius.md,
              },
            ]}
            onPress={() => navigation.navigate("IntegrationHub")}
            accessibilityRole="button"
            accessibilityLabel="Open Integration Hub"
          >
            <Text style={styles.integrationBtnText}>
              OPEN INTEGRATION HUB & CONSOLE →
            </Text>
          </TouchableOpacity>
        </View>

        {/* ── Section: Backend Connection ─────────────────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            BACKEND CONNECTION & NETWORK
          </Text>

          <View style={styles.modeTabs}>
            <TouchableOpacity
              style={[
                styles.modeTab,
                mode === "usb" && { backgroundColor: colors.accent },
              ]}
              onPress={() => setMode("usb")}
            >
              <Text
                style={[
                  styles.modeTabText,
                  { color: mode === "usb" ? "#FFFFFF" : colors.textSecondary },
                ]}
              >
                USB / ADB
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.modeTab,
                mode === "wifi" && { backgroundColor: colors.accent },
              ]}
              onPress={() => setMode("wifi")}
            >
              <Text
                style={[
                  styles.modeTabText,
                  { color: mode === "wifi" ? "#FFFFFF" : colors.textSecondary },
                ]}
              >
                Wi-Fi / LAN
              </Text>
            </TouchableOpacity>
          </View>

          {mode === "wifi" && (
            <View style={styles.wifiConfig}>
              <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>
                Host IP / Domain
              </Text>
              <TextInput
                style={[
                  styles.input,
                  {
                    backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                    color: colors.textPrimary,
                    borderColor: colors.border,
                    borderRadius: radius.sm,
                  },
                ]}
                value={wifiHost}
                onChangeText={setWifiHost}
                placeholder="192.168.1.X"
                placeholderTextColor={colors.textMuted}
                autoCapitalize="none"
              />
              <Text style={[styles.inputLabel, { color: colors.textSecondary, marginTop: 6 }]}>
                Port
              </Text>
              <TextInput
                style={[
                  styles.input,
                  {
                    backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                    color: colors.textPrimary,
                    borderColor: colors.border,
                    borderRadius: radius.sm,
                  },
                ]}
                value={wifiPort}
                onChangeText={setWifiPort}
                placeholder="8000"
                placeholderTextColor={colors.textMuted}
                keyboardType="numeric"
              />
            </View>
          )}

          <View style={styles.urlBox}>
            <Text style={[styles.urlLabel, { color: colors.textMuted }]}>
              REST API: <Text style={{ color: colors.textPrimary }}>{activeApiUrl}</Text>
            </Text>
            <Text style={[styles.urlLabel, { color: colors.textMuted }]}>
              WebSocket: <Text style={{ color: colors.textPrimary }}>{activeWsUrl}</Text>
            </Text>
          </View>

          <TouchableOpacity
            style={[
              styles.secondaryBtn,
              {
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
            onPress={testConnection}
          >
            {connectionStatus === "checking" ? (
              <ActivityIndicator color={colors.accent} size="small" />
            ) : (
              <Text style={[styles.secondaryBtnText, { color: colors.textPrimary }]}>
                ⚡ Test Backend Health
              </Text>
            )}
          </TouchableOpacity>

          {statusMessage ? (
            <Text
              style={[
                styles.statusMsg,
                {
                  color:
                    connectionStatus === "connected"
                      ? colors.success
                      : connectionStatus === "error"
                      ? colors.danger
                      : colors.textSecondary,
                },
              ]}
            >
              {statusMessage}
            </Text>
          ) : null}
        </View>

        {/* ── Section: About & Sign Out ────────────────────────────────────── */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.xl,
              shadowColor: isDark ? "#000000" : colors.cardShadow,
            },
          ]}
        >
          <Text style={[styles.cardHeader, { color: colors.textSecondary }]}>
            ABOUT DHWANI AI
          </Text>

          <View style={styles.aboutRow}>
            <View style={{ flexDirection: "row", alignItems: "center" }}>
              <DhwaniLogo size="sm" showText={false} style={{ marginRight: 8 }} />
              <Text style={[styles.aboutTitle, { color: colors.textPrimary }]}>
                Dhwani AI
              </Text>
            </View>
            <Text style={[styles.aboutVersion, { color: colors.textMuted }]}>
              Version 1.0.0 (Build 2026.09)
            </Text>
          </View>
          <Text style={[styles.aboutTagline, { color: colors.textSecondary }]}>
            Real-Time Voice Protection · Detect. Verify. Prevent.
          </Text>
          <Text style={[styles.aboutIndia, { color: colors.accent }]}>
            🇮🇳 Built for a Safer India · Voice Security Platform
          </Text>

          <TouchableOpacity
            style={[
              styles.logoutBtn,
              {
                backgroundColor: `${colors.danger}18`,
                borderColor: `${colors.danger}44`,
                borderRadius: radius.md,
              },
            ]}
            onPress={logout}
          >
            <Text style={[styles.logoutText, { color: colors.danger }]}>
              Sign Out
            </Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      {/* Persistent Bottom Navigation */}
      <BottomNavigation activeTab="settings" />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    paddingHorizontal: 20,
    gap: 12,
  },
  title: {
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: -0.4,
    marginBottom: 4,
  },
  card: {
    borderWidth: 1,
    padding: 16,
    gap: 12,
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  cardHeader: {
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.8,
  },
  cardSubtext: {
    fontSize: 12,
    marginTop: -4,
  },
  profileRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  avatarCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  profileInfo: {
    flex: 1,
  },
  profileName: {
    fontSize: 15,
    fontWeight: "700",
  },
  profileEmail: {
    fontSize: 12,
    marginTop: 2,
  },
  verifiedPill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 99,
    borderWidth: 1,
  },
  verifiedText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  settingRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 6,
  },
  settingTextCol: {
    flex: 1,
    marginRight: 12,
  },
  settingLabel: {
    fontSize: 14,
    fontWeight: "600",
  },
  settingDesc: {
    fontSize: 12,
    marginTop: 2,
    lineHeight: 16,
  },
  settingControlCol: {
    alignItems: "flex-end",
  },
  roleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  statusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    borderWidth: 1,
  },
  statusBadgeText: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  actionBtn: {
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  actionBtnText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  secondaryBtn: {
    borderWidth: 1,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
  },
  secondaryBtnText: {
    fontSize: 13,
    fontWeight: "600",
  },
  modeTabs: {
    flexDirection: "row",
    borderRadius: 8,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "rgba(128,128,128,0.2)",
  },
  modeTab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  modeTabText: {
    fontSize: 13,
    fontWeight: "600",
  },
  wifiConfig: {
    gap: 4,
  },
  inputLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
  input: {
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13,
  },
  urlBox: {
    padding: 10,
    borderRadius: 6,
    backgroundColor: "rgba(128,128,128,0.08)",
    gap: 4,
  },
  urlLabel: {
    fontSize: 11,
    fontFamily: "monospace",
  },
  statusMsg: {
    fontSize: 12,
    textAlign: "center",
    marginTop: 2,
  },
  aboutRow: {
    flexDirection: "row",
    alignItems: "baseline",
    justifyContent: "space-between",
  },
  aboutTitle: {
    fontSize: 16,
    fontWeight: "800",
  },
  aboutVersion: {
    fontSize: 11,
  },
  aboutTagline: {
    fontSize: 12,
  },
  aboutIndia: {
    fontSize: 11,
    fontWeight: "600",
    marginTop: -4,
  },
  logoutBtn: {
    borderWidth: 1,
    paddingVertical: 11,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 6,
  },
  logoutText: {
    fontSize: 13,
    fontWeight: "700",
  },
  integrationCardRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 12,
  },
  integrationIconBox: {
    width: 40,
    height: 40,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
  },
  integrationTextCol: {
    flex: 1,
  },
  integrationTitle: {
    fontSize: 14,
    fontWeight: "700",
  },
  integrationSubtitle: {
    fontSize: 11,
    marginTop: 2,
  },
  integrationBtn: {
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  integrationBtnText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
});
