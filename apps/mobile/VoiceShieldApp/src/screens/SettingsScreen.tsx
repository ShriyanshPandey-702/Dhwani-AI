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
  Alert,
} from 'react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { colors, spacing, radius, typography } from '../utils/theme';
import {
  useConnectionStore,
  getApiBaseUrl,
  getWsBaseUrl,
} from '../store/connectionStore';
import { useCallScreeningStore } from '../store/callScreeningStore';
import { callScreeningService } from '../services/telecom/callScreeningService';

export const SettingsScreen: React.FC = () => {
  const navigation = useNavigation();
  const [pushEnabled, setPushEnabled] = React.useState(true);
  const [rawAudioEnabled, setRawAudioEnabled] = React.useState(false);

  const isRoleHeld = useCallScreeningStore(s => s.isRoleHeld);
  const checkRoleStatus = useCallScreeningStore(s => s.checkRoleStatus);
  const requestRole = useCallScreeningStore(s => s.requestRole);
  const openSettings = useCallScreeningStore(s => s.openSettings);
  const isRoleLoading = useCallScreeningStore(s => s.isLoading);

  const [hasContactsPermission, setHasContactsPermission] = React.useState<boolean | null>(null);

  useFocusEffect(
    React.useCallback(() => {
      checkRoleStatus();
      // Check contacts permission status on focus
      callScreeningService.hasContactsPermission?.().then(granted => {
        setHasContactsPermission(granted);
      }).catch(() => setHasContactsPermission(false));
    }, [checkRoleStatus]),
  );

  const handleTestNotification = async () => {
    try {
      await callScreeningService.testSecurityNotification();
      Alert.alert('Notification Sent', 'A local test security alert was sent. Check your notifications shade.');
    } catch (err: any) {
      Alert.alert('Notification Test Failed', err?.message || 'Could not send test notification.');
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

        {/* Call Screening Protection */}
        <Section title="Call Screening Protection">
          <Row
            label="Protection Status"
            value={isRoleHeld ? 'Active' : 'Inactive'}
          />
          {!isRoleHeld ? (
            <TouchableOpacity
              onPress={() => requestRole()}
              style={styles.enableRoleBtn}
              disabled={isRoleLoading}
              accessibilityLabel="Enable Call Screening"
              accessibilityRole="button">
              {isRoleLoading ? (
                <ActivityIndicator color={colors.white} />
              ) : (
                <Text style={styles.enableRoleBtnText}>Enable Call Screening</Text>
              )}
            </TouchableOpacity>
          ) : (
            <View style={styles.roleControlsContainer}>
              <View style={styles.activeBadge}>
                <Text style={styles.activeBadgeText}>● Active</Text>
              </View>

              <TouchableOpacity
                onPress={() => openSettings()}
                style={styles.roleActionBtn}
                disabled={isRoleLoading}
                accessibilityLabel="Change Call Screening App"
                accessibilityRole="button">
                <Text style={styles.roleActionBtnText}>Change Call Screening App</Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => openSettings()}
                style={[styles.roleActionBtn, styles.roleDisableBtn]}
                disabled={isRoleLoading}
                accessibilityLabel="Disable VoiceShield Screening"
                accessibilityRole="button">
                <Text style={styles.roleDisableBtnText}>Disable VoiceShield Screening</Text>
              </TouchableOpacity>
            </View>
          )}
          <Text style={styles.roleExplanation}>
            Android requires user control over call screening. To change or disable VoiceShield, select 'Caller ID & spam app' in Android system settings.
          </Text>
        </Section>

        {/* Contacts Permission */}
        <Section title="Contacts Permission">
          <Row
            label="Status"
            value={
              hasContactsPermission === null
                ? 'Checking…'
                : hasContactsPermission
                ? '✅ Granted'
                : '⚠️ Not Granted'
            }
          />
          <Text style={styles.roleExplanation}>
            Allow VoiceShield to detect known contacts so calls from friends and family are
            recognized as safe and screened seamlessly. Without this permission, all calls
            appear as "unknown" to the screening service.
          </Text>
          {!hasContactsPermission && hasContactsPermission !== null && (
            <Text style={styles.roleExplanation}>
              To grant access: Android Settings → Apps → VoiceShield → Permissions → Contacts.
            </Text>
          )}
        </Section>

        {/* Notifications */}
        <Section title="Notifications">
          <ToggleRow
            label="Security Alerts"
            value={pushEnabled}
            onChange={setPushEnabled}
            description="Receive push alerts for high-risk events"
          />
          <TouchableOpacity
            onPress={handleTestNotification}
            style={styles.testNotificationBtn}
            accessibilityLabel="Test Security Notification"
            accessibilityRole="button">
            <Text style={styles.testNotificationBtnText}>🔔  Test Security Notification</Text>
          </TouchableOpacity>
          <Text style={styles.testNotificationDesc}>
            Fires a local test alert to verify heads-up display, sound, and notification permission. (Does not affect dashboard stats or create call records).
          </Text>
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
  enableRoleBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 12,
    alignItems: 'center',
    marginHorizontal: spacing.md,
    marginVertical: spacing.sm,
  },
  enableRoleBtnText: {
    color: colors.white,
    fontWeight: '700',
    fontSize: 14,
  },
  activeBadge: {
    backgroundColor: `${colors.success}18`,
    borderColor: `${colors.success}44`,
    borderWidth: 1,
    borderRadius: radius.sm,
    paddingVertical: 8,
    paddingHorizontal: spacing.md,
    marginHorizontal: spacing.md,
    marginVertical: spacing.xs,
    alignItems: 'center',
  },
  activeBadgeText: {
    color: colors.success,
    fontWeight: '700',
    fontSize: 13,
  },
  roleExplanation: {
    color: colors.textMuted,
    fontSize: 12,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    lineHeight: 16,
  },
  roleControlsContainer: {
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xs,
    gap: spacing.xs,
  },
  roleActionBtn: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.sm,
    paddingVertical: 10,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
  },
  roleActionBtnText: {
    color: colors.brand,
    fontWeight: '700',
    fontSize: 13,
  },
  roleDisableBtn: {
    backgroundColor: `${colors.error}10`,
    borderColor: `${colors.error}33`,
  },
  roleDisableBtnText: {
    color: colors.error,
    fontWeight: '700',
    fontSize: 13,
  },
  testNotificationBtn: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.sm,
    paddingVertical: 10,
    alignItems: 'center',
    marginHorizontal: spacing.md,
    marginTop: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
  },
  testNotificationBtnText: {
    color: colors.brand,
    fontWeight: '700',
    fontSize: 13,
  },
  testNotificationDesc: {
    color: colors.textMuted,
    fontSize: 11,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.xs,
    paddingBottom: spacing.sm,
    lineHeight: 15,
  },
});
