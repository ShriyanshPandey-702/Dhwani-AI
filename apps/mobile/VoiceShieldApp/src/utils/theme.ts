// VoiceShield Design Tokens & Theme
export const colors = {
  // Backgrounds
  bg: '#0A0E1A',
  bgCard: '#111827',
  bgElevated: '#1C2436',

  // Brand
  brand: '#6C63FF',
  brandLight: '#8B85FF',
  brandDim: '#6C63FF33',

  // Risk States
  safe: '#10B981',
  watch: '#3B82F6',
  suspicious: '#F59E0B',
  high: '#EF4444',
  critical: '#DC2626',

  // Text
  textPrimary: '#F9FAFB',
  textSecondary: '#9CA3AF',
  textMuted: '#4B5563',

  // UI
  border: '#1F2937',
  success: '#10B981',
  error: '#EF4444',
  warning: '#F59E0B',
  info: '#3B82F6',

  white: '#FFFFFF',
  black: '#000000',
};

export const RISK_COLORS = {
  insufficient_evidence: colors.watch,
  low: colors.safe,
  suspicious: colors.suspicious,
  high: colors.high,
  critical: colors.critical,
};

export const RISK_LABELS = {
  insufficient_evidence: 'Monitoring',
  low: 'Low Risk',
  suspicious: 'Suspicious',
  high: 'High Risk',
  critical: 'Critical',
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const radius = {
  sm: 8,
  md: 12,
  lg: 20,
  full: 9999,
};

export const typography = {
  h1: { fontSize: 32, fontWeight: '700' as const, color: colors.textPrimary },
  h2: { fontSize: 24, fontWeight: '700' as const, color: colors.textPrimary },
  h3: { fontSize: 18, fontWeight: '600' as const, color: colors.textPrimary },
  body: { fontSize: 15, fontWeight: '400' as const, color: colors.textPrimary },
  small: { fontSize: 13, fontWeight: '400' as const, color: colors.textSecondary },
  caption: { fontSize: 11, fontWeight: '400' as const, color: colors.textMuted },
  mono: { fontSize: 12, fontFamily: 'monospace', color: colors.textSecondary },
};
