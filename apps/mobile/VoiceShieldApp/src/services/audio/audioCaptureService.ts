import { NativeModules, NativeEventEmitter, Platform } from 'react-native';
import { wsService } from '../websocket/wsService';

export interface AudioChunkPayload {
  data: string;
  seq: number;
  timestamp: number;
  byteLength: number;
  samples: number;
}

export interface AudioCaptureError {
  code: string;
  message: string;
}

export interface AudioCaptureMetrics {
  chunksReceived: number;
  chunksSent: number;
  chunksDropped: number;
  lastSeq: number;
}

type AudioErrorHandler = (error: AudioCaptureError) => void;
type ChunkHandler = (chunk: AudioChunkPayload) => void;

const LINKING_ERROR =
  "The package 'VoiceShieldAudioCapture' doesn't seem to be linked. Make sure: \n\n" +
  Platform.select({ ios: "- You have run 'pod install'\n", default: '' }) +
  '- You rebuilt the app after installing the package\n' +
  '- You are not using Expo Go\n';

function getNativeModule() {
  if (NativeModules.VoiceShieldAudioCapture) {
    return NativeModules.VoiceShieldAudioCapture;
  }
  return new Proxy(
    {},
    {
      get() {
        throw new Error(LINKING_ERROR);
      },
    },
  );
}

/**
 * Service orchestrating native audio capture and forwarding raw PCM chunks
 * directly to the Dhwani AI WebSocket gateway.
 *
 * Sequence Number Invariant:
 * The native AudioRecord module is the sole owner of sequence numbers
 * (`seq = 0, 1, 2, 3...`). This service forwards the native `seq` directly
 * without generating, altering, or re-indexing sequence values.
 */
class AudioCaptureService {
  private eventEmitter: NativeEventEmitter | null = null;
  private chunkSubscription: any = null;
  private errorSubscription: any = null;

  private isRunning: boolean = false;
  private errorHandlers: Set<AudioErrorHandler> = new Set();
  private chunkHandlers: Set<ChunkHandler> = new Set();

  private metrics: AudioCaptureMetrics = {
    chunksReceived: 0,
    chunksSent: 0,
    chunksDropped: 0,
    lastSeq: -1,
  };

  constructor() {
    if (NativeModules.VoiceShieldAudioCapture) {
      this.eventEmitter = new NativeEventEmitter(NativeModules.VoiceShieldAudioCapture);
    }
  }

  /**
   * Reset local metrics for a new capture session.
   */
  private resetMetrics() {
    this.metrics = {
      chunksReceived: 0,
      chunksSent: 0,
      chunksDropped: 0,
      lastSeq: -1,
    };
  }

  /**
   * Check whether microphone permission is granted on the device.
   */
  async checkPermission(): Promise<'granted' | 'denied'> {
    if (Platform.OS !== 'android') {
      return 'denied';
    }
    return getNativeModule().checkPermission();
  }

  /**
   * Query whether the native AudioRecord thread is active.
   */
  async isCapturing(): Promise<boolean> {
    if (Platform.OS !== 'android') {
      return false;
    }
    return getNativeModule().isCapturing();
  }

  /**
   * Start native microphone capture and wire the event stream to wsService.
   */
  async startCapture(): Promise<void> {
    if (this.isRunning) {
      return;
    }

    if (Platform.OS !== 'android') {
      throw new Error('Native audio capture is currently supported on Android only.');
    }

    this.resetMetrics();

    if (!this.eventEmitter && NativeModules.VoiceShieldAudioCapture) {
      this.eventEmitter = new NativeEventEmitter(NativeModules.VoiceShieldAudioCapture);
    }

    if (this.eventEmitter) {
      this.chunkSubscription = this.eventEmitter.addListener(
        'onAudioChunk',
        (payload: any) => {
          this.handleIncomingChunk(payload as AudioChunkPayload);
        },
      );

      this.errorSubscription = this.eventEmitter.addListener(
        'onAudioCaptureError',
        (error: any) => {
          this.handleCaptureError(error as AudioCaptureError);
        },
      );
    }

    try {
      await getNativeModule().startCapture(null);
      this.isRunning = true;
    } catch (err) {
      this.teardownSubscriptions();
      throw err;
    }
  }

  /**
   * Stop native microphone capture and detach event listeners.
   */
  async stopCapture(): Promise<void> {
    if (!this.isRunning) {
      return;
    }

    this.isRunning = false;
    this.teardownSubscriptions();

    if (Platform.OS === 'android') {
      try {
        await getNativeModule().stopCapture();
      } catch {
        // Native module may already be released
      }
    }
  }

  private teardownSubscriptions() {
    if (this.chunkSubscription) {
      this.chunkSubscription.remove();
      this.chunkSubscription = null;
    }
    if (this.errorSubscription) {
      this.errorSubscription.remove();
      this.errorSubscription = null;
    }
  }

  /**
   * Handle one incoming native chunk and forward to WebSocket gateway.
   * Preserves native sequence number authoritative ownership.
   */
  private handleIncomingChunk(chunk: AudioChunkPayload) {
    this.metrics.chunksReceived += 1;
    this.metrics.lastSeq = chunk.seq;

    // Notify any local subscribers/listeners
    for (const handler of this.chunkHandlers) {
      try {
        handler(chunk);
      } catch {}
    }

    // Forward to WebSocket gateway with the native sequence number
    const sent = wsService.sendAudioChunk(chunk.data, chunk.seq);
    if (sent) {
      this.metrics.chunksSent += 1;
    } else {
      // Socket was not open or send failed: drop immediately to protect real-time freshness
      this.metrics.chunksDropped += 1;
    }
  }

  private handleCaptureError(error: AudioCaptureError) {
    for (const handler of this.errorHandlers) {
      try {
        handler(error);
      } catch {}
    }
  }

  onError(handler: AudioErrorHandler): () => void {
    this.errorHandlers.add(handler);
    return () => {
      this.errorHandlers.delete(handler);
    };
  }

  onChunk(handler: ChunkHandler): () => void {
    this.chunkHandlers.add(handler);
    return () => {
      this.chunkHandlers.delete(handler);
    };
  }

  getMetrics(): AudioCaptureMetrics {
    return { ...this.metrics };
  }

  isActive(): boolean {
    return this.isRunning;
  }
}

export const audioCaptureService = new AudioCaptureService();
