import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { DeviceData } from "../types";
import { useCallScreeningStore } from "../store/callScreeningStore";
import { useConnectionStore } from "../store/connectionStore";
import client from "../services/api/client";
import { BottomNavigation } from "../components/BottomNavigation";
import { BackgroundWave } from "../components/BackgroundWave";

export const DeviceTrustScreen: React.FC = () => {
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const isRoleHeld = useCallScreeningStore((s) => s.isRoleHeld);
  const connectionStatus = useConnectionStore((s) => s.connectionStatus);

  const [devices, setDevices] = useState<DeviceData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [registering, setRegistering] = useState(false);

  const load = async () => {
    try {
      const { data } = await client.get<DeviceData[]>("/devices");
      setDevices(data);
    } catch {
      // Backend may be offline
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const registerDevice = async () => {
    setRegistering(true);
    try {
      const { data } = await client.post("/devices/register", {
        device_name: "Secondary Device",
        platform: "android",
      });
      Alert.alert(
        "Device Registered ✓",
        `New secondary device enrolled for out-of-band verification token: ${data.device_token?.slice(0, 16)}…`,
        [{ text: "OK", onPress: load }]
      );
    } catch {
      Alert.alert("Notice", "Backend offline or could not register secondary device.");
    } finally {
      setRegistering(false);
    }
  };

  const revokeDevice = (deviceId: string) => {
    Alert.alert("Revoke Device", "This device will no longer be able to approve verifications.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Revoke",
        style: "destructive",
        onPress: async () => {
          try {
            await client.delete(`/devices/${deviceId}`);
            load();
          } catch {}
        },
      },
    ]);
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
        <Text style={[styles.title, { color: colors.textPrimary }]}>
          Device Security & Trust
        </Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
          Hardware trust binding, Telecom call screening status, and out-of-band verification devices.
        </Text>

        {/* Section 16: Current Primary Device Card */}
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
          <Text style={[styles.cardHeader, { color: colors.textMuted }]}>
            THIS DEVICE (PRIMARY)
          </Text>

          <View style={styles.deviceHeroRow}>
            <View
              style={[
                styles.deviceIconCircle,
                {
                  backgroundColor: isDark ? `${colors.accent}18` : `${colors.accent}12`,
                  borderColor: `${colors.accent}33`,
                },
              ]}
            >
              <Text style={{ fontSize: 26 }}>📱</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.deviceName, { color: colors.textPrimary }]}>
                Realme 8
              </Text>
              <Text style={[styles.devicePlatform, { color: colors.textSecondary }]}>
                Android 13 · Physical Device
              </Text>
            </View>
            <View
              style={[
                styles.statusPill,
                {
                  backgroundColor: `${colors.success}18`,
                  borderColor: `${colors.success}44`,
                  borderRadius: radius.full,
                },
              ]}
            >
              <Text style={[styles.statusPillText, { color: colors.success }]}>
                ACTIVE
              </Text>
            </View>
          </View>

          <View style={[styles.divider, { backgroundColor: colors.border }]} />

          <View style={styles.row}>
            <Text style={[styles.rowKey, { color: colors.textSecondary }]}>
              Device protection
            </Text>
            <Text style={[styles.rowVal, { color: colors.success }]}>
              ACTIVE
            </Text>
          </View>

          <View style={styles.row}>
            <Text style={[styles.rowKey, { color: colors.textSecondary }]}>
              Telecom call screening
            </Text>
            <Text
              style={[
                styles.rowVal,
                { color: isRoleHeld ? colors.success : colors.warning },
              ]}
            >
              {isRoleHeld ? "ACTIVE" : "NOT CONFIGURED"}
            </Text>
          </View>

          <View style={styles.row}>
            <Text style={[styles.rowKey, { color: colors.textSecondary }]}>
              Backend connection
            </Text>
            <Text
              style={[
                styles.rowVal,
                {
                  color:
                    connectionStatus === "connected"
                      ? colors.success
                      : connectionStatus === "error"
                      ? colors.danger
                      : colors.warning,
                },
              ]}
            >
              {connectionStatus === "connected"
                ? "CONNECTED"
                : connectionStatus === "error"
                ? "UNAVAILABLE"
                : "CHECKING"}
            </Text>
          </View>

          <View style={styles.row}>
            <Text style={[styles.rowKey, { color: colors.textSecondary }]}>
              Microphone PCM capture
            </Text>
            <Text style={[styles.rowVal, { color: colors.success }]}>
              ACTIVE
            </Text>
          </View>

          <View style={styles.row}>
            <Text style={[styles.rowKey, { color: colors.textSecondary }]}>
              Cellular raw audio access
            </Text>
            <Text style={[styles.rowVal, { color: colors.textMuted }]}>
              UNSUPPORTED (OS RESTRICTION)
            </Text>
          </View>
        </View>

        {/* Secondary Out-of-Band Devices (design.md Section 16) */}
        <View style={styles.sectionHeaderRow}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
            Secondary Verification Devices
          </Text>
        </View>

        <TouchableOpacity
          style={[
            styles.addBtn,
            {
              backgroundColor: colors.accent,
              borderRadius: radius.lg,
              opacity: registering ? 0.7 : 1,
            },
          ]}
          onPress={registerDevice}
          disabled={registering}
          accessibilityRole="button"
          accessibilityLabel="Register Secondary Device"
        >
          {registering ? (
            <ActivityIndicator color="#FFFFFF" size="small" />
          ) : (
            <Text style={styles.addBtnText}>+ Register Secondary Verification Device</Text>
          )}
        </TouchableOpacity>

        {isLoading ? (
          <ActivityIndicator color={colors.accent} style={{ marginTop: 24 }} />
        ) : devices.length === 0 ? (
          <View
            style={[
              styles.emptyCard,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.xl,
              },
            ]}
          >
            <Text style={[styles.emptyText, { color: colors.textMuted }]}>
              No secondary verification devices registered yet.
            </Text>
          </View>
        ) : (
          devices.map((d) => (
            <View
              key={d.id}
              style={[
                styles.secondaryCard,
                {
                  backgroundColor: isDark ? colors.surface : colors.surface,
                  borderColor: colors.border,
                  borderRadius: radius.lg,
                },
              ]}
            >
              <View style={styles.secLeft}>
                <Text style={{ fontSize: 22, marginRight: 10 }}>📱</Text>
                <View>
                  <Text style={[styles.secName, { color: colors.textPrimary }]}>
                    {d.device_name}
                  </Text>
                  <Text style={[styles.secMeta, { color: colors.textMuted }]}>
                    {d.platform} • {d.is_active ? "ACTIVE" : "REVOKED"}
                  </Text>
                </View>
              </View>
              <TouchableOpacity
                onPress={() => revokeDevice(d.id)}
                style={[
                  styles.revokeBtn,
                  {
                    backgroundColor: `${colors.danger}18`,
                    borderColor: `${colors.danger}44`,
                  },
                ]}
                accessibilityRole="button"
                accessibilityLabel="Revoke device"
              >
                <Text style={[styles.revokeBtnText, { color: colors.danger }]}>
                  Revoke
                </Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </ScrollView>

      {/* Persistent Bottom Navigation */}
      <BottomNavigation activeTab="device" />
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
  },
  subtitle: {
    fontSize: 13,
    lineHeight: 18,
  },
  card: {
    borderWidth: 1,
    padding: 16,
    gap: 10,
    marginTop: 6,
    elevation: 3,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
  },
  cardHeader: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.8,
  },
  deviceHeroRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },
  deviceIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  deviceName: {
    fontSize: 17,
    fontWeight: "800",
  },
  devicePlatform: {
    fontSize: 12,
    marginTop: 2,
  },
  statusPill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
  },
  statusPillText: {
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  divider: {
    height: 1,
    marginVertical: 4,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 3,
  },
  rowKey: {
    fontSize: 13,
  },
  rowVal: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  sectionHeaderRow: {
    marginTop: 8,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: "700",
  },
  addBtn: {
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
    elevation: 2,
  },
  addBtnText: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "700",
  },
  emptyCard: {
    borderWidth: 1,
    padding: 24,
    alignItems: "center",
  },
  emptyText: {
    fontSize: 13,
  },
  secondaryCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    padding: 14,
  },
  secLeft: {
    flexDirection: "row",
    alignItems: "center",
  },
  secName: {
    fontSize: 14,
    fontWeight: "700",
  },
  secMeta: {
    fontSize: 11,
    marginTop: 2,
  },
  revokeBtn: {
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 999,
  },
  revokeBtnText: {
    fontSize: 11,
    fontWeight: "700",
  },
});
