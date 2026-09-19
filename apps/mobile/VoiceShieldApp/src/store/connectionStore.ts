import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DEFAULT_API_BASE_URL, DEFAULT_WS_BASE_URL } from '../config/api';

const STORAGE_KEY = '@voiceshield_connection_config';

export type ConnectionMode = 'usb' | 'wifi';
export type ConnectionHealthStatus = 'idle' | 'checking' | 'connected' | 'error';

export interface ConnectionConfig {
  mode: ConnectionMode;
  wifiHost: string;
  wifiPort: string;
}

export interface ConnectionState extends ConnectionConfig {
  isLoaded: boolean;
  connectionStatus: ConnectionHealthStatus;
  statusMessage: string | null;

  setMode: (mode: ConnectionMode) => Promise<void>;
  setWifiHost: (host: string) => Promise<void>;
  setWifiPort: (port: string) => Promise<void>;
  loadConfig: () => Promise<void>;
  testConnection: () => Promise<{ success: boolean; message: string }>;
}

export interface SanitizedHostPort {
  host: string;
  port: string;
  isValid: boolean;
  error?: string;
}

/**
 * Sanitizes and validates host and port inputs.
 * Strips protocols (http://, ws://, etc.), trailing slashes, and extracts embedded ports.
 */
export function sanitizeHostPort(rawHost: string, rawPort: string): SanitizedHostPort {
  let host = (rawHost || '').trim();
  let port = (rawPort || '').trim();

  // Strip protocol prefixes if accidentally pasted
  host = host.replace(/^(https?|wss?):\/\//i, '');
  // Strip trailing slashes
  host = host.replace(/\/+$/, '');

  // If the host field contains a port (e.g. 192.168.1.5:8000), extract it
  const colonIndex = host.lastIndexOf(':');
  if (colonIndex !== -1 && !host.includes(']')) {
    const extractedPort = host.slice(colonIndex + 1);
    host = host.slice(0, colonIndex);
    if (!port && extractedPort) {
      port = extractedPort;
    }
  }

  if (!host) {
    return { host: '', port: port || '8000', isValid: false, error: 'Host IP is required for Wi-Fi mode' };
  }

  const portNum = parseInt(port || '8000', 10);
  if (isNaN(portNum) || portNum < 1 || portNum > 65535) {
    return { host, port, isValid: false, error: 'Port must be between 1 and 65535' };
  }

  return { host, port: String(portNum), isValid: true };
}

/**
 * Dynamically resolves the REST API base URL.
 * Returns null if Wi-Fi mode is selected but not properly configured.
 */
export function getApiBaseUrl(): string | null {
  const { mode, wifiHost, wifiPort } = useConnectionStore.getState();
  if (mode === 'usb') {
    return DEFAULT_API_BASE_URL;
  }
  const sanitized = sanitizeHostPort(wifiHost, wifiPort);
  if (!sanitized.isValid) {
    return null;
  }
  return `http://${sanitized.host}:${sanitized.port}`;
}

/**
 * Dynamically resolves the WebSocket base URL.
 * Returns null if Wi-Fi mode is selected but not properly configured.
 */
export function getWsBaseUrl(): string | null {
  const { mode, wifiHost, wifiPort } = useConnectionStore.getState();
  if (mode === 'usb') {
    return DEFAULT_WS_BASE_URL;
  }
  const sanitized = sanitizeHostPort(wifiHost, wifiPort);
  if (!sanitized.isValid) {
    return null;
  }
  return `ws://${sanitized.host}:${sanitized.port}`;
}

async function persistConfig(config: ConnectionConfig): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  } catch {
    // Non-fatal if storage write fails
  }
}

export const useConnectionStore = create<ConnectionState>((set, get) => ({
  mode: 'usb',
  wifiHost: '',
  wifiPort: '8000',
  isLoaded: false,
  connectionStatus: 'idle',
  statusMessage: null,

  setMode: async (mode: ConnectionMode) => {
    set({ mode, connectionStatus: 'idle', statusMessage: null });
    const { wifiHost, wifiPort } = get();
    await persistConfig({ mode, wifiHost, wifiPort });
  },

  setWifiHost: async (host: string) => {
    set({ wifiHost: host, connectionStatus: 'idle', statusMessage: null });
    const { mode, wifiPort } = get();
    await persistConfig({ mode, wifiHost: host, wifiPort });
  },

  setWifiPort: async (port: string) => {
    set({ wifiPort: port, connectionStatus: 'idle', statusMessage: null });
    const { mode, wifiHost } = get();
    await persistConfig({ mode, wifiHost, wifiPort: port });
  },

  loadConfig: async () => {
    try {
      const raw = await AsyncStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed: Partial<ConnectionConfig> = JSON.parse(raw);
        set({
          mode: parsed.mode === 'wifi' ? 'wifi' : 'usb',
          wifiHost: typeof parsed.wifiHost === 'string' ? parsed.wifiHost : '',
          wifiPort: typeof parsed.wifiPort === 'string' ? parsed.wifiPort : '8000',
          isLoaded: true,
        });
        return;
      }
    } catch {
      // Fallback to default
    }
    set({ isLoaded: true });
  },

  testConnection: async () => {
    const apiBase = getApiBaseUrl();
    if (!apiBase) {
      const msg = 'Please configure a valid Mac LAN host IP.';
      set({ connectionStatus: 'error', statusMessage: msg });
      return { success: false, message: msg };
    }

    set({ connectionStatus: 'checking', statusMessage: 'Testing connection...' });

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3500);

    try {
      const response = await fetch(`${apiBase}/health`, {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (response.ok) {
        const msg = `Connected successfully (${response.status} OK)`;
        set({ connectionStatus: 'connected', statusMessage: msg });
        return { success: true, message: msg };
      } else {
        const msg = `Server returned status ${response.status}`;
        set({ connectionStatus: 'error', statusMessage: msg });
        return { success: false, message: msg };
      }
    } catch (err: any) {
      clearTimeout(timeoutId);
      const isTimeout = err?.name === 'AbortError';
      const msg = isTimeout
        ? 'Connection timed out (no response in 3.5s). Verify IP and Mac firewall.'
        : `Connection failed: ${err?.message || 'Network unreachable'}`;
      set({ connectionStatus: 'error', statusMessage: msg });
      return { success: false, message: msg };
    }
  },
}));
