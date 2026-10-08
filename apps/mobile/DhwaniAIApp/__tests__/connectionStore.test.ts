import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  useConnectionStore,
  getApiBaseUrl,
  getWsBaseUrl,
  sanitizeHostPort,
} from '../src/store/connectionStore';

describe('connectionStore', () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    await AsyncStorage.clear();
    // Reset store state
    useConnectionStore.setState({
      mode: 'usb',
      wifiHost: '',
      wifiPort: '8000',
      isLoaded: false,
      connectionStatus: 'idle',
      statusMessage: null,
    });
  });

  describe('sanitizeHostPort', () => {
    it('returns invalid when host is empty', () => {
      const res = sanitizeHostPort('', '8000');
      expect(res.isValid).toBe(false);
      expect(res.error).toBeDefined();
    });

    it('returns invalid when host is only whitespace', () => {
      const res = sanitizeHostPort('   ', '8000');
      expect(res.isValid).toBe(false);
    });

    it('sanitizes clean IPv4 and port', () => {
      const res = sanitizeHostPort('192.168.1.42', '8000');
      expect(res.isValid).toBe(true);
      expect(res.host).toBe('192.168.1.42');
      expect(res.port).toBe('8000');
    });

    it('strips http:// and trailing slashes', () => {
      const res = sanitizeHostPort('http://192.168.1.42/', '8000');
      expect(res.isValid).toBe(true);
      expect(res.host).toBe('192.168.1.42');
      expect(res.port).toBe('8000');
    });

    it('strips ws:// and wss://', () => {
      const res = sanitizeHostPort('ws://192.168.1.50', '9000');
      expect(res.isValid).toBe(true);
      expect(res.host).toBe('192.168.1.50');
      expect(res.port).toBe('9000');
    });

    it('extracts port embedded in host field', () => {
      const res = sanitizeHostPort('192.168.1.99:8080', '');
      expect(res.isValid).toBe(true);
      expect(res.host).toBe('192.168.1.99');
      expect(res.port).toBe('8080');
    });

    it('rejects invalid port numbers', () => {
      const resLow = sanitizeHostPort('192.168.1.1', '0');
      expect(resLow.isValid).toBe(false);

      const resHigh = sanitizeHostPort('192.168.1.1', '70000');
      expect(resHigh.isValid).toBe(false);

      const resNaN = sanitizeHostPort('192.168.1.1', 'abcd');
      expect(resNaN.isValid).toBe(false);
    });
  });

  describe('URL Resolution', () => {
    it('defaults to localhost:8000 in USB mode', () => {
      expect(getApiBaseUrl()).toBe('http://localhost:8000');
      expect(getWsBaseUrl()).toBe('ws://localhost:8000');
    });

    it('returns null in Wi-Fi mode when host is empty', async () => {
      await useConnectionStore.getState().setMode('wifi');
      expect(getApiBaseUrl()).toBeNull();
      expect(getWsBaseUrl()).toBeNull();
    });

    it('constructs correct URLs in Wi-Fi mode when configured', async () => {
      await useConnectionStore.getState().setMode('wifi');
      await useConnectionStore.getState().setWifiHost('192.168.1.15');
      await useConnectionStore.getState().setWifiPort('8000');

      expect(getApiBaseUrl()).toBe('http://192.168.1.15:8000');
      expect(getWsBaseUrl()).toBe('ws://192.168.1.15:8000');
    });

    it('sanitizes user input in Wi-Fi mode', async () => {
      await useConnectionStore.getState().setMode('wifi');
      await useConnectionStore.getState().setWifiHost('http://10.0.0.5/');
      await useConnectionStore.getState().setWifiPort('8080');

      expect(getApiBaseUrl()).toBe('http://10.0.0.5:8080');
      expect(getWsBaseUrl()).toBe('ws://10.0.0.5:8080');
    });
  });

  describe('Persistence & Rehydration', () => {
    it('persists and reloads config from AsyncStorage', async () => {
      await useConnectionStore.getState().setMode('wifi');
      await useConnectionStore.getState().setWifiHost('192.168.1.55');
      await useConnectionStore.getState().setWifiPort('8001');

      // Reset in-memory state
      useConnectionStore.setState({
        mode: 'usb',
        wifiHost: '',
        wifiPort: '8000',
        isLoaded: false,
      });

      // Load config from AsyncStorage
      await useConnectionStore.getState().loadConfig();

      const state = useConnectionStore.getState();
      expect(state.mode).toBe('wifi');
      expect(state.wifiHost).toBe('192.168.1.55');
      expect(state.wifiPort).toBe('8001');
      expect(state.isLoaded).toBe(true);
      expect(getApiBaseUrl()).toBe('http://192.168.1.55:8001');
    });
  });

  describe('testConnection', () => {
    it('fails immediately when Wi-Fi host is unconfigured', async () => {
      await useConnectionStore.getState().setMode('wifi');
      const result = await useConnectionStore.getState().testConnection();

      expect(result.success).toBe(false);
      expect(useConnectionStore.getState().connectionStatus).toBe('error');
      expect(useConnectionStore.getState().statusMessage).toContain('valid Mac LAN host IP');
    });
  });
});
