import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { RootStackParamList } from "../navigation/AppNavigator";

export type BottomTabKey = "home" | "calls" | "analyze" | "device" | "settings";

interface BottomNavigationProps {
  activeTab: BottomTabKey;
}

type Nav = NativeStackNavigationProp<RootStackParamList>;

export const BottomNavigation: React.FC<BottomNavigationProps> = ({ activeTab }) => {
  const navigation = useNavigation<Nav>();
  const insets = useSafeAreaInsets();
  const { colors, isDark } = useTheme();

  const handleTabPress = (tab: BottomTabKey) => {
    if (tab === activeTab) return;
    switch (tab) {
      case "home":
        navigation.navigate("Home");
        break;
      case "calls":
        navigation.navigate("Incidents");
        break;
      case "analyze":
        navigation.navigate("ManualAnalysis");
        break;
      case "device":
        navigation.navigate("Devices");
        break;
      case "settings":
        navigation.navigate("Settings");
        break;
    }
  };

  const tabs: { key: BottomTabKey; label: string; icon: string }[] = [
    { key: "home", label: "Home", icon: "⌂" },
    { key: "calls", label: "Calls", icon: "☎" },
    { key: "analyze", label: "Analyze", icon: "⚡" },
    { key: "device", label: "Device", icon: "📱" },
    { key: "settings", label: "Settings", icon: "⚙" },
  ];

  return (
    <View
      style={[
        styles.bar,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderTopColor: colors.border,
          paddingBottom: Math.max(insets.bottom, 12),
        },
      ]}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.key;
        const color = isActive ? colors.accent : colors.textMuted;

        return (
          <TouchableOpacity
            key={tab.key}
            activeOpacity={0.7}
            onPress={() => handleTabPress(tab.key)}
            style={styles.tabButton}
            accessibilityRole="tab"
            accessibilityState={{ selected: isActive }}
            accessibilityLabel={`${tab.label} tab`}
          >
            <View style={styles.iconWrapper}>
              <Text style={[styles.iconText, { color }]}>{tab.icon}</Text>
            </View>
            <Text
              style={[
                styles.tabLabel,
                {
                  color,
                  fontWeight: isActive ? "700" : "500",
                },
              ]}
            >
              {tab.label}
            </Text>
            {isActive && (
              <View
                style={[
                  styles.activeIndicator,
                  { backgroundColor: colors.accent },
                ]}
              />
            )}
          </TouchableOpacity>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    borderTopWidth: 1,
    paddingTop: 8,
    elevation: 8,
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
  },
  tabButton: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
    paddingVertical: 4,
  },
  iconWrapper: {
    height: 22,
    alignItems: "center",
    justifyContent: "center",
  },
  iconText: {
    fontSize: 18,
    lineHeight: 22,
  },
  tabLabel: {
    fontSize: 11,
    marginTop: 2,
    letterSpacing: 0.2,
  },
  activeIndicator: {
    position: "absolute",
    top: -8,
    width: 20,
    height: 2.5,
    borderRadius: 2,
  },
});
