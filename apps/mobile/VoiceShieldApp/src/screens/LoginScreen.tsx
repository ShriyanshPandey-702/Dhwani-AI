import React, { useState } from "react";
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Image,
} from "react-native";
import { useNavigation } from "@react-navigation/native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../utils/theme";
import { useAuthStore } from "../store/authStore";

export const LoginScreen: React.FC = () => {
  const navigation = useNavigation();
  const insets = useSafeAreaInsets();
  const { colors, radius, isDark } = useTheme();

  const [isRegister, setIsRegister] = useState(false);
  const [emailOrPhone, setEmailOrPhone] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);

  const { login, register, isLoading, error, clearError } = useAuthStore();

  const handleSubmit = async () => {
    clearError();
    if (isRegister) {
      await register(emailOrPhone, password, fullName);
    } else {
      await login(emailOrPhone, password);
    }
  };

  return (
    <KeyboardAvoidingView
      style={[
        styles.container,
        {
          backgroundColor: isDark ? colors.background : colors.background,
        },
      ]}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={[
          styles.scroll,
          {
            paddingTop: insets.top + 24,
            paddingBottom: Math.max(insets.bottom, 24),
          },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        {/* Brand Header */}
        <View style={styles.brandSection}>
          <Image
            source={require("../assets/logo.png")}
            style={styles.logoImage}
            resizeMode="contain"
            accessibilityRole="image"
            accessibilityLabel="Dhwani AI Logo"
          />
          <Text style={[styles.brandTitle, { color: colors.textPrimary }]}>
            Dhwani AI
          </Text>
          <Text style={[styles.brandTagline, { color: colors.textSecondary }]}>
            Secure Calls. Trusted People.
          </Text>
        </View>

        {/* Input Card Container */}
        <View
          style={[
            styles.card,
            {
              backgroundColor: isDark ? colors.surface : colors.surface,
              borderColor: colors.border,
              borderRadius: radius.lg,
              shadowColor: colors.cardShadow,
            },
          ]}
        >
          {isRegister && (
            <View style={styles.inputGroup}>
              <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>
                Full Name
              </Text>
              <TextInput
                style={[
                  styles.input,
                  {
                    backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                    color: colors.textPrimary,
                    borderColor: colors.border,
                    borderRadius: radius.sm,
                  },
                ]}
                value={fullName}
                onChangeText={setFullName}
                placeholder="Full Name"
                placeholderTextColor={colors.textMuted}
                autoCapitalize="words"
              />
            </View>
          )}

          {/* Email or Phone */}
          <View style={styles.inputGroup}>
            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>
              Email or Phone
            </Text>
            <TextInput
              style={[
                styles.input,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  color: colors.textPrimary,
                  borderColor: colors.border,
                  borderRadius: radius.sm,
                },
              ]}
              value={emailOrPhone}
              onChangeText={setEmailOrPhone}
              placeholder="name@company.com or +91..."
              placeholderTextColor={colors.textMuted}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          {/* Password */}
          <View style={styles.inputGroup}>
            <Text style={[styles.inputLabel, { color: colors.textSecondary }]}>
              Password
            </Text>
            <View
              style={[
                styles.passwordRow,
                {
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderColor: colors.border,
                  borderRadius: radius.sm,
                },
              ]}
            >
              <TextInput
                style={[styles.passwordInput, { color: colors.textPrimary }]}
                value={password}
                onChangeText={setPassword}
                placeholder="••••••••••••"
                placeholderTextColor={colors.textMuted}
                secureTextEntry={!showPassword}
                autoCapitalize="none"
              />
              <TouchableOpacity
                onPress={() => setShowPassword(!showPassword)}
                style={styles.eyeBtn}
                accessibilityRole="button"
                accessibilityLabel={showPassword ? "Hide password" : "Show password"}
              >
                <Text style={{ fontSize: 16, color: colors.textMuted }}>
                  {showPassword ? "👁" : "👁‍🗨"}
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Remember me & Forgot Password */}
          {!isRegister && (
            <View style={styles.optionsRow}>
              <TouchableOpacity
                onPress={() => setRememberMe(!rememberMe)}
                style={styles.rememberRow}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: rememberMe }}
              >
                <View
                  style={[
                    styles.checkbox,
                    {
                      borderColor: rememberMe ? colors.accent : colors.border,
                      backgroundColor: rememberMe ? colors.accent : "transparent",
                      borderRadius: 4,
                    },
                  ]}
                >
                  {rememberMe ? (
                    <Text style={{ color: "#FFFFFF", fontSize: 11, fontWeight: "800" }}>✓</Text>
                  ) : null}
                </View>
                <Text style={[styles.optionText, { color: colors.textSecondary }]}>
                  Remember me
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={() => {}}
                accessibilityRole="button"
                accessibilityLabel="Forgot password"
              >
                <Text style={[styles.forgotText, { color: colors.accent }]}>
                  Forgot password?
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {error ? (
            <View
              style={[
                styles.errorBox,
                {
                  backgroundColor: `${colors.danger}18`,
                  borderColor: `${colors.danger}44`,
                  borderRadius: radius.sm,
                },
              ]}
            >
              <Text style={[styles.errorText, { color: colors.danger }]}>{error}</Text>
            </View>
          ) : null}

          {/* Primary Action Button */}
          <TouchableOpacity
            style={[
              styles.primaryBtn,
              {
                backgroundColor: colors.accent,
                borderRadius: radius.md,
                opacity: isLoading ? 0.7 : 1,
              },
            ]}
            onPress={handleSubmit}
            disabled={isLoading}
            accessibilityRole="button"
            accessibilityLabel={isRegister ? "Create account" : "Sign In"}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFFFFF" size="small" />
            ) : (
              <Text style={styles.primaryBtnText}>
                {isRegister ? "Create Account" : "Sign In"}
              </Text>
            )}
          </TouchableOpacity>

          {/* Divider */}
          <View style={styles.dividerRow}>
            <View style={[styles.dividerLine, { backgroundColor: colors.border }]} />
            <Text style={[styles.dividerText, { color: colors.textMuted }]}>
              or continue with
            </Text>
            <View style={[styles.dividerLine, { backgroundColor: colors.border }]} />
          </View>

          {/* Social Auth Providers */}
          <View style={styles.socialRow}>
            <TouchableOpacity
              style={[
                styles.socialBtn,
                {
                  borderColor: colors.border,
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderRadius: radius.sm,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Continue with Google"
            >
              <Text style={[styles.socialText, { color: colors.textPrimary }]}>G Google</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.socialBtn,
                {
                  borderColor: colors.border,
                  backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                  borderRadius: radius.sm,
                },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Continue with Apple"
            >
              <Text style={[styles.socialText, { color: colors.textPrimary }]}> Apple</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity
            style={[
              styles.enterpriseBtn,
              {
                borderColor: colors.border,
                backgroundColor: isDark ? colors.surfaceElevated : colors.surfaceElevated,
                borderRadius: radius.sm,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="Institution or Enterprise login"
          >
            <Text style={[styles.enterpriseText, { color: colors.textPrimary }]}>
              🏛 Institution / Enterprise
            </Text>
          </TouchableOpacity>

          {/* Toggle Create / Sign in */}
          <TouchableOpacity
            onPress={() => {
              clearError();
              setIsRegister(!isRegister);
            }}
            style={styles.toggleRow}
            accessibilityRole="button"
          >
            <Text style={[styles.toggleText, { color: colors.textSecondary }]}>
              {isRegister ? "Already have an account? " : "New to Dhwani AI? "}
              <Text style={[styles.toggleLink, { color: colors.accent }]}>
                {isRegister ? "Sign In" : "Create an account"}
              </Text>
            </Text>
          </TouchableOpacity>
        </View>

        {/* Backend Settings Link */}
        <TouchableOpacity
          onPress={() => navigation.navigate("Settings" as never)}
          style={styles.settingsLink}
          accessibilityRole="button"
          accessibilityLabel="Connection Settings"
        >
          <Text style={[styles.settingsLinkText, { color: colors.textMuted }]}>
            ⚙ Connection & Server Settings
          </Text>
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: 20,
  },
  brandSection: {
    alignItems: "center",
    marginBottom: 24,
  },
  logoImage: {
    width: 68,
    height: 68,
    marginBottom: 10,
  },
  brandTitle: {
    fontSize: 26,
    fontWeight: "800",
    letterSpacing: -0.4,
  },
  brandTagline: {
    fontSize: 13,
    fontWeight: "500",
    marginTop: 4,
    letterSpacing: 0.2,
  },
  card: {
    borderWidth: 1,
    padding: 20,
    gap: 14,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 3,
  },
  inputGroup: {
    gap: 6,
  },
  inputLabel: {
    fontSize: 12,
    fontWeight: "600",
    letterSpacing: 0.2,
  },
  input: {
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 14,
  },
  passwordRow: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    paddingHorizontal: 14,
  },
  passwordInput: {
    flex: 1,
    paddingVertical: 10,
    fontSize: 14,
  },
  eyeBtn: {
    padding: 6,
  },
  optionsRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 2,
  },
  rememberRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  checkbox: {
    width: 18,
    height: 18,
    borderWidth: 1.5,
    alignItems: "center",
    justifyContent: "center",
  },
  optionText: {
    fontSize: 12,
    fontWeight: "500",
  },
  forgotText: {
    fontSize: 12,
    fontWeight: "600",
  },
  errorBox: {
    borderWidth: 1,
    padding: 10,
  },
  errorText: {
    fontSize: 13,
  },
  primaryBtn: {
    paddingVertical: 13,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 4,
  },
  primaryBtnText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700",
    letterSpacing: 0.3,
  },
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 4,
  },
  dividerLine: {
    flex: 1,
    height: 1,
  },
  dividerText: {
    paddingHorizontal: 10,
    fontSize: 11,
    fontWeight: "500",
  },
  socialRow: {
    flexDirection: "row",
    gap: 10,
  },
  socialBtn: {
    flex: 1,
    borderWidth: 1,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  socialText: {
    fontSize: 13,
    fontWeight: "600",
  },
  enterpriseBtn: {
    borderWidth: 1,
    paddingVertical: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  enterpriseText: {
    fontSize: 13,
    fontWeight: "600",
  },
  toggleRow: {
    alignItems: "center",
    marginTop: 6,
  },
  toggleText: {
    fontSize: 13,
  },
  toggleLink: {
    fontWeight: "700",
  },
  settingsLink: {
    marginTop: 20,
    alignItems: "center",
  },
  settingsLinkText: {
    fontSize: 12,
    fontWeight: "500",
  },
});
