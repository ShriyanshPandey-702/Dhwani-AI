module.exports = {
  preset: '@react-native/jest-preset',

  // Helper modules under __tests__ are fixtures, not suites.
  testPathIgnorePatterns: ['<rootDir>/node_modules/', '<rootDir>/__tests__/helpers/'],

  // These packages ship untranspiled ESM and must go through Babel.
  transformIgnorePatterns: [
    'node_modules/(?!(?:@react-native-async-storage|@react-native|react-native|react-native-gesture-handler|react-native-reanimated|react-native-screens|react-native-safe-area-context|@react-navigation)/)',
  ],

  setupFiles: ['<rootDir>/jest.setup.js'],
};
