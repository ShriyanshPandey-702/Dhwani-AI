import React from 'react';
import { View, Text, StyleSheet, ScrollView, Switch, TouchableOpacity } from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { colors, spacing, radius, typography } from '../utils/theme';
import { useAuthStore } from '../store/authStore';

export const SettingsScreen: React.FC = () => {
  const navigation = useNavigation();
  const { user, logout } = useAuthStore();
  const [pushEnabled, setPushEnabled] = React.useState(true);
  const [rawAudioEnabled, setRawAudioEnabled] = React.useState(false);

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Settings</Text>

        {/* Account */}
        <Section title="Account">
          <Row label="Email" value={user?.email || '—'} />
          <Row label="Role" value={user?.role || 'user'} />
          <TouchableOpacity
            onPress={() => navigation.navigate('Devices' as never)}
            style={styles.linkRow}
            accessibilityLabel="Manage trusted devices"
            accessibilityRole="button">
            <Text style={styles.linkText}>Manage Trusted Devices →</Text>
          </TouchableOpacity>
        </Section>

        {/* Notifications */}
        <Section title="Notifications">
          <ToggleRow
            label="Security Alerts"
            value={pushEnabled}
            onChange={setPushEnabled}
            description="Receive push alerts for high-risk events"
          />
        </Section>

        {/* Privacy */}
        <Section title="Privacy">
          <ToggleRow
            label="Raw Audio Retention"
            value={rawAudioEnabled}
            onChange={setRawAudioEnabled}
            description="Store raw audio for debugging (off by default per privacy policy)"
          />
          <Row label="Data Minimization" value="Feature-only logging enabled" />
          <Row label="Third-party Processing" value="None — analysis runs on the VoiceShield backend" />
        </Section>

        {/* Detection pipeline */}
        <Section title="Detection Pipeline">
          <Row label="Authenticity" value="Heuristic DSP stub (AASIST/RawNet2 planned)" />
          <Row label="Speaker Identity" value="Spectral stub (ECAPA-TDNN planned)" />
          <Row label="Speech-to-Text" value="Scripted stub (Whisper planned)" />
          <Row label="Context Rules" value="Rule-based, active" />
          <Row label="Audio Source" value="Development mock audio" />
        </Section>

        {/* Security */}
        <Section title="Security">
          <Row label="Transport" value="TLS enforced" />
          <Row label="Local Storage" value="Android Keystore" />
          <Row label="Evidence Integrity" value="SHA-256 hashing" />
          <Row label="Policy Version" value="v1" />
        </Section>

        {/* Logout */}
        <TouchableOpacity
          style={styles.logoutBtn}
          onPress={logout}
          accessibilityLabel="Sign out"
          accessibilityRole="button">
          <Text style={styles.logoutText}>Sign Out</Text>
        </TouchableOpacity>

        <Text style={styles.version}>VoiceShield v0.1.0 · SIH 2026 · Problem 26104</Text>
      </ScrollView>
    </View>
  );
};

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <View style={styles.section}>
    <Text style={styles.sectionTitle}>{title}</Text>
    <View style={styles.sectionContent}>{children}</View>
  </View>
);

const Row: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <View style={styles.row}>
    <Text style={styles.rowLabel}>{label}</Text>
    <Text style={styles.rowValue}>{value}</Text>
  </View>
);

const ToggleRow: React.FC<{ label: string; value: boolean; onChange: (v: boolean) => void; description: string }> =
  ({ label, value, onChange, description }) => (
    <View style={styles.toggleRow}>
      <View style={{ flex: 1 }}>
        <Text style={styles.rowLabel}>{label}</Text>
        <Text style={styles.rowDesc}>{description}</Text>
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        trackColor={{ false: colors.bgElevated, true: colors.brand }}
        thumbColor={colors.white}
        accessibilityLabel={label}
      />
    </View>
  );

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.md },
  title: { ...typography.h2, marginBottom: spacing.sm },
  section: { gap: spacing.sm },
  sectionTitle: {
    fontSize: 12, fontWeight: '700', color: colors.textMuted,
    textTransform: 'uppercase', letterSpacing: 1.2,
  },
  sectionContent: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  rowLabel: { color: colors.textSecondary, fontSize: 14 },
  rowValue: { color: colors.textPrimary, fontSize: 14, fontWeight: '600', maxWidth: '60%', textAlign: 'right' },
  rowDesc: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  linkRow: {
    padding: spacing.md,
  },
  linkText: { color: colors.brand, fontWeight: '600', fontSize: 14 },
  logoutBtn: {
    backgroundColor: `${colors.error}18`,
    borderRadius: radius.md,
    paddingVertical: 14, alignItems: 'center',
    borderWidth: 1, borderColor: `${colors.error}44`,
    marginTop: spacing.md,
  },
  logoutText: { color: colors.error, fontWeight: '700', fontSize: 15 },
  version: { textAlign: 'center', color: colors.textMuted, fontSize: 11, marginTop: spacing.sm },
});
