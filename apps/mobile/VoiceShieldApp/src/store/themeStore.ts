import { create } from "zustand";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { Appearance } from "react-native";

export type ThemeMode = "light" | "dark" | "system";

interface ThemeStoreState {
  mode: ThemeMode;
  systemColorScheme: "light" | "dark";
  setMode: (mode: ThemeMode) => Promise<void>;
  initTheme: () => Promise<void>;
}

const THEME_STORAGE_KEY = "@dhwani_ai_theme_mode";

export const useThemeStore = create<ThemeStoreState>((set, get) => ({
  mode: "light",
  systemColorScheme: (Appearance.getColorScheme() as "light" | "dark") || "light",

  setMode: async (mode: ThemeMode) => {
    set({ mode });
    try {
      await AsyncStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch {
      // safe fallback
    }
  },

  initTheme: async () => {
    try {
      const saved = await AsyncStorage.getItem(THEME_STORAGE_KEY);
      if (saved === "light" || saved === "dark" || saved === "system") {
        set({ mode: saved });
      }
    } catch {
      // safe fallback
    }

    Appearance.addChangeListener(({ colorScheme }) => {
      set({ systemColorScheme: colorScheme === "light" ? "light" : "dark" });
    });
  },
}));
