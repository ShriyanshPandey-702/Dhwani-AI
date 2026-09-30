import React from "react";
import { View, StyleSheet, Dimensions } from "react-native";
import { useTheme } from "../utils/theme";

const { width, height } = Dimensions.get("window");

interface BackgroundWaveProps {
  opacity?: number;
}

export const BackgroundWave: React.FC<BackgroundWaveProps> = ({ opacity = 1 }) => {
  const { isDark, colors } = useTheme();

  return (
    <View style={[StyleSheet.absoluteFill, styles.container, { opacity }]} pointerEvents="none">
      {/* Wave Blob 1 - Top Right (Cyan/Blue in Dark, Soft Lavender/Blue in Light) */}
      <View
        style={[
          styles.blob,
          styles.blobTopRight,
          {
            backgroundColor: isDark ? "#22D3EE" : "#BFDBFE",
            opacity: isDark ? 0.07 : 0.25,
          },
        ]}
      />

      {/* Wave Blob 2 - Center Left (Purple in Dark, Pastel Pink/Blush in Light) */}
      <View
        style={[
          styles.blob,
          styles.blobCenterLeft,
          {
            backgroundColor: isDark ? "#8B5CF6" : "#FBCFE8",
            opacity: isDark ? 0.06 : 0.22,
          },
        ]}
      />

      {/* Wave Blob 3 - Bottom Right (Coral/Teal in Dark, Soft Mint/Cyan in Light) */}
      <View
        style={[
          styles.blob,
          styles.blobBottomRight,
          {
            backgroundColor: isDark ? "#5FD0C5" : "#CCFBF1",
            opacity: isDark ? 0.08 : 0.3,
          },
        ]}
      />

      {/* Subtle curved wave line overlay */}
      <View
        style={[
          styles.waveArc1,
          {
            borderColor: isDark ? "rgba(95, 208, 197, 0.08)" : "rgba(37, 99, 235, 0.05)",
          },
        ]}
      />
      <View
        style={[
          styles.waveArc2,
          {
            borderColor: isDark ? "rgba(139, 92, 246, 0.06)" : "rgba(231, 111, 81, 0.05)",
          },
        ]}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    overflow: "hidden",
  },
  blob: {
    position: "absolute",
    borderRadius: 9999,
  },
  blobTopRight: {
    width: width * 0.9,
    height: width * 0.9,
    top: -width * 0.3,
    right: -width * 0.3,
  },
  blobCenterLeft: {
    width: width * 0.85,
    height: width * 0.85,
    top: height * 0.35,
    left: -width * 0.4,
  },
  blobBottomRight: {
    width: width * 0.8,
    height: width * 0.8,
    bottom: -width * 0.25,
    right: -width * 0.25,
  },
  waveArc1: {
    position: "absolute",
    width: width * 1.5,
    height: width * 1.5,
    borderRadius: width * 0.75,
    borderWidth: 1.5,
    top: -width * 0.2,
    left: -width * 0.25,
  },
  waveArc2: {
    position: "absolute",
    width: width * 1.6,
    height: width * 1.6,
    borderRadius: width * 0.8,
    borderWidth: 1.5,
    bottom: -width * 0.3,
    right: -width * 0.3,
  },
});
