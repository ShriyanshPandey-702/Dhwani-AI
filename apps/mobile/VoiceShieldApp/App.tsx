/**
 * VoiceShield — React Native Entry Point
 * DETECT · SCORE · CHALLENGE · VERIFY · PROTECT
 */

import React, { useEffect, useState } from 'react';
import { StatusBar, useColorScheme } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AppNavigator } from './src/navigation/AppNavigator';
import { SplashScreen } from './src/screens/SplashScreen';
import { useConnectionStore } from './src/store/connectionStore';
import { colors } from './src/utils/theme';


function App(): React.JSX.Element {
  const [showSplash, setShowSplash] = useState(true);
  const { loadConfig } = useConnectionStore();

  useEffect(() => {
    loadConfig();
  }, []);

  if (showSplash) {
    return (
      <>
        <StatusBar barStyle="light-content" />
        <SplashScreen onFinish={() => setShowSplash(false)} />
      </>
    );
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <StatusBar barStyle="light-content" />
        <AppNavigator />
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

export default App;
