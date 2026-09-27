import React, { useEffect, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  TouchableOpacity,
} from "react-native";
import { useRoute, useNavigation, RouteProp } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { IncidentDetail } from "../types";
import client from "../services/api/client";
import { RootStackParamList } from "../navigation/AppNavigator";
import { RiskBadge } from "../components/RiskBadge";

type Route = RouteProp<RootStackParamList, "IncidentDetail">;

export const IncidentDetailScreen: React.FC = () => {
  const route = useRoute<Route>();
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const { incidentId } = route.params;
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    client
      .get<IncidentDetail>(`/incidents/${incidentId}`)
      .then((r) => setIncident(r.data))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [incidentId]);

  if (isLoading) {
    return (
      <View
        style={[
          styles.container,
          styles.center,
          { backgroundColor: isDark ? colors.background : colors.background },
        ]}
      >
        <ActivityIndicator color={colors.accent} size="large" />
      </View>
    );
  }

  if (!incident) {
    return (
      <View
        style={[
          styles.container,
          styles.center,
          { backgroundColor: isDark ? colors.background : colors.background },
        ]}
      >
        <Text style={[styles.error, { color: colors.danger }]}>Incident record not found.</Text>
        <TouchableOpacity onPress={() => navigation.goBack()} style={{ marginTop: 12 }}>
          <Text style={{ color: colors.accent, fontWeight: "700" }}>‹ Go Back</Text>
        </TouchableOpacity>
      </View>
    );
  }

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
          accessibilityRole="button"
        >
          <Text style={[styles.backText, { color: colors.textSecondary }]}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.textPrimary }]}>
          Incident Report
        </Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          { paddingBottom: insets.bottom + 32 },
        ]}
      >
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.md,
            },
          ]}
        >
          <View style={styles.topRow}>
            <Text style={[styles.id, { color: colors.textMuted }]}>
              #{incident.id.slice(0, 16)}
            </Text>
            <RiskBadge state={incident.peak_risk_state || incident.final_state} size="sm" />
          </View>

          <Row label="Final State" value={incident.final_state.toUpperCase()} />
          <Row label="Peak Risk Score" value={String(incident.peak_risk_score ?? "N/A")} />
          <Row label="Action Taken" value={incident.action_taken ?? "N/A"} />
          <Row label="Verification" value={incident.verification_outcome ?? "N/A"} />
          <Row label="Policy Version" value={incident.policy_version} />
          <Row label="Timestamp" value={new Date(incident.created_at).toLocaleString()} />
        </View>

        {/* SHA-256 Integrity Hash */}
        <View
          style={[
            styles.hashBox,
            {
              backgroundColor: `${colors.success}10`,
              borderColor: `${colors.success}40`,
              borderRadius: radius.md,
            },
          ]}
        >
          <Text style={[styles.hashLabel, { color: colors.success }]}>
            SHA-256 Tamper-Proof Integrity Hash
          </Text>
          <Text style={[styles.hashValue, { color: colors.textPrimary }]} selectable numberOfLines={3}>
            {incident.integrity_hash}
          </Text>
          <Text style={[styles.hashNote, { color: colors.textMuted }]}>
            Guarantees forensic session telemetry has not been tampered with since creation.
          </Text>
        </View>

        {/* Model Versions */}
        {incident.model_versions && (
          <View
            style={[
              styles.card,
              {
                backgroundColor: isDark ? colors.surface : colors.surface,
                borderColor: colors.border,
                borderRadius: radius.md,
              },
            ]}
          >
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>
              Active AI Models
            </Text>
            {Object.entries(incident.model_versions).map(([k, v]) => (
              <Row key={k} label={k} value={String(v)} />
            ))}
          </View>
        )}
      </ScrollView>
    </View>
  );
};

const Row: React.FC<{ label: string; value: string }> = ({ label, value }) => {
  const { colors } = useTheme();
  return (
    <View style={[styles.row, { borderBottomColor: colors.border }]}>
      <Text style={[styles.rowLabel, { color: colors.textSecondary }]}>{label}</Text>
      <Text style={[styles.rowValue, { color: colors.textPrimary }]}>{value}</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  backBtn: { paddingVertical: 4, paddingRight: 10 },
  backText: { fontSize: 16, fontWeight: "600" },
  headerTitle: { fontSize: 16, fontWeight: "700" },
  scroll: { padding: 18, gap: 12 },
  card: { borderWidth: 1, padding: 16, gap: 4 },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  id: { fontFamily: "monospace", fontSize: 12 },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  rowLabel: { fontSize: 13, flex: 1 },
  rowValue: { fontSize: 13, fontWeight: "600", flex: 1, textAlign: "right" },
  sectionTitle: {
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 0.8,
    textTransform: "uppercase",
    marginBottom: 4,
  },
  hashBox: { borderWidth: 1, padding: 14, gap: 6 },
  hashLabel: { fontSize: 11, fontWeight: "700", letterSpacing: 0.8 },
  hashValue: { fontFamily: "monospace", fontSize: 11 },
  hashNote: { fontSize: 11, fontStyle: "italic", marginTop: 2 },
  error: { fontSize: 14 },
});
