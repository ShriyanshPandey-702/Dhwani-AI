import { create } from 'zustand';
import { OverviewStats, SessionData } from '../types';
import client from '../services/api/client';

interface SessionStoreState {
  session: SessionData | null;
  sessions: SessionData[];
  /** Aggregates for the Home security-overview dashboard. */
  overview: OverviewStats | null;
  isMonitoring: boolean;
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;

  createSession: () => Promise<SessionData | null>;
  startSession: (sessionId: string) => Promise<void>;
  stopSession: (sessionId: string) => Promise<void>;
  loadSessions: () => Promise<void>;
  loadOverview: () => Promise<void>;
  refreshHome: () => Promise<void>;
  setSession: (s: SessionData | null) => void;
  setMonitoring: (v: boolean) => void;
  clearError: () => void;
}

const message = (err: any, fallback: string): string =>
  err?.response?.data?.detail || err?.message || fallback;

export const useSessionStore = create<SessionStoreState>((set, get) => ({
  session: null,
  sessions: [],
  overview: null,
  isMonitoring: false,
  isLoading: false,
  isRefreshing: false,
  error: null,

  createSession: async () => {
    set({ isLoading: true, error: null });
    try {
      const { data } = await client.post<SessionData>('/sessions');
      set({ session: data, isLoading: false });
      return data;
    } catch (err: any) {
      set({ error: message(err, 'Failed to create session'), isLoading: false });
      return null;
    }
  },

  startSession: async (sessionId: string) => {
    const { data } = await client.post<SessionData>(`/sessions/${sessionId}/start`);
    set({ session: data, isMonitoring: true });
  },

  stopSession: async (sessionId: string) => {
    const { data } = await client.post<SessionData>(`/sessions/${sessionId}/stop`);
    set({ session: data, isMonitoring: false });
  },

  loadSessions: async () => {
    try {
      const { data } = await client.get<SessionData[]>('/sessions');
      set({ sessions: data });
    } catch (err: any) {
      set({ error: message(err, 'Failed to load sessions') });
    }
  },

  loadOverview: async () => {
    try {
      const { data } = await client.get<OverviewStats>('/incidents/stats/overview');
      set({ overview: data });
    } catch (err: any) {
      // A missing backend leaves `overview` null; the Home screen then renders
      // an explicit empty state rather than inventing figures.
      set({ error: message(err, 'Failed to load security overview') });
    }
  },

  refreshHome: async () => {
    set({ isRefreshing: true, error: null });
    await Promise.all([get().loadSessions(), get().loadOverview()]);
    set({ isRefreshing: false });
  },

  setSession: s => set({ session: s }),
  setMonitoring: v => set({ isMonitoring: v }),
  clearError: () => set({ error: null }),
}));
