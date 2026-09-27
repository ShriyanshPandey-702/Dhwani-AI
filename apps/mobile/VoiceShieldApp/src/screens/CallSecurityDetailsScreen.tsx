import React from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from "react-native";
import { useNavigation, useRoute, RouteProp } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "../utils/theme";
import { RiskBadge } from "../components/RiskBadge";
import { RootStackParamList } from "../navigation/AppNavigator";
import { ScreenedCallEvent } from "../types/telecom";
import { RiskState } from "../types";

type Route = RouteProp<RootStackParamList, "CallSecurityDetails">;

export const CallSecurityDetailsScreen: React.FC = () => {
  const navigation = useNavigation();
  const route = useRoute<Route>();
  const insets = useSafeAreaInsets();
  const { colors, riskColors, radius, isDark } = useTheme();

  const { callRecord } = route.params;

  const formatDateTime = (timestamp: number): string => {
    const d = new Date(timestamp);
    const pad = (n: number) => `${n}`.padStart(2, "0");
    const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    const time = `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
    return `${date} ${time}`;
  };

  const normalizeState = (raw: string | undefined | null): RiskState => {
    const s = raw?.toLowerCase();
    if (s === "low") return "low";
    if (s === "suspicious") return "suspicious";
    if (s === "high") return "high";
    if (s === "critical") return "critical";
    return "insufficient_evidence";
  };

  const state = normalizeState(callRecord.riskState);
  const riskColor = riskColors[state];
  const score = callRecord.riskScore ?? 0;

  const displayCaller = callRecord.callerName
    ? `${callRecord.callerName} (${callRecord.callerMasked})`
    : callRecord.callerMasked;

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
          paddingTop: insets.top,
        },
      ]}
    >
      {/* Header */}
      <View
        style={[
          styles.header,
          {
            borderBottomColor: colors.border,
            backgroundColor: isDark ? colors.surface : colors.surface,
          },
        ]}
      >
        <TouchableOpacity
          onPress={() => navigation.goBack()}
          style={styles.backBtn}
          accessibilityLabel="Go back"
          accessibilityRole="button"
        >
          <Text style={[styles.backBtnText, { color: colors.textSecondary }]}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.textPrimary }]}>
          Call Security Details
        </Text>
        <View style={styles.backPlaceholder} />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + 32 },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Top Risk Headline (Section 27) */}
        <View
          style={[
            styles.riskHeadlineCard,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.headlineLeft}>
            <Text style={{ fontSize: 11, fontWeight: "700", color: colors.accent, marginBottom: 4, letterSpacing: 0.5 }}>
              Incoming SIM Call — Metadata Only
            </Text>
            <Text style={[styles.headlineCaller, { color: colors.textPrimary }]}>
              {displayCaller}
            </Text>
            <Text style={[styles.headlineTime, { color: colors.textSecondary }]}>
              {formatDateTime(callRecord.timestamp)}
            </Text>
            <View style={styles.badgeWrap}>
              <RiskBadge state={state} size="md" />
            </View>
          </View>

          <View
            style={[
              styles.scoreCircle,
              {
                borderColor: `${riskColor}55`,
                backgroundColor: `${riskColor}12`,
              },
            ]}
          >
            <Text style={[styles.scoreValue, { color: riskColor }]}>{score}</Text>
            <Text style={[styles.scoreLabel, { color: colors.textMuted }]}>/ 100</Text>
          </View>
        </View>

        {/* Persistent Evidence Streams (Section 27) */}
        <View style={styles.sectionTitleRow}>
          <Text style={[styles.sectionTitle, { color: colors.textPrimary }]}>
            PERSISTENT EVIDENCE SUMMARY
          </Text>
        </View>

        {/* 1. Authenticity */}
        <View
          style={[
            styles.evidenceBox,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.evidenceHeader}>
            <Text style={[styles.evidenceTitle, { color: colors.textPrimary }]}>
              1. VOICE AUTHENTICITY
            </Text>
            <Text style={[styles.evidenceStatus, { color: colors.textMuted }]}>
              SIM METADATA
            </Text>
          </View>
          <Text style={[styles.evidenceDesc, { color: colors.textSecondary }]}>
            Cellular SIM carrier screening was evaluated. Raw cellular call media is restricted by Android OS from third-party recording.
          </Text>
          <View style={styles.evidenceDetailRow}>
            <Text style={[styles.evidenceKey, { color: colors.textMuted }]}>Carrier Verification: </Text>
            <Text style={[styles.evidenceVal, { color: colors.textPrimary }]}>
              {callRecord.verificationStatus === "PASSED"
                ? "STIR/SHAKEN Passed"
                : callRecord.verificationStatus === "FAILED"
                ? "Verification Failed"
                : "Not Signed by Carrier"}
            </Text>
          </View>
        </View>

        {/* 2. Identity */}
        <View
          style={[
            styles.evidenceBox,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.evidenceHeader}>
            <Text style={[styles.evidenceTitle, { color: colors.textPrimary }]}>
              2. SPEAKER IDENTITY
            </Text>
            <Text style={[styles.evidenceStatus, { color: colors.textMuted }]}>
              CONTACT SIGNALS
            </Text>
          </View>
          <View style={styles.evidenceDetailRow}>
            <Text style={[styles.evidenceKey, { color: colors.textMuted }]}>Contact Status: </Text>
            <Text style={[styles.evidenceVal, { color: colors.textPrimary }]}>
              {callRecord.contactStatus === "IN_CONTACTS"
                ? "Saved in Device Contacts"
                : "Not in Device Contacts"}
            </Text>
          </View>
          <View style={styles.evidenceDetailRow}>
            <Text style={[styles.evidenceKey, { color: colors.textMuted }]}>Caller Warning: </Text>
            <Text style={[styles.evidenceVal, { color: colors.textPrimary }]}>
              {callRecord.warningType === "NONE" ? "None" : callRecord.warningType}
            </Text>
          </View>
        </View>

        {/* 3. Active Liveness */}
        <View
          style={[
            styles.evidenceBox,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.evidenceHeader}>
            <Text style={[styles.evidenceTitle, { color: colors.textPrimary }]}>
              3. ACTIVE LIVENESS
            </Text>
            <Text style={[styles.evidenceStatus, { color: colors.textMuted }]}>
              PASSIVE SCREENING
            </Text>
          </View>
          <Text style={[styles.evidenceDesc, { color: colors.textSecondary }]}>
            Active cryptographic or verbal liveness challenge is available on-demand during live sessions.
          </Text>
        </View>

        {/* 4. Consequences / Intent */}
        <View
          style={[
            styles.evidenceBox,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.evidenceHeader}>
            <Text style={[styles.evidenceTitle, { color: colors.textPrimary }]}>
              4. CONSEQUENCES & INTENT
            </Text>
            <Text
              style={[
                styles.evidenceStatus,
                { color: callRecord.decision === "ALLOW" ? colors.success : colors.warning },
              ]}
            >
              {callRecord.decision?.toUpperCase() || "ALLOW"}
            </Text>
          </View>
          <Text style={[styles.evidenceDesc, { color: colors.textSecondary }]}>
            {callRecord.explanation || "No adverse screening indicators detected on incoming SIM call."}
          </Text>
        </View>

        {/* Screening Diagnostics */}
        <View
          style={[
            styles.diagnosticsBox,
            {
              backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
              borderColor: colors.border,
              borderRadius: radius.sm,
            },
          ]}
        >
          <Text style={[styles.diagTitle, { color: colors.textMuted }]}>
            TELECOM SCREENING DIAGNOSTICS
          </Text>
          <Text style={[styles.diagRow, { color: colors.textSecondary }]}>
            Latency: {callRecord.screeningLatencyMs ?? 0} ms · Event ID: {callRecord.eventId}
          </Text>
          <Text style={[styles.diagNote, { color: colors.textMuted }]}>
            Screened via Android Telecom CallScreeningService.
          </Text>
        </View>
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  backBtn: {
    paddingVertical: 4,
    paddingRight: 10,
  },
  backBtnText: {
    fontSize: 16,
    fontWeight: "600",
  },
  headerTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  backPlaceholder: {
    width: 40,
  },
  scroll: {
    paddingHorizontal: 18,
    paddingTop: 16,
    gap: 12,
  },
  riskHeadlineCard: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    borderWidth: 1,
    padding: 16,
  },
  headlineLeft: {
    flex: 1,
    marginRight: 12,
  },
  headlineCaller: {
    fontSize: 18,
    fontWeight: "800",
  },
  headlineTime: {
    fontSize: 12,
    marginTop: 2,
  },
  badgeWrap: {
    marginTop: 8,
  },
  scoreCircle: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  scoreValue: {
    fontSize: 26,
    fontWeight: "800",
  },
  scoreLabel: {
    fontSize: 9,
    fontWeight: "600",
  },
  sectionTitleRow: {
    marginTop: 6,
    marginBottom: 2,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1,
  },
  evidenceBox: {
    borderWidth: 1,
    padding: 14,
    gap: 6,
  },
  evidenceHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  evidenceTitle: {
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  evidenceStatus: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  evidenceDesc: {
    fontSize: 12,
    lineHeight: 16,
  },
  evidenceDetailRow: {
    flexDirection: "row",
    marginTop: 2,
  },
  evidenceKey: {
    fontSize: 12,
  },
  evidenceVal: {
    fontSize: 12,
    fontWeight: "600",
  },
  diagnosticsBox: {
    borderWidth: 1,
    padding: 12,
    gap: 4,
    marginTop: 4,
  },
  diagTitle: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.8,
  },
  diagRow: {
    fontSize: 11,
    fontFamily: "monospace",
  },
  diagNote: {
    fontSize: 10,
  },
});
