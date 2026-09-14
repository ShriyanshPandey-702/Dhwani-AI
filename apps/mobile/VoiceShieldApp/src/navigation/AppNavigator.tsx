import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { colors } from '../utils/theme';

import { LoginScreen } from '../screens/LoginScreen';
import { HomeScreen } from '../screens/HomeScreen';
import { CallScreen } from '../screens/CallScreen';
import { ChallengeScreen } from '../screens/ChallengeScreen';
import { VerificationScreen } from '../screens/VerificationScreen';
import { IncidentHistoryScreen } from '../screens/IncidentHistoryScreen';
import { IncidentDetailScreen } from '../screens/IncidentDetailScreen';
import { DeviceTrustScreen } from '../screens/DeviceTrustScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { useAuthStore } from '../store/authStore';

export type RootStackParamList = {
  Login: undefined;
  Home: undefined;
  Call: { sessionId: string; mode?: 'mock' | 'live' };
  Challenge: { sessionId: string };
  Verification: { sessionId: string };
  Incidents: undefined;
  IncidentDetail: { incidentId: string };
  Devices: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export const AppNavigator: React.FC = () => {
  const { isAuthenticated } = useAuthStore();

  return (
    <NavigationContainer>
      <Stack.Navigator
        screenOptions={{
          headerStyle: { backgroundColor: colors.bgCard },
          headerTintColor: colors.textPrimary,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.bg },
          headerTitleStyle: { fontWeight: '700' },
        }}>
        {!isAuthenticated ? (
          <Stack.Screen name="Login" component={LoginScreen} options={{ headerShown: false }} />
        ) : (
          <>
            <Stack.Screen name="Home" component={HomeScreen} options={{ headerShown: false }} />
            <Stack.Screen name="Call" component={CallScreen}
              options={{ title: 'Monitoring', headerBackTitle: 'End' }} />
            <Stack.Screen name="Challenge" component={ChallengeScreen}
              options={{ title: 'Voice Challenge' }} />
            <Stack.Screen name="Verification" component={VerificationScreen}
              options={{ title: 'Verification' }} />
            <Stack.Screen name="Incidents" component={IncidentHistoryScreen}
              options={{ title: 'Incident History' }} />
            <Stack.Screen name="IncidentDetail" component={IncidentDetailScreen}
              options={{ title: 'Incident Details' }} />
            <Stack.Screen name="Devices" component={DeviceTrustScreen}
              options={{ title: 'Trusted Devices' }} />
            <Stack.Screen name="Settings" component={SettingsScreen}
              options={{ title: 'Settings' }} />
          </>
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
};
