import { create } from 'zustand';
import { UserProfile } from '../types';
import { authService } from '../services/auth/authService';

interface AuthState {
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, fullName: string) => Promise<void>;
  logout: () => Promise<void>;
  loadUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      await authService.login(email, password);
      const user = await authService.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      set({ isLoading: false, error: err?.response?.data?.detail || 'Login failed' });
    }
  },

  register: async (email, password, fullName) => {
    set({ isLoading: true, error: null });
    try {
      await authService.register(email, password, fullName);
      const user = await authService.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (err: any) {
      set({ isLoading: false, error: err?.response?.data?.detail || 'Registration failed' });
    }
  },

  logout: async () => {
    await authService.logout();
    set({ user: null, isAuthenticated: false });
  },

  loadUser: async () => {
    const hasToken = await authService.hasValidToken();
    if (!hasToken) {
      set({ isAuthenticated: false });
      return;
    }
    try {
      const user = await authService.getMe();
      set({ user, isAuthenticated: true });
    } catch {
      set({ isAuthenticated: false });
    }
  },

  clearError: () => set({ error: null }),
}));
