module.exports = {
  presets: ['module:@react-native/babel-preset'],
  // react-native-reanimated v4 runs its worklets through this plugin.
  // It must stay last in the plugin list.
  plugins: ['react-native-worklets/plugin'],
};
