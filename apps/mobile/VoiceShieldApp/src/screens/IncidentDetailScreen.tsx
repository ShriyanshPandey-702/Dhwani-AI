import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { colors, spacing, radius, typography } from '../utils/theme';
import { IncidentDetail } from '../types';
import client from '../services/api/client';
import { RootStackParamList } from '../navigation/AppNavigator';

type Route = RouteProp<RootStackParamList, 'IncidentDetail'>;

export const IncidentDetailScreen: React.FC = () => {
  const route = useRoute<Route>();
  const { incidentId } = route.params;
  const [incident, setIncident] = useState<IncidentDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    client.get<IncidentDetail>(`/incidents/${incidentId}`)
      .then(r => setIncident(r.data))
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) return <ActivityIndicator color={colors.brand} size="large" style={{ flex: 1 }} />;
  if (!incident) return <Text style={styles.error}>Incident not found.</Text>;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scroll}>
      <Text style={styles.title}>Incident Report</Text>
      <Text style={styles.id}>#{incident.id.slice(0, 16)}</Text>

      <Row label="Final State" value={incident.final_state.toUpperCase()} />
      <Row label="Peak Risk Score" value={String(incident.peak_risk_score ?? 'N/A')} />
      <Row label="Peak Risk State" value={incident.peak_risk_state ?? 'N/A'} />
      <Row label="Action Taken" value={incident.action_taken ?? 'N/A'} />
      <Row label="Verification Outcome" value={incident.verification_outcome ?? 'N/A'} />
      <Row label="Policy Version" value={incident.policy_version} />
      <Row label="Timestamp" value={new Date(incident.created_at).toLocaleString()} />

      {/* Evidence Summary */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Evidence Summary</Text>
        <Text style={styles.json}>{JSON.stringify(incident.evidence_summary, null, 2)}</Text>
      </View>

      {/* Integrity Hash */}
      <View style={styles.hashBox}>
        <Text style={styles.hashLabel}>SHA-256 Integrity Hash</Text>
        <Text style={styles.hashValue} selectable numberOfLines={3}>
          {incident.integrity_hash}
        </Text>
        <Text style={styles.hashNote}>
          This hash verifies the evidence has not been tampered with since recording.
        </Text>
      </View>

      {/* Model Versions */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Model Versions</Text>
        {Object.entries(incident.model_versions).map(([k, v]) => (
          <Row key={k} label={k} value={v as string} />
        ))}
      </View>
    </ScrollView>
  );
};

const Row: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <View style={styles.row}>
    <Text style={styles.rowLabel}>{label}</Text>
    <Text style={styles.rowValue}>{value}</Text>
  </View>
);

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.md },
  title: { ...typography.h2 },
  id: { color: colors.textMuted, fontFamily: 'monospace', fontSize: 12, marginBottom: spacing.md },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  rowLabel: { color: colors.textSecondary, fontSize: 13, flex: 1 },
  rowValue: { color: colors.textPrimary, fontSize: 13, fontWeight: '600', flex: 1, textAlign: 'right' },
  section: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    borderWidth: 1, borderColor: colors.border,
  },
  sectionTitle: {
    fontSize: 12, fontWeight: '700', color: colors.textMuted,
    textTransform: 'uppercase', letterSpacing: 1, marginBottom: spacing.sm,
  },
  json: { ...typography.mono, fontSize: 11 },
  hashBox: {
    backgroundColor: `${colors.success}10`,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: 6,
    borderWidth: 1, borderColor: `${colors.success}40`,
  },
  hashLabel: { fontSize: 11, fontWeight: '700', color: colors.success, textTransform: 'uppercase', letterSpacing: 1 },
  hashValue: { fontFamily: 'monospace', fontSize: 11, color: colors.textSecondary },
  hashNote: { fontSize: 11, color: colors.textMuted, fontStyle: 'italic', marginTop: 4 },
  error: { color: colors.error, padding: spacing.lg },
});
