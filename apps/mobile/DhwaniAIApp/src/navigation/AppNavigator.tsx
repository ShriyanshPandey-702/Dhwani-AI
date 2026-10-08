import React from "react";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { useTheme } from "../utils/theme";

import { LoginScreen } from "../screens/LoginScreen";
import { HomeScreen } from "../screens/HomeScreen";
import { CallScreen } from "../screens/CallScreen";
import { ChallengeScreen } from "../screens/ChallengeScreen";
import { VerificationScreen } from "../screens/VerificationScreen";
import { IncidentHistoryScreen } from "../screens/IncidentHistoryScreen";
import { IncidentDetailScreen } from "../screens/IncidentDetailScreen";
import { DeviceTrustScreen } from "../screens/DeviceTrustScreen";
import { SettingsScreen } from "../screens/SettingsScreen";
import { ManualAnalysisScreen } from "../screens/ManualAnalysisScreen";
import { CallSecurityDetailsScreen } from "../screens/CallSecurityDetailsScreen";
import { IntegrationHubScreen } from "../screens/IntegrationHubScreen";
import { ScreenedCallEvent } from "../types/telecom";

export type RootStackParamList = {
  Login?: undefined;
  Home: undefined;
  Call: {
    sessionId: string;
    mode?: "mock" | "live" | "recording";
    source?: string;
    callerNumber?: string;
    callerName?: string;
  };
  Challenge: { sessionId: string };
  Verification: { sessionId: string };
  Incidents: undefined;
  IncidentDetail: { incidentId: string };
  Devices: undefined;
  Settings: undefined;
  ManualAnalysis: undefined;
  CallSecurityDetails: { callRecord: ScreenedCallEvent };
  IntegrationHub: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

export const AppNavigator: React.FC = () => {
  const { colors, isDark } = useTheme();

  return (
    <NavigationContainer>
      <Stack.Navigator
        initialRouteName="Home"
        screenOptions={{
          headerShown: false,
          contentStyle: {
            backgroundColor: isDark ? colors.background : colors.background,
          },
          animation: "fade_from_bottom",
        }}
      >
        <Stack.Screen name="Home" component={HomeScreen} />
        <Stack.Screen name="Call" component={CallScreen} />
        <Stack.Screen name="Challenge" component={ChallengeScreen} />
        <Stack.Screen name="Verification" component={VerificationScreen} />
        <Stack.Screen name="Incidents" component={IncidentHistoryScreen} />
        <Stack.Screen name="IncidentDetail" component={IncidentDetailScreen} />
        <Stack.Screen name="Devices" component={DeviceTrustScreen} />
        <Stack.Screen name="Settings" component={SettingsScreen} />
        <Stack.Screen name="ManualAnalysis" component={ManualAnalysisScreen} />
        <Stack.Screen name="CallSecurityDetails" component={CallSecurityDetailsScreen} />
        <Stack.Screen name="IntegrationHub" component={IntegrationHubScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
};
