import { create } from 'zustand';
import { ScreenedCallEvent } from '../types/telecom';
import { callScreeningService } from '../services/telecom/callScreeningService';

interface CallScreeningState {
  isRoleHeld: boolean;
  isAvailable: boolean;
  recentCalls: ScreenedCallEvent[];
  activeAlert: ScreenedCallEvent | null;
  isLoading: boolean;
  error: string | null;

  checkRoleStatus: () => Promise<boolean>;
  requestRole: () => Promise<boolean>;
  loadRecentCalls: () => Promise<void>;
  clearHistory: () => Promise<void>;
  addScreenedCall: (event: ScreenedCallEvent) => void;
  dismissAlert: () => void;
  setRoleHeld: (held: boolean) => void;
}

export const useCallScreeningStore = create<CallScreeningState>((set, get) => ({
  isRoleHeld: false,
  isAvailable: true,
  recentCalls: [],
  activeAlert: null,
  isLoading: false,
  error: null,

  checkRoleStatus: async () => {
    try {
      const [isHeld, isAvailable] = await Promise.all([
        callScreeningService.isRoleHeld(),
        callScreeningService.getRoleAvailability(),
      ]);
      set({ isRoleHeld: isHeld, isAvailable, error: null });
      return isHeld;
    } catch (err: any) {
      set({ error: err?.message || 'Failed to check call screening role status' });
      return false;
    }
  },

  requestRole: async () => {
    set({ isLoading: true, error: null });
    try {
      const result = await callScreeningService.requestRole();
      const granted = result.granted || result.alreadyHeld;
      set({ isRoleHeld: granted, isLoading: false });
      return granted;
    } catch (err: any) {
      set({
        error: err?.message || 'Failed to request call screening role',
        isLoading: false,
      });
      return false;
    }
  },

  loadRecentCalls: async () => {
    set({ isLoading: true, error: null });
    try {
      const calls = await callScreeningService.getRecentScreenedCalls();
      set({ recentCalls: calls, isLoading: false });
    } catch (err: any) {
      set({
        error: err?.message || 'Failed to load recent screened calls',
        isLoading: false,
      });
    }
  },

  clearHistory: async () => {
    try {
      await callScreeningService.clearScreenedCalls();
      set({ recentCalls: [], activeAlert: null });
    } catch (err: any) {
      set({ error: err?.message || 'Failed to clear screened calls history' });
    }
  },

  addScreenedCall: (event: ScreenedCallEvent) => {
    set(state => {
      const updated = [event, ...state.recentCalls.filter(c => c.eventId !== event.eventId)];
      const activeAlert = event.riskLevel === 'HIGH' || event.warningType !== 'NONE' ? event : state.activeAlert;
      return { recentCalls: updated.slice(0, 50), activeAlert };
    });
  },

  dismissAlert: () => set({ activeAlert: null }),

  setRoleHeld: (held: boolean) => set({ isRoleHeld: held }),
}));
