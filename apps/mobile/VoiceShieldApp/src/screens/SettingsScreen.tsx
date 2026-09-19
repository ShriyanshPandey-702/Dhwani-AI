import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Switch,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { colors, spacing, radius, typography } from '../utils/theme';
import {
  useConnectionStore,
  getApiBaseUrl,
  getWsBaseUrl,
} from '../store/connectionStore';

export const SettingsScreen: React.FC = () => {
  const navigation = useNavigation();
  const [pushEnabled, setPushEnabled] = React.useState(true);
  const [rawAudioEnabled, setRawAudioEnabled] = React.useState(false);

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
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Settings</Text>

        {/* Backend Connection */}
        <Section title="Backend Connection">
          <View style={styles.modeSelector}>
            <TouchableOpacity
              style={[styles.modeBtn, mode === 'usb' && styles.modeBtnActive]}
              onPress={() => setMode('usb')}
              accessibilityLabel="USB ADB mode"
              accessibilityRole="button">
              <Text style={[styles.modeBtnText, mode === 'usb' && styles.modeBtnTextActive]}>
                USB / ADB
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.modeBtn, mode === 'wifi' && styles.modeBtnActive]}
              onPress={() => setMode('wifi')}
              accessibilityLabel="Wi-Fi LAN mode"
              accessibilityRole="button">
              <Text style={[styles.modeBtnText, mode === 'wifi' && styles.modeBtnTextActive]}>
                Wi-Fi / LAN
              </Text>
            </TouchableOpacity>
          </View>

          {mode === 'wifi' && (
            <View style={styles.wifiConfigContainer}>
              <View style={styles.inputRow}>
                <Text style={styles.inputLabel}>Backend Host (IP)</Text>
                <TextInput
                  style={styles.textInput}
                  value={wifiHost}
                  onChangeText={setWifiHost}
                  placeholder="192.168.1.5 (Mac LAN IP)"
                  placeholderTextColor={colors.textMuted}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="default"
                  accessibilityLabel="Backend host IP"
                />
              </View>

              <View style={styles.inputRow}>
                <Text style={styles.inputLabel}>Backend Port</Text>
                <TextInput
                  style={styles.textInput}
                  value={wifiPort}
                  onChangeText={setWifiPort}
                  placeholder="8000"
                  placeholderTextColor={colors.textMuted}
                  keyboardType="numeric"
                  accessibilityLabel="Backend port"
                />
              </View>

              {!wifiHost.trim() && (
                <View style={styles.warningBox}>
                  <Text style={styles.warningText}>
                    Please enter the Mac's LAN IP to connect over Wi-Fi.
                  </Text>
                </View>
              )}
            </View>
          )}

          <Row
            label="REST Endpoint"
            value={activeApiUrl || 'Not configured'}
          />
          <Row
            label="WebSocket"
            value={activeWsUrl || 'Not configured'}
          />

          <View style={styles.testConnectionContainer}>
            <TouchableOpacity
              style={[
                styles.testBtn,
                connectionStatus === 'checking' && styles.testBtnDisabled,
              ]}
              onPress={() => testConnection()}
              disabled={connectionStatus === 'checking'}
              accessibilityLabel="Test backend connection"
              accessibilityRole="button">
              {connectionStatus === 'checking' ? (
                <ActivityIndicator size="small" color={colors.white} />
              ) : (
                <Text style={styles.testBtnText}>Test Connection</Text>
              )}
            </TouchableOpacity>

            {statusMessage && (
              <View
                style={[
                  styles.statusBadge,
                  connectionStatus === 'connected' && styles.statusBadgeSuccess,
                  connectionStatus === 'error' && styles.statusBadgeError,
                ]}>
                <Text
                  style={[
                    styles.statusText,
                    connectionStatus === 'connected' && styles.statusTextSuccess,
                    connectionStatus === 'error' && styles.statusTextError,
                  ]}>
                  {statusMessage}
                </Text>
              </View>
            )}
          </View>
        </Section>

        {/* Account & Trust */}
        <Section title="Account & Trust">
          <Row label="Client Mode" value="Standalone Direct Access" />
          <Row label="Enrolment Status" value="Demo Enrolment Active" />
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
          <Row label="Authenticity" value="AASIST-L real authenticity detection" />
          <Row label="Speaker Identity" value="ECAPA-TDNN real speaker identity inference" />
          <Row label="Speech-to-Text" value="faster-whisper tiny real transcription" />
          <Row label="Context Rules" value="Rule-based, active" />
          <Row label="Audio Source" value="Real microphone/audio capture in live mode" />
        </Section>

        {/* Security */}
        <Section title="Security">
          <Row label="Transport" value="TLS / LAN WebSocket" />
          <Row label="Local Storage" value="Android Keystore" />
          <Row label="Evidence Integrity" value="SHA-256 hashing" />
          <Row label="Policy Version" value="v1" />
        </Section>

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
  rowValue: { color: colors.textPrimary, fontSize: 13, fontWeight: '600', maxWidth: '60%', textAlign: 'right' },
  rowDesc: { color: colors.textMuted, fontSize: 11, marginTop: 2 },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  modeSelector: {
    flexDirection: 'row',
    backgroundColor: colors.bgElevated,
    padding: 4,
    borderRadius: radius.sm,
    margin: spacing.sm,
    gap: 4,
  },
  modeBtn: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: radius.sm,
  },
  modeBtnActive: {
    backgroundColor: colors.brand,
  },
  modeBtnText: {
    color: colors.textSecondary,
    fontSize: 13,
    fontWeight: '600',
  },
  modeBtnTextActive: {
    color: colors.white,
    fontWeight: '700',
  },
  wifiConfigContainer: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    gap: spacing.sm,
  },
  inputRow: {
    gap: 4,
  },
  inputLabel: {
    color: colors.textSecondary,
    fontSize: 12,
    fontWeight: '600',
  },
  textInput: {
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    color: colors.textPrimary,
    fontSize: 14,
  },
  warningBox: {
    backgroundColor: `${colors.warning}18`,
    borderWidth: 1,
    borderColor: `${colors.warning}44`,
    borderRadius: radius.sm,
    padding: spacing.sm,
    marginTop: 2,
  },
  warningText: {
    color: colors.warning,
    fontSize: 12,
    fontWeight: '500',
  },
  testConnectionContainer: {
    padding: spacing.md,
    gap: spacing.sm,
  },
  testBtn: {
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.brand,
    borderRadius: radius.sm,
    paddingVertical: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  testBtnDisabled: {
    opacity: 0.6,
  },
  testBtnText: {
    color: colors.brandLight,
    fontSize: 13,
    fontWeight: '700',
  },
  statusBadge: {
    backgroundColor: colors.bgElevated,
    padding: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  statusBadgeSuccess: {
    backgroundColor: `${colors.success}18`,
    borderColor: `${colors.success}44`,
  },
  statusBadgeError: {
    backgroundColor: `${colors.error}18`,
    borderColor: `${colors.error}44`,
  },
  statusText: {
    fontSize: 12,
    color: colors.textSecondary,
    textAlign: 'center',
  },
  statusTextSuccess: {
    color: colors.success,
    fontWeight: '600',
  },
  statusTextError: {
    color: colors.error,
    fontWeight: '600',
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
