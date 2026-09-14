import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Alert, ActivityIndicator,
} from 'react-native';
import { colors, spacing, radius, typography } from '../utils/theme';
import { DeviceData } from '../types';
import client from '../services/api/client';

export const DeviceTrustScreen: React.FC = () => {
  const [devices, setDevices] = useState<DeviceData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [registering, setRegistering] = useState(false);

  const load = async () => {
    const { data } = await client.get<DeviceData[]>('/devices');
    setDevices(data);
  };

  useEffect(() => {
    load().catch(console.error).finally(() => setIsLoading(false));
  }, []);

  const registerDevice = async () => {
    setRegistering(true);
    try {
      const { data } = await client.post('/devices/register', {
        device_name: 'My Android Device',
        platform: 'android',
      });
      Alert.alert(
        'Device Registered ✓',
        `Store this token securely in Android Keystore:\n\n${data.device_token}`,
        [{ text: 'OK', onPress: load }]
      );
    } catch (e) {
      Alert.alert('Error', 'Failed to register device');
    } finally {
      setRegistering(false);
    }
  };

  const revokeDevice = (deviceId: string) => {
    Alert.alert('Revoke Device', 'This device will no longer be able to approve verifications.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Revoke', style: 'destructive',
        onPress: async () => {
          await client.delete(`/devices/${deviceId}`);
          load();
        },
      },
    ]);
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.title}>Trusted Devices</Text>
        <Text style={styles.subtitle}>
          Your trusted devices can approve OOB verification requests. A device must be separate
          from the suspected call channel.
        </Text>

        <TouchableOpacity
          style={[styles.registerBtn, registering && styles.disabled]}
          onPress={registerDevice}
          disabled={registering}
          accessibilityLabel="Register this device as trusted"
          accessibilityRole="button">
          {registering ? <ActivityIndicator color={colors.white} /> :
            <Text style={styles.registerBtnText}>+ Register This Device</Text>}
        </TouchableOpacity>

        {isLoading ? (
          <ActivityIndicator color={colors.brand} style={{ marginTop: 32 }} />
        ) : devices.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No trusted devices registered yet.</Text>
          </View>
        ) : (
          devices.map(d => (
            <View key={d.id} style={styles.deviceCard}>
              <View style={styles.deviceLeft}>
                <Text style={styles.deviceIcon}>📱</Text>
                <View>
                  <Text style={styles.deviceName}>{d.device_name}</Text>
                  <Text style={styles.deviceMeta}>{d.platform} · {d.is_active ? 'Active' : 'Revoked'}</Text>
                </View>
              </View>
              <TouchableOpacity
                style={styles.revokeBtn}
                onPress={() => revokeDevice(d.id)}
                accessibilityLabel={`Revoke device ${d.device_name}`}
                accessibilityRole="button">
                <Text style={styles.revokeBtnText}>Revoke</Text>
              </TouchableOpacity>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.md },
  title: { ...typography.h2 },
  subtitle: { color: colors.textSecondary, fontSize: 14, lineHeight: 20 },
  registerBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.md,
    paddingVertical: 14, alignItems: 'center',
  },
  disabled: { opacity: 0.6 },
  registerBtnText: { color: colors.white, fontWeight: '700', fontSize: 15 },
  empty: { alignItems: 'center', padding: spacing.xl },
  emptyText: { color: colors.textMuted, fontSize: 14 },
  deviceCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1, borderColor: colors.border,
  },
  deviceLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  deviceIcon: { fontSize: 28 },
  deviceName: { fontWeight: '700', color: colors.textPrimary, fontSize: 15 },
  deviceMeta: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  revokeBtn: {
    paddingHorizontal: 12, paddingVertical: 6,
    borderRadius: radius.full,
    backgroundColor: `${colors.error}18`,
    borderWidth: 1, borderColor: `${colors.error}44`,
  },
  revokeBtnText: { color: colors.error, fontWeight: '700', fontSize: 12 },
});
