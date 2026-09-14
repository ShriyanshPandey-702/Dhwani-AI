/* Test environment setup for the VoiceShield mobile app. */

require('react-native-gesture-handler/jestSetup');

// AsyncStorage has no native module under Jest; use the mock it ships.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest'),
);

// Keep test output focused on assertions rather than RN warnings.
jest.spyOn(console, 'warn').mockImplementation(() => {});
