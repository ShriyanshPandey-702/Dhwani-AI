import React from "react";
import { View, StyleSheet, ViewStyle } from "react-native";

export interface IconProps {
  size?: number;
  color?: string;
  strokeWidth?: number;
  style?: ViewStyle;
}

/**
 * Clean, lightweight, scalable vector icons rendered using React Native native primitives.
 * Provides 100% consistent cross-platform strokes, supports dynamic theming,
 * scales smoothly, and does not depend on device emoji fonts.
 */

// 1. Microphone Icon
export const MicIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const capWidth = size * 0.36;
  const capHeight = size * 0.52;
  const cradleWidth = size * 0.62;
  const cradleHeight = size * 0.44;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Microphone Capsule */}
      <View
        style={{
          width: capWidth,
          height: capHeight,
          borderRadius: capWidth / 2,
          borderWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          top: size * 0.08,
        }}
      />
      {/* U-Shape Cradle Arc */}
      <View
        style={{
          width: cradleWidth,
          height: cradleHeight,
          borderBottomLeftRadius: cradleWidth / 2,
          borderBottomRightRadius: cradleWidth / 2,
          borderLeftWidth: strokeWidth,
          borderRightWidth: strokeWidth,
          borderBottomWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          top: size * 0.24,
        }}
      />
      {/* Stem */}
      <View
        style={{
          width: strokeWidth,
          height: size * 0.18,
          backgroundColor: color,
          position: "absolute",
          bottom: size * 0.12,
        }}
      />
      {/* Base Bar */}
      <View
        style={{
          width: size * 0.44,
          height: strokeWidth,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
          bottom: size * 0.12,
        }}
      />
    </View>
  );
};

// 2. Notification / Bell Icon
export const BellIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const domeWidth = size * 0.56;
  const domeHeight = size * 0.48;
  const rimWidth = size * 0.74;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Top hanger loop */}
      <View
        style={{
          width: size * 0.16,
          height: size * 0.12,
          borderRadius: (size * 0.16) / 2,
          borderWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          top: size * 0.10,
        }}
      />
      {/* Dome */}
      <View
        style={{
          width: domeWidth,
          height: domeHeight,
          borderTopLeftRadius: domeWidth / 2,
          borderTopRightRadius: domeWidth / 2,
          borderLeftWidth: strokeWidth,
          borderRightWidth: strokeWidth,
          borderTopWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          top: size * 0.18,
        }}
      />
      {/* Bottom Rim Bar */}
      <View
        style={{
          width: rimWidth,
          height: strokeWidth,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
          top: size * 0.66,
        }}
      />
      {/* Clapper */}
      <View
        style={{
          width: size * 0.20,
          height: size * 0.14,
          borderBottomLeftRadius: (size * 0.20) / 2,
          borderBottomRightRadius: (size * 0.20) / 2,
          backgroundColor: color,
          position: "absolute",
          bottom: size * 0.10,
        }}
      />
    </View>
  );
};

// 3. Phone / Call Icon (Ringing Telephone Handset with Waves)
export const PhoneIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const waveStroke = Math.max(strokeWidth * 0.9, 1.8);
  const outerWave = size * 0.52;
  const innerWave = size * 0.32;
  const handsetSpine = size * 0.44;
  const handsetStroke = Math.max(strokeWidth * 1.5, 3);
  const earW = size * 0.28;
  const earH = size * 0.16;

  return (
    <View
      style={[
        { width: size, height: size, alignItems: "center", justifyContent: "center" },
        style,
      ]}
    >
      {/* Outer Sound Wave Arc (Top Right) */}
      <View
        style={{
          position: "absolute",
          top: size * 0.04,
          right: size * 0.04,
          width: outerWave,
          height: outerWave,
          borderTopRightRadius: outerWave,
          borderTopWidth: waveStroke,
          borderRightWidth: waveStroke,
          borderColor: color,
        }}
      />

      {/* Inner Sound Wave Arc (Top Right) */}
      <View
        style={{
          position: "absolute",
          top: size * 0.18,
          right: size * 0.18,
          width: innerWave,
          height: innerWave,
          borderTopRightRadius: innerWave,
          borderTopWidth: waveStroke,
          borderRightWidth: waveStroke,
          borderColor: color,
        }}
      />

      {/* Handset Curved Spine (Bottom Left) */}
      <View
        style={{
          position: "absolute",
          bottom: size * 0.06,
          left: size * 0.06,
          width: handsetSpine,
          height: handsetSpine,
          borderBottomLeftRadius: handsetSpine * 0.7,
          borderLeftWidth: handsetStroke,
          borderBottomWidth: handsetStroke,
          borderColor: color,
          backgroundColor: "transparent",
        }}
      />

      {/* Top Earpiece Capsule */}
      <View
        style={{
          position: "absolute",
          top: size * 0.36,
          left: size * 0.02,
          width: earW,
          height: earH,
          borderRadius: earH / 2,
          backgroundColor: color,
          transform: [{ rotate: "-40deg" }],
        }}
      />

      {/* Bottom Mouthpiece Capsule */}
      <View
        style={{
          position: "absolute",
          bottom: size * 0.02,
          left: size * 0.36,
          width: earW,
          height: earH,
          borderRadius: earH / 2,
          backgroundColor: color,
          transform: [{ rotate: "-40deg" }],
        }}
      />
    </View>
  );
};

// 4. Device / Mobile Phone Icon
export const DeviceIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const phoneWidth = size * 0.54;
  const phoneHeight = size * 0.82;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      <View
        style={{
          width: phoneWidth,
          height: phoneHeight,
          borderRadius: size * 0.12,
          borderWidth: strokeWidth,
          borderColor: color,
          alignItems: "center",
          justifyContent: "space-between",
          paddingVertical: size * 0.08,
        }}
      >
        {/* Top Speaker Notch */}
        <View
          style={{
            width: size * 0.18,
            height: strokeWidth,
            borderRadius: strokeWidth / 2,
            backgroundColor: color,
          }}
        />
        {/* Bottom Home Indicator */}
        <View
          style={{
            width: size * 0.14,
            height: strokeWidth,
            borderRadius: strokeWidth / 2,
            backgroundColor: color,
          }}
        />
      </View>
    </View>
  );
};

// 5. Home Icon (Clean Outlined Pitched Roof House with Door)
export const HomeIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const roofBoxSize = size * 0.52;
  const houseW = size * 0.60;
  const houseH = size * 0.42;
  const doorW = size * 0.20;
  const doorH = size * 0.22;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Pitched Roof (45-deg Outlined Chevron Peak) */}
      <View
        style={{
          width: roofBoxSize,
          height: roofBoxSize,
          borderTopWidth: strokeWidth,
          borderLeftWidth: strokeWidth,
          borderTopLeftRadius: size * 0.06,
          borderColor: color,
          position: "absolute",
          top: size * 0.12,
          transform: [{ rotate: "45deg" }],
        }}
      />
      {/* House Body Box */}
      <View
        style={{
          width: houseW,
          height: houseH,
          borderLeftWidth: strokeWidth,
          borderRightWidth: strokeWidth,
          borderBottomWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          bottom: size * 0.12,
          alignItems: "center",
          justifyContent: "flex-end",
          backgroundColor: "transparent",
        }}
      >
        {/* Centered Doorway */}
        <View
          style={{
            width: doorW,
            height: doorH,
            borderTopLeftRadius: doorW * 0.3,
            borderTopRightRadius: doorW * 0.3,
            borderLeftWidth: strokeWidth,
            borderRightWidth: strokeWidth,
            borderTopWidth: strokeWidth,
            borderColor: color,
          }}
        />
      </View>
    </View>
  );
};

// 6. Settings / Gear Icon
export const SettingsIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const outerRing = size * 0.68;
  const innerRing = size * 0.36;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Outer Gear Ring */}
      <View
        style={{
          width: outerRing,
          height: outerRing,
          borderRadius: outerRing / 2,
          borderWidth: strokeWidth * 1.5,
          borderColor: color,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/* Inner Hub Circle */}
        <View
          style={{
            width: innerRing,
            height: innerRing,
            borderRadius: innerRing / 2,
            borderWidth: strokeWidth,
            borderColor: color,
          }}
        />
      </View>
      {/* Vertical Teeth */}
      <View
        style={{
          width: strokeWidth * 1.5,
          height: size * 0.84,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
        }}
      />
      {/* Horizontal Teeth */}
      <View
        style={{
          width: size * 0.84,
          height: strokeWidth * 1.5,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
        }}
      />
      {/* Diagonal 45 Teeth */}
      <View
        style={{
          width: strokeWidth * 1.5,
          height: size * 0.84,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
          transform: [{ rotate: "45deg" }],
        }}
      />
      {/* Diagonal -45 Teeth */}
      <View
        style={{
          width: strokeWidth * 1.5,
          height: size * 0.84,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
          transform: [{ rotate: "-45deg" }],
        }}
      />
    </View>
  );
};

// 7. User / Profile Icon
export const UserIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const headSize = size * 0.34;
  const bodyWidth = size * 0.64;
  const bodyHeight = size * 0.32;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Head */}
      <View
        style={{
          width: headSize,
          height: headSize,
          borderRadius: headSize / 2,
          borderWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          top: size * 0.12,
        }}
      />
      {/* Shoulder Arc */}
      <View
        style={{
          width: bodyWidth,
          height: bodyHeight,
          borderTopLeftRadius: bodyWidth / 2,
          borderTopRightRadius: bodyWidth / 2,
          borderLeftWidth: strokeWidth,
          borderRightWidth: strokeWidth,
          borderTopWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          bottom: size * 0.12,
        }}
      />
    </View>
  );
};

// 8. Shield Icon
export const ShieldIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const width = size * 0.66;
  const height = size * 0.78;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      <View
        style={{
          width,
          height,
          borderTopLeftRadius: size * 0.14,
          borderTopRightRadius: size * 0.14,
          borderBottomLeftRadius: width / 2,
          borderBottomRightRadius: width / 2,
          borderWidth: strokeWidth,
          borderColor: color,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {/* Inner vertical spine */}
        <View
          style={{
            width: strokeWidth,
            height: height * 0.55,
            backgroundColor: color,
          }}
        />
      </View>
    </View>
  );
};

// 9. Folder / File Icon
export const FolderIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const bodyWidth = size * 0.72;
  const bodyHeight = size * 0.50;
  const tabWidth = size * 0.32;
  const tabHeight = size * 0.14;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Folder Tab */}
      <View
        style={{
          width: tabWidth,
          height: tabHeight,
          borderTopLeftRadius: size * 0.06,
          borderTopRightRadius: size * 0.06,
          backgroundColor: color,
          position: "absolute",
          top: size * 0.18,
          left: size * 0.14,
        }}
      />
      {/* Main Folder Body */}
      <View
        style={{
          width: bodyWidth,
          height: bodyHeight,
          borderRadius: size * 0.08,
          borderWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          bottom: size * 0.18,
        }}
      />
    </View>
  );
};

// 10. Alert Triangle Icon
export const AlertTriangleIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#F59E0B",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Exclamation point line */}
      <View
        style={{
          width: strokeWidth,
          height: size * 0.36,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
          top: size * 0.24,
        }}
      />
      {/* Exclamation point dot */}
      <View
        style={{
          width: strokeWidth * 1.4,
          height: strokeWidth * 1.4,
          borderRadius: (strokeWidth * 1.4) / 2,
          backgroundColor: color,
          position: "absolute",
          bottom: size * 0.20,
        }}
      />
      {/* Triangle outer frame */}
      <View
        style={{
          width: size * 0.76,
          height: size * 0.76,
          borderWidth: strokeWidth,
          borderColor: color,
          borderRadius: size * 0.12,
          transform: [{ rotate: "45deg" }],
        }}
      />
    </View>
  );
};

// 11. Clipboard / History Icon
export const ClipboardIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  const boardW = size * 0.66;
  const boardH = size * 0.78;
  const clipW = size * 0.32;
  const clipH = size * 0.14;

  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Board Base */}
      <View
        style={{
          width: boardW,
          height: boardH,
          borderRadius: size * 0.08,
          borderWidth: strokeWidth,
          borderColor: color,
          alignItems: "center",
          paddingTop: clipH * 0.8,
        }}
      >
        {/* Inner lines */}
        <View style={{ width: boardW * 0.6, height: strokeWidth, backgroundColor: color, marginVertical: 3 }} />
        <View style={{ width: boardW * 0.6, height: strokeWidth, backgroundColor: color, marginVertical: 3 }} />
        <View style={{ width: boardW * 0.4, height: strokeWidth, backgroundColor: color, marginVertical: 3 }} />
      </View>
      {/* Top Clip */}
      <View
        style={{
          position: "absolute",
          top: size * 0.06,
          width: clipW,
          height: clipH,
          borderRadius: size * 0.04,
          backgroundColor: color,
        }}
      />
    </View>
  );
};

// 12. Code / Dev Bracket Icon
export const CodeIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Left chevron < */}
      <View
        style={{
          position: "absolute",
          left: size * 0.12,
          width: size * 0.3,
          height: size * 0.3,
          borderColor: color,
          borderLeftWidth: strokeWidth,
          borderBottomWidth: strokeWidth,
          transform: [{ rotate: "45deg" }],
        }}
      />
      {/* Slash / */}
      <View
        style={{
          position: "absolute",
          width: strokeWidth,
          height: size * 0.55,
          backgroundColor: color,
          borderRadius: strokeWidth / 2,
          transform: [{ rotate: "20deg" }],
        }}
      />
      {/* Right chevron > */}
      <View
        style={{
          position: "absolute",
          right: size * 0.12,
          width: size * 0.3,
          height: size * 0.3,
          borderColor: color,
          borderRightWidth: strokeWidth,
          borderTopWidth: strokeWidth,
          transform: [{ rotate: "45deg" }],
        }}
      />
    </View>
  );
};

// 13. Terminal / Console Icon
export const TerminalIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Terminal window border */}
      <View
        style={{
          width: size * 0.88,
          height: size * 0.76,
          borderRadius: size * 0.12,
          borderWidth: strokeWidth,
          borderColor: color,
          padding: 3,
        }}
      >
        {/* Prompt chevron > */}
        <View
          style={{
            position: "absolute",
            left: size * 0.18,
            top: size * 0.28,
            width: size * 0.18,
            height: size * 0.18,
            borderColor: color,
            borderRightWidth: strokeWidth,
            borderTopWidth: strokeWidth,
            transform: [{ rotate: "45deg" }],
          }}
        />
        {/* Cursor underscore _ */}
        <View
          style={{
            position: "absolute",
            left: size * 0.44,
            bottom: size * 0.22,
            width: size * 0.26,
            height: strokeWidth,
            backgroundColor: color,
            borderRadius: strokeWidth / 2,
          }}
        />
      </View>
    </View>
  );
};

// 14. Bank / Core Banking Icon
export const BankIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Roof Pediment / Triangle */}
      <View
        style={{
          width: size * 0.84,
          height: size * 0.14,
          borderTopLeftRadius: size * 0.06,
          borderTopRightRadius: size * 0.06,
          backgroundColor: color,
          position: "absolute",
          top: size * 0.14,
        }}
      />
      {/* Columns */}
      <View
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          width: size * 0.68,
          position: "absolute",
          top: size * 0.34,
        }}
      >
        <View style={{ width: strokeWidth * 1.5, height: size * 0.34, backgroundColor: color }} />
        <View style={{ width: strokeWidth * 1.5, height: size * 0.34, backgroundColor: color }} />
        <View style={{ width: strokeWidth * 1.5, height: size * 0.34, backgroundColor: color }} />
        <View style={{ width: strokeWidth * 1.5, height: size * 0.34, backgroundColor: color }} />
      </View>
      {/* Base */}
      <View
        style={{
          width: size * 0.88,
          height: strokeWidth * 1.8,
          borderRadius: strokeWidth / 2,
          backgroundColor: color,
          position: "absolute",
          bottom: size * 0.14,
        }}
      />
    </View>
  );
};

// 15. Headset / Contact Center Icon
export const HeadsetIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Headband Arc */}
      <View
        style={{
          width: size * 0.72,
          height: size * 0.68,
          borderTopLeftRadius: size * 0.36,
          borderTopRightRadius: size * 0.36,
          borderLeftWidth: strokeWidth,
          borderRightWidth: strokeWidth,
          borderTopWidth: strokeWidth,
          borderColor: color,
          position: "absolute",
          top: size * 0.12,
        }}
      />
      {/* Left Earpiece */}
      <View
        style={{
          position: "absolute",
          left: size * 0.08,
          top: size * 0.44,
          width: size * 0.14,
          height: size * 0.28,
          borderRadius: size * 0.07,
          backgroundColor: color,
        }}
      />
      {/* Right Earpiece */}
      <View
        style={{
          position: "absolute",
          right: size * 0.08,
          top: size * 0.44,
          width: size * 0.14,
          height: size * 0.28,
          borderRadius: size * 0.07,
          backgroundColor: color,
        }}
      />
      {/* Mic Boom */}
      <View
        style={{
          position: "absolute",
          right: size * 0.12,
          bottom: size * 0.16,
          width: size * 0.32,
          height: strokeWidth,
          backgroundColor: color,
          borderRadius: strokeWidth / 2,
        }}
      />
    </View>
  );
};

// 16. Webhook / Event Stream Icon
export const WebhookIcon: React.FC<IconProps> = ({
  size = 20,
  color = "#2563EB",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Central Node */}
      <View
        style={{
          width: size * 0.24,
          height: size * 0.24,
          borderRadius: size * 0.12,
          backgroundColor: color,
        }}
      />
      {/* Left Branch */}
      <View
        style={{
          position: "absolute",
          left: size * 0.12,
          top: size * 0.22,
          width: size * 0.2,
          height: size * 0.2,
          borderRadius: size * 0.1,
          borderWidth: strokeWidth,
          borderColor: color,
        }}
      />
      {/* Right Branch */}
      <View
        style={{
          position: "absolute",
          right: size * 0.12,
          bottom: size * 0.22,
          width: size * 0.2,
          height: size * 0.2,
          borderRadius: size * 0.1,
          borderWidth: strokeWidth,
          borderColor: color,
        }}
      />
    </View>
  );
};

// 17. Copy Icon
export const CopyIcon: React.FC<IconProps> = ({
  size = 18,
  color = "#94A3B8",
  strokeWidth = 1.8,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      {/* Back square */}
      <View
        style={{
          position: "absolute",
          top: size * 0.1,
          right: size * 0.1,
          width: size * 0.55,
          height: size * 0.55,
          borderRadius: size * 0.08,
          borderWidth: strokeWidth,
          borderColor: color,
          opacity: 0.6,
        }}
      />
      {/* Front square */}
      <View
        style={{
          position: "absolute",
          bottom: size * 0.1,
          left: size * 0.1,
          width: size * 0.58,
          height: size * 0.58,
          borderRadius: size * 0.08,
          borderWidth: strokeWidth,
          borderColor: color,
          backgroundColor: "transparent",
        }}
      />
    </View>
  );
};

// 18. Checkmark Icon
export const CheckIcon: React.FC<IconProps> = ({
  size = 18,
  color = "#10B981",
  strokeWidth = 2.2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      <View
        style={{
          width: size * 0.5,
          height: size * 0.28,
          borderColor: color,
          borderLeftWidth: strokeWidth,
          borderBottomWidth: strokeWidth,
          transform: [{ rotate: "-45deg" }],
          marginBottom: size * 0.08,
        }}
      />
    </View>
  );
};

// 19. Chevron Right
export const ChevronRightIcon: React.FC<IconProps> = ({
  size = 16,
  color = "#94A3B8",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      <View
        style={{
          width: size * 0.36,
          height: size * 0.36,
          borderColor: color,
          borderRightWidth: strokeWidth,
          borderTopWidth: strokeWidth,
          transform: [{ rotate: "45deg" }],
        }}
      />
    </View>
  );
};

// 20. Chevron Down
export const ChevronDownIcon: React.FC<IconProps> = ({
  size = 16,
  color = "#94A3B8",
  strokeWidth = 2,
  style,
}) => {
  return (
    <View style={[{ width: size, height: size, alignItems: "center", justifyContent: "center" }, style]}>
      <View
        style={{
          width: size * 0.36,
          height: size * 0.36,
          borderColor: color,
          borderRightWidth: strokeWidth,
          borderBottomWidth: strokeWidth,
          transform: [{ rotate: "45deg" }],
        }}
      />
    </View>
  );
};

