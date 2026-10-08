// Dhwani AI Design Tokens & Theme Specification (design.md)
import { useThemeStore, ThemeMode } from "../store/themeStore";

export const lightColors = {
  // Backgrounds
  background: "#F8F4F2", // warm off-white, not harsh white
  surface: "#FFFFFF",
  surfaceElevated: "#F0EAE6",
  surfaceHighlight: "#EBE3DC",

  // Typography
  textPrimary: "#172536",
  textSecondary: "#63707D",
  textMuted: "#89939D",

  // Borders
  border: "#E4E7E9",
  borderLight: "#EDEFEF",

  // Brand / Accents
  accent: "#1E8A7D", // soft teal / blue-green
  accentSoft: "#E6F5F3",
  accentSecondary: "#E76F51", // soft blush pink / warm coral
  accentPink: "#F2C1C5",

  // Status
  success: "#059669",
  warning: "#D97706",
  danger: "#E63946",
  critical: "#DC2626",

  // Risk Orb Specific
  orbLow: "#059669",
  orbHigh: "#E63946",
  highRiskSurface: "#FDF2F2",
  cardShadow: "rgba(23, 37, 54, 0.05)",

  // Backward compatibility aliases
  bg: "#F8F4F2",
  bgCard: "#FFFFFF",
  bgElevated: "#F0EAE6",
  brand: "#1E8A7D",
  brandLight: "#38A89A",
  brandDim: "#1E8A7D22",
  safe: "#059669",
  watch: "#64748B",
  suspicious: "#D97706",
  high: "#E63946",
  info: "#1E8A7D",
  error: "#E63946",
  white: "#FFFFFF",
  black: "#000000",
};

export const darkColors = {
  // Backgrounds
  background: "#071017", // deep blue-black, not pure black
  surface: "#0D171F",
  surfaceElevated: "#111E27",
  surfaceHighlight: "#162734",

  // Typography
  textPrimary: "#F4F7F8",
  textSecondary: "#A9B5BD",
  textMuted: "#74838D",

  // Borders
  border: "#24343E",
  borderLight: "#1C2932",

  // Brand / Accents
  accent: "#5FD0C5", // vibrant teal
  accentSoft: "#133537",
  accentSecondary: "#7FAFC5", // soft blue
  accentPink: "#F2C1C5",

  // Status
  success: "#10B981",
  warning: "#F59E0B",
  danger: "#FF747A",
  critical: "#EF4444",

  // Risk Orb Specific
  orbLow: "#5FD0C5",
  orbHigh: "#FF747A",
  highRiskSurface: "#2A161A",
  cardShadow: "rgba(0, 0, 0, 0.4)",

  // Backward compatibility aliases
  bg: "#071017",
  bgCard: "#0D171F",
  bgElevated: "#111E27",
  brand: "#5FD0C5",
  brandLight: "#86E2D8",
  brandDim: "#5FD0C522",
  safe: "#5FD0C5",
  watch: "#64748B",
  suspicious: "#F59E0B",
  high: "#FF747A",
  info: "#5FD0C5",
  error: "#FF747A",
  white: "#FFFFFF",
  black: "#000000",
};

export const LIGHT_RISK_COLORS = {
  insufficient_evidence: "#64748B",
  low: "#059669",
  suspicious: "#D97706",
  high: "#E63946",
  critical: "#DC2626",
};

export const DARK_RISK_COLORS = {
  insufficient_evidence: "#64748B",
  low: "#5FD0C5",
  suspicious: "#F59E0B",
  high: "#FF747A",
  critical: "#EF4444",
};

// Default export uses dark tokens to preserve dark-theme default
export const colors = darkColors;
export const RISK_COLORS = DARK_RISK_COLORS;

// Strict 5 Risk States (design.md Section 12)
export const RISK_LABELS = {
  insufficient_evidence: "Insufficient Evidence",
  low: "Low",
  suspicious: "Suspicious",
  high: "High",
  critical: "Critical",
};

export const spacing = {
  xxs: 4,
  xs: 8,
  sm: 12,
  md: 16,
  lg: 20,
  xl: 24,
  xxl: 32,
  xxxl: 40,
  huge: 48,
};

export const radius = {
  xs: 6,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  full: 9999,
};

export const typography = {
  h1: { fontSize: 28, fontWeight: "700" as const, letterSpacing: -0.5 },
  h2: { fontSize: 22, fontWeight: "700" as const, letterSpacing: -0.3 },
  h3: { fontSize: 18, fontWeight: "600" as const },
  subtitle: { fontSize: 15, fontWeight: "500" as const },
  body: { fontSize: 14, fontWeight: "400" as const },
  small: { fontSize: 13, fontWeight: "400" as const },
  caption: { fontSize: 11, fontWeight: "500" as const, letterSpacing: 0.2 },
  mono: { fontSize: 12, fontFamily: "monospace" },
  metric: { fontSize: 50, fontWeight: "800" as const, letterSpacing: -1 },
};

/**
 * React hook to consume current theme dynamically across screens.
 */
export const useTheme = () => {
  const mode = useThemeStore((s) => s.mode);
  const systemColorScheme = useThemeStore((s) => s.systemColorScheme);
  const setMode = useThemeStore((s) => s.setMode);

  const isDark =
    mode === "dark" || (mode === "system" && systemColorScheme === "dark");

  const currentColors = isDark ? darkColors : lightColors;
  const currentRiskColors = isDark ? DARK_RISK_COLORS : LIGHT_RISK_COLORS;

  return {
    isDark,
    mode,
    setMode,
    colors: currentColors,
    riskColors: currentRiskColors,
    spacing,
    radius,
    typography,
  };
};
