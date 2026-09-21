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
import { ManualAnalysisScreen } from '../screens/ManualAnalysisScreen';
import { CallSecurityDetailsScreen } from '../screens/CallSecurityDetailsScreen';
import { ScreenedCallEvent } from '../types/telecom';

export type RootStackParamList = {
  Login?: undefined;
  Home: undefined;
  Call: { sessionId: string; mode?: 'mock' | 'live' };
  Challenge: { sessionId: string };
  Verification: { sessionId: string };
  Incidents: undefined;
  IncidentDetail: { incidentId: string };
  Devices: undefined;
  Settings: undefined;
  ManualAnalysis: undefined;
  CallSecurityDetails: { callRecord: ScreenedCallEvent };
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export const AppNavigator: React.FC = () => {
  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Home"
        screenOptions={{
          headerStyle: { backgroundColor: colors.bgCard },
          headerTintColor: colors.textPrimary,
          headerShadowVisible: false,
          contentStyle: { backgroundColor: colors.bg },
          headerTitleStyle: { fontWeight: '700' },
        }}>
        <Stack.Screen name="Home" component={HomeScreen} options={{ headerShown: false }} />
        <Stack.Screen
          name="Call"
          component={CallScreen}
          options={{ title: 'Monitoring', headerBackTitle: 'End' }}
        />
        <Stack.Screen
          name="Challenge"
          component={ChallengeScreen}
          options={{ title: 'Voice Challenge' }}
        />
        <Stack.Screen
          name="Verification"
          component={VerificationScreen}
          options={{ title: 'Verification' }}
        />
        <Stack.Screen
          name="Incidents"
          component={IncidentHistoryScreen}
          options={{ title: 'Incident History' }}
        />
        <Stack.Screen
          name="IncidentDetail"
          component={IncidentDetailScreen}
          options={{ title: 'Incident Details' }}
        />
        <Stack.Screen
          name="Devices"
          component={DeviceTrustScreen}
          options={{ title: 'Trusted Devices' }}
        />
        <Stack.Screen
          name="Settings"
          component={SettingsScreen}
          options={{ title: 'Settings' }}
        />
        <Stack.Screen
          name="ManualAnalysis"
          component={ManualAnalysisScreen}
          options={{ title: 'Manual Analysis' }}
        />
        <Stack.Screen
          name="CallSecurityDetails"
          component={CallSecurityDetailsScreen}
          options={{ headerShown: false }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  );
};
