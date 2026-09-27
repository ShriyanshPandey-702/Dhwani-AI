/**
 * Dhwani AI — React Native Entry Point
 * Secure Calls. Trusted People.
 */

import React, { useEffect, useState } from "react";
import { StatusBar } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AppNavigator } from "./src/navigation/AppNavigator";
import { SplashScreen } from "./src/screens/SplashScreen";
import { useConnectionStore } from "./src/store/connectionStore";
import { useTheme } from "./src/utils/theme";

function MainApp(): React.JSX.Element {
  const [showSplash, setShowSplash] = useState(true);
  const { loadConfig } = useConnectionStore();
  const { isDark } = useTheme();

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  if (showSplash) {
    return (
      <>
        <StatusBar barStyle={isDark ? "light-content" : "dark-content"} />
        <SplashScreen onFinish={() => setShowSplash(false)} />
      </>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar barStyle={isDark ? "light-content" : "dark-content"} />
        <AppNavigator />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

export default MainApp;
