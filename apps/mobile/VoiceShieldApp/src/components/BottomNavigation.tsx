import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { useNavigation } from "@react-navigation/native";
import { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { RootStackParamList } from "../navigation/AppNavigator";

import { HomeIcon, PhoneIcon, MicIcon, DeviceIcon, SettingsIcon } from "./Icons";

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

  return (
    <View
      style={[
        styles.bar,
        {
          backgroundColor: isDark ? colors.surface : colors.surface,
          borderTopColor: colors.border,
          paddingBottom: Math.max(insets.bottom, 10),
        },
      ]}
    >
      {/* 1. Home Tab */}
      <TouchableOpacity
        activeOpacity={0.7}
        onPress={() => handleTabPress("home")}
        style={styles.tabButton}
        accessibilityRole="tab"
        accessibilityState={{ selected: activeTab === "home" }}
        accessibilityLabel="Home tab"
      >
        <HomeIcon
          size={20}
          color={activeTab === "home" ? colors.accent : colors.textMuted}
        />
        <Text
          style={[
            styles.tabLabel,
            {
              color: activeTab === "home" ? colors.accent : colors.textMuted,
              fontWeight: activeTab === "home" ? "700" : "500",
            },
          ]}
        >
          Home
        </Text>
      </TouchableOpacity>

      {/* 2. Calls Tab */}
      <TouchableOpacity
        activeOpacity={0.7}
        onPress={() => handleTabPress("calls")}
        style={styles.tabButton}
        accessibilityRole="tab"
        accessibilityState={{ selected: activeTab === "calls" }}
        accessibilityLabel="Calls tab"
      >
        <PhoneIcon
          size={20}
          color={activeTab === "calls" ? colors.accent : colors.textMuted}
        />
        <Text
          style={[
            styles.tabLabel,
            {
              color: activeTab === "calls" ? colors.accent : colors.textMuted,
              fontWeight: activeTab === "calls" ? "700" : "500",
            },
          ]}
        >
          Calls
        </Text>
      </TouchableOpacity>

      {/* 3. Central Live Analysis Tab (Prominent Raised Button per design.md Section 11) */}
      <TouchableOpacity
        activeOpacity={0.85}
        onPress={() => handleTabPress("analyze")}
        style={styles.centerTabButton}
        accessibilityRole="tab"
        accessibilityState={{ selected: activeTab === "analyze" }}
        accessibilityLabel="Live Voice Analysis tab"
      >
        <View
          style={[
            styles.centerOrb,
            {
              backgroundColor: colors.accent,
              shadowColor: colors.accent,
            },
          ]}
        >
          <MicIcon size={22} color="#FFFFFF" strokeWidth={2.2} />
        </View>
        <Text
          style={[
            styles.centerLabel,
            {
              color: activeTab === "analyze" ? colors.accent : colors.textMuted,
              fontWeight: activeTab === "analyze" ? "700" : "600",
            },
          ]}
        >
          Analyze
        </Text>
      </TouchableOpacity>

      {/* 4. Device Tab */}
      <TouchableOpacity
        activeOpacity={0.7}
        onPress={() => handleTabPress("device")}
        style={styles.tabButton}
        accessibilityRole="tab"
        accessibilityState={{ selected: activeTab === "device" }}
        accessibilityLabel="Device tab"
      >
        <DeviceIcon
          size={20}
          color={activeTab === "device" ? colors.accent : colors.textMuted}
        />
        <Text
          style={[
            styles.tabLabel,
            {
              color: activeTab === "device" ? colors.accent : colors.textMuted,
              fontWeight: activeTab === "device" ? "700" : "500",
            },
          ]}
        >
          Device
        </Text>
      </TouchableOpacity>

      {/* 5. Settings Tab */}
      <TouchableOpacity
        activeOpacity={0.7}
        onPress={() => handleTabPress("settings")}
        style={styles.tabButton}
        accessibilityRole="tab"
        accessibilityState={{ selected: activeTab === "settings" }}
        accessibilityLabel="Settings tab"
      >
        <SettingsIcon
          size={20}
          color={activeTab === "settings" ? colors.accent : colors.textMuted}
        />
        <Text
          style={[
            styles.tabLabel,
            {
              color: activeTab === "settings" ? colors.accent : colors.textMuted,
              fontWeight: activeTab === "settings" ? "700" : "500",
            },
          ]}
        >
          Settings
        </Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    borderTopWidth: 1,
    paddingTop: 6,
    elevation: 10,
    shadowColor: "#000000",
    shadowOffset: { width: 0, height: -3 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    alignItems: "flex-end",
  },
  tabButton: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 4,
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
  centerTabButton: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    top: -12,
  },
  centerOrb: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.35,
    shadowRadius: 6,
    elevation: 6,
  },
  centerIcon: {
    fontSize: 22,
  },
  centerLabel: {
    fontSize: 11,
    marginTop: 3,
    letterSpacing: 0.2,
  },
});
