import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { colors, spacing, radius, typography } from '../utils/theme';
import { IncidentSummary } from '../types';
import client from '../services/api/client';
import { RootStackParamList } from '../navigation/AppNavigator';

type Nav = NativeStackNavigationProp<RootStackParamList>;

const STATE_COLORS: Record<string, string> = {
  low: colors.safe, suspicious: colors.suspicious,
  high: colors.high, critical: colors.critical, insufficient_evidence: colors.watch,
};

export const IncidentHistoryScreen: React.FC = () => {
  const navigation = useNavigation<Nav>();
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    client.get<IncidentSummary[]>('/incidents')
      .then(r => setIncidents(r.data))
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, []);

  const renderItem = ({ item }: { item: IncidentSummary }) => {
    const color = STATE_COLORS[item.peak_risk_state || 'low'] || colors.watch;
    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => navigation.navigate('IncidentDetail', { incidentId: item.id })}
        accessibilityLabel={`Incident ${item.id.slice(0, 8)}, state ${item.final_state}`}
        accessibilityRole="button">
        <View style={styles.cardLeft}>
          <View style={[styles.riskDot, { backgroundColor: color }]} />
          <View>
            <Text style={styles.incidentId}>#{item.id.slice(0, 8)}</Text>
            <Text style={styles.incidentDate}>{new Date(item.created_at).toLocaleString()}</Text>
          </View>
        </View>
        <View style={styles.cardRight}>
          <Text style={[styles.stateText, { color }]}>{(item.peak_risk_state || 'low').toUpperCase()}</Text>
          <Text style={styles.scoreText}>{item.peak_risk_score ?? 0}</Text>
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Incident History</Text>
      {isLoading ? (
        <ActivityIndicator color={colors.brand} size="large" style={{ marginTop: 48 }} />
      ) : (
        <FlatList
          data={incidents}
          keyExtractor={i => i.id}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.emptyText}>No incidents recorded yet.</Text>
            </View>
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  title: { ...typography.h2, padding: spacing.lg, paddingBottom: spacing.md },
  list: { padding: spacing.lg, gap: spacing.sm },
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1, borderColor: colors.border,
  },
  cardLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  riskDot: { width: 10, height: 10, borderRadius: 5 },
  incidentId: { fontWeight: '700', color: colors.textPrimary, fontSize: 15 },
  incidentDate: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  cardRight: { alignItems: 'flex-end' },
  stateText: { fontSize: 11, fontWeight: '700', letterSpacing: 1 },
  scoreText: { fontSize: 22, fontWeight: '800', color: colors.textPrimary },
  empty: { alignItems: 'center', padding: spacing.xl },
  emptyText: { color: colors.textMuted, fontSize: 14 },
});
