import AsyncStorage from '@react-native-async-storage/async-storage';
import { WS_BASE_URL } from '../../config/api';

export type ConnectionState =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'
  | 'failed';

type EventHandler = (event: unknown) => void;
type StateHandler = (state: ConnectionState) => void;

/**
 * Single WebSocket connection to the risk stream.
 *
 * Responsibilities are deliberately narrow: connect, authenticate, keep alive,
 * reconnect with backoff, and hand raw parsed messages to subscribers. All
 * interpretation of events lives in the Zustand store, so reconnection logic
 * and dashboard logic can be tested independently.
 */
class WebSocketService {
  private ws: WebSocket | null = null;
  private sessionId: string | null = null;
  private handlers = new Set<EventHandler>();
  private stateHandlers = new Set<StateHandler>();
  private pingTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect = false;
  private reconnectAttempts = 0;
  private connectionState: ConnectionState = 'idle';
  // Settled when the socket first reaches OPEN, so callers can safely send
  // immediately after `connect()` resolves rather than guessing with a timer.
  private openResolve: (() => void) | null = null;
  private openReject: ((error: Error) => void) | null = null;

  private readonly MAX_RECONNECT = 5;
  private readonly PING_INTERVAL_MS = 20000;

  /** Resolves once the socket is actually OPEN, or rejects if it cannot connect. */
  async connect(sessionId: string): Promise<void> {
    const token = await AsyncStorage.getItem('access_token');
    if (!token) {
      this.setState('failed');
      throw new Error('No access token');
    }
    this.sessionId = sessionId;
    this.shouldReconnect = true;
    this.reconnectAttempts = 0;

    return new Promise<void>((resolve, reject) => {
      this.openResolve = resolve;
      this.openReject = reject;
      this.open(token);
    });
  }

  private settleOpen(error?: Error) {
    const resolve = this.openResolve;
    const reject = this.openReject;
    this.openResolve = null;
    this.openReject = null;
    if (error) {
      reject?.(error);
    } else {
      resolve?.();
    }
  }

  private open(token: string) {
    this.setState(this.reconnectAttempts > 0 ? 'reconnecting' : 'connecting');

    // The token travels as a query parameter because React Native's WebSocket
    // cannot set request headers. The backend validates it before accepting.
    const url = `${WS_BASE_URL}/ws/sessions/${this.sessionId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.setState('open');
      this.startPing();
      this.settleOpen();
    };

    ws.onmessage = event => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data as string);
      } catch {
        // A malformed frame is dropped; the stream continues.
        return;
      }
      this.handlers.forEach(handler => {
        try {
          handler(parsed);
        } catch {
          // One misbehaving subscriber must not break the others.
        }
      });
    };

    ws.onerror = () => {
      // `onclose` always follows, which is where reconnection is decided.
    };

    ws.onclose = () => {
      this.stopPing();
      if (!this.shouldReconnect) {
        this.setState('closed');
        this.settleOpen(new Error('WebSocket closed before opening'));
        return;
      }
      if (this.reconnectAttempts >= this.MAX_RECONNECT) {
        this.setState('failed');
        this.settleOpen(new Error('WebSocket reconnect attempts exhausted'));
        return;
      }
      const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 15000);
      this.reconnectAttempts += 1;
      this.setState('reconnecting');
      this.reconnectTimer = setTimeout(async () => {
        const nextToken = await AsyncStorage.getItem('access_token');
        if (nextToken && this.shouldReconnect) {
          this.open(nextToken);
        } else {
          this.setState('failed');
          this.settleOpen(new Error('No access token on reconnect'));
        }
      }, delay);
    };
  }

  /** Send a message if the socket is open; returns whether it was sent. */
  send(message: Record<string, unknown>): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      return false;
    }
    this.ws.send(JSON.stringify(message));
    return true;
  }

  sendAudioChunk(base64Data: string, seq?: number): boolean {
    const payload: Record<string, unknown> = { type: 'audio_chunk', data: base64Data };
    if (typeof seq === 'number') {
      payload.seq = seq;
    }
    return this.send(payload);
  }

  /** Ask the backend to run the DEVELOPMENT MOCK AUDIO scenario. */
  startDemo(): boolean {
    return this.send({ type: 'start_demo' });
  }

  stopDemo(): boolean {
    return this.send({ type: 'stop_demo' });
  }

  disconnect() {
    this.shouldReconnect = false;
    this.settleOpen(new Error('Disconnected before opening'));
    this.stopPing();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
    this.sessionId = null;
    this.setState('closed');
  }

  addHandler(fn: EventHandler): () => void {
    this.handlers.add(fn);
    return () => {
      this.handlers.delete(fn);
    };
  }

  addStateHandler(fn: StateHandler): () => void {
    this.stateHandlers.add(fn);
    return () => {
      this.stateHandlers.delete(fn);
    };
  }

  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  get state(): ConnectionState {
    return this.connectionState;
  }

  private setState(next: ConnectionState) {
    this.connectionState = next;
    this.stateHandlers.forEach(handler => {
      try {
        handler(next);
      } catch {
        // Ignore subscriber errors.
      }
    });
  }

  private startPing() {
    this.stopPing();
    this.pingTimer = setInterval(() => {
      this.send({ type: 'ping' });
    }, this.PING_INTERVAL_MS);
  }

  private stopPing() {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }
}

export const wsService = new WebSocketService();
