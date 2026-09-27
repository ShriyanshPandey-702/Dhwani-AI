import React, { useEffect, useState, useMemo } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { IncidentSummary, RiskState } from "../types";
import { ScreenedCallEvent } from "../types/telecom";
import { useCallScreeningStore } from "../store/callScreeningStore";
import client from "../services/api/client";
import { RootStackParamList } from "../navigation/AppNavigator";
import { CallRow } from "../components/CallRow";
import { BottomNavigation } from "../components/BottomNavigation";

type Nav = NativeStackNavigationProp<RootStackParamList>;
type FilterType = "all" | "low" | "suspicious" | "high";

type UnifiedCallRecord = {
  id: string;
  source: "screened" | "incident";
  callerName?: string | null;
  callerMasked: string;
  timestamp: number;
  riskState: RiskState;
  decision?: string;
  category: string;
  screenedRecord?: ScreenedCallEvent;
  incidentId?: string;
};

const normalizeRiskState = (raw: string | undefined | null): RiskState => {
  const s = raw?.toLowerCase();
  if (s === "low") return "low";
  if (s === "suspicious") return "suspicious";
  if (s === "high") return "high";
  if (s === "critical") return "critical";
  return "insufficient_evidence";
};

export const IncidentHistoryScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const recentScreenedCalls = useCallScreeningStore((s) => s.recentCalls);
  const loadRecentCalls = useCallScreeningStore((s) => s.loadRecentCalls);

  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeFilter, setActiveFilter] = useState<FilterType>("all");

  useEffect(() => {
    loadRecentCalls();
    client
      .get<IncidentSummary[]>("/incidents")
      .then((r) => setIncidents(r.data))
      .catch(() => {})
      .finally(() => setIsLoading(false));
  }, [loadRecentCalls]);

  // Combine and sort real calls
  const unifiedRecords: UnifiedCallRecord[] = useMemo(() => {
    const list: UnifiedCallRecord[] = [];

    recentScreenedCalls.forEach((sc) => {
      list.push({
        id: `sc-${sc.eventId}`,
        source: "screened",
        callerName: sc.callerName,
        callerMasked: sc.callerMasked,
        timestamp: sc.timestamp,
        riskState: normalizeRiskState(sc.riskState),
        decision: sc.decision,
        category: "Incoming SIM Call — Metadata Only",
        screenedRecord: sc,
      });
    });

    incidents.forEach((inc) => {
      const ms = new Date(inc.created_at).getTime();
      list.push({
        id: `inc-${inc.id}`,
        source: "incident",
        callerMasked: `Session ${inc.session_id?.slice(0, 8) || inc.id.slice(0, 8)}`,
        timestamp: isNaN(ms) ? Date.now() : ms,
        riskState: normalizeRiskState(inc.peak_risk_state || inc.final_state),
        decision: inc.action_taken || undefined,
        category: "Device Microphone — Live Audio",
        incidentId: inc.id,
      });
    });

    list.sort((a, b) => b.timestamp - a.timestamp);
    return list;
  }, [recentScreenedCalls, incidents]);

  // Filter based on selected chip
  const filteredRecords = useMemo(() => {
    if (activeFilter === "all") return unifiedRecords;
    if (activeFilter === "low") {
      return unifiedRecords.filter((r) => r.riskState === "low");
    }
    if (activeFilter === "suspicious") {
      return unifiedRecords.filter((r) => r.riskState === "suspicious");
    }
    if (activeFilter === "high") {
      return unifiedRecords.filter(
        (r) => r.riskState === "high" || r.riskState === "critical"
      );
    }
    return unifiedRecords;
  }, [unifiedRecords, activeFilter]);

  const filterChips: { key: FilterType; label: string }[] = [
    { key: "all", label: "All" },
    { key: "low", label: "Low" },
    { key: "suspicious", label: "Suspicious" },
    { key: "high", label: "High Risk" },
  ];

  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
        },
      ]}
    >
      {/* Top Header (design.md Section 26) */}
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>
          Call History
        </Text>
        <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
          Screened cellular calls & live voice telemetry
        </Text>
      </View>

      {/* Horizontal Filter Chips (Section 26) */}
      <View style={styles.chipsWrapper}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipsScroll}
        >
          {filterChips.map((chip) => {
            const isSelected = activeFilter === chip.key;
            return (
              <TouchableOpacity
                key={chip.key}
                activeOpacity={0.7}
                onPress={() => setActiveFilter(chip.key)}
                style={[
                  styles.chip,
                  {
                    backgroundColor: isSelected ? colors.accent : isDark ? colors.surface : colors.surface,
                    borderColor: isSelected ? colors.accent : colors.border,
                    borderRadius: radius.full,
                  },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`Filter: ${chip.label}`}
              >
                <Text
                  style={[
                    styles.chipText,
                    {
                      color: isSelected ? "#FFFFFF" : colors.textSecondary,
                      fontWeight: isSelected ? "700" : "500",
                    },
                  ]}
                >
                  {chip.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Call List */}
      {isLoading ? (
        <View style={styles.loaderWrap}>
          <ActivityIndicator color={colors.accent} size="large" />
        </View>
      ) : (
        <FlatList
          data={filteredRecords}
          keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <CallRow
              callerName={item.callerName}
              callerMasked={item.callerMasked}
              timestamp={item.timestamp}
              riskState={item.riskState}
              decision={item.decision}
              category={item.category}
              onPress={() => {
                if (item.source === "screened" && item.screenedRecord) {
                  navigation.navigate("CallSecurityDetails", {
                    callRecord: item.screenedRecord,
                  });
                } else if (item.incidentId) {
                  navigation.navigate("IncidentDetail", {
                    incidentId: item.incidentId,
                  });
                }
              }}
            />
          )}
          contentContainerStyle={[
            styles.list,
            { paddingBottom: Math.max(insets.bottom, 20) + 16 },
          ]}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Text style={{ fontSize: 36, marginBottom: 8 }}>📋</Text>
              <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>
                No calls yet
              </Text>
              <Text style={[styles.emptySubtitle, { color: colors.textSecondary }]}>
                {activeFilter === "all"
                  ? "Incoming screened calls and recorded sessions will appear here."
                  : `No calls matching "${activeFilter}" risk filter.`}
              </Text>
            </View>
          }
        />
      )}

      {/* Bottom Navigation */}
      <BottomNavigation activeTab="calls" />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 8,
    gap: 3,
  },
  title: {
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: -0.4,
  },
  subtitle: {
    fontSize: 13,
  },
  chipsWrapper: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: "rgba(128,128,128,0.15)",
  },
  chipsScroll: {
    paddingHorizontal: 20,
    gap: 8,
  },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 7,
    borderWidth: 1,
  },
  chipText: {
    fontSize: 12,
  },
  list: {
    paddingHorizontal: 20,
    paddingTop: 12,
    gap: 4,
  },
  loaderWrap: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  emptyState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 60,
    paddingHorizontal: 30,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  emptySubtitle: {
    fontSize: 13,
    textAlign: "center",
    marginTop: 4,
    lineHeight: 18,
  },
});
