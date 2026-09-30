import { NativeModules, NativeEventEmitter, Platform } from 'react-native';

// Set platform to android
(Platform as any).OS = 'android';

const mockStartCapture = jest.fn();
const mockStopCapture = jest.fn();
const mockCheckPermission = jest.fn();
const mockIsCapturing = jest.fn();

let chunkListener: ((chunk: any) => void) | null = null;
let errorListener: ((error: any) => void) | null = null;

NativeModules.VoiceShieldAudioCapture = {
  startCapture: mockStartCapture,
  stopCapture: mockStopCapture,
  checkPermission: mockCheckPermission,
  isCapturing: mockIsCapturing,
  addListener: jest.fn(),
  removeListeners: jest.fn(),
};

jest.spyOn(NativeEventEmitter.prototype, 'addListener').mockImplementation(function (
  event: any,
  callback: any,
) {
  if (event === 'onAudioChunk') {
    chunkListener = callback;
  } else if (event === 'onAudioCaptureError') {
    errorListener = callback;
  }
  return {
    remove: jest.fn(),
  } as any;
});

import { audioCaptureService } from '../src/services/audio/audioCaptureService';
import { wsService } from '../src/services/websocket/wsService';

describe('audioCaptureService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    chunkListener = null;
    errorListener = null;
    mockStartCapture.mockResolvedValue({ started: true, sampleRate: 16000 });
    mockStopCapture.mockResolvedValue({ stopped: true });
    mockCheckPermission.mockResolvedValue('granted');
    mockIsCapturing.mockResolvedValue(false);
  });

  afterEach(async () => {
    await audioCaptureService.stopCapture();
  });

  it('checks permission on Android platform', async () => {
    const status = await audioCaptureService.checkPermission();
    expect(status).toBe('granted');
    expect(mockCheckPermission).toHaveBeenCalledTimes(1);
  });

  it('starts capture and registers event listeners', async () => {
    await audioCaptureService.startCapture();
    expect(audioCaptureService.isActive()).toBe(true);
    expect(mockStartCapture).toHaveBeenCalledTimes(1);
  });

  it('preserves native sequence number when forwarding to wsService', async () => {
    const sendSpy = jest.spyOn(wsService, 'sendAudioChunk').mockReturnValue(true);

    await audioCaptureService.startCapture();

    expect(chunkListener).toBeDefined();

    // Simulate 3 incoming native chunks with native sequence numbers 0, 1, 2
    chunkListener!({
      data: 'b64chunk0',
      seq: 0,
      timestamp: 1000,
      byteLength: 8000,
      samples: 4000,
    });

    expect(sendSpy).toHaveBeenLastCalledWith('b64chunk0', 0);

    chunkListener!({
      data: 'b64chunk1',
      seq: 1,
      timestamp: 1250,
      byteLength: 8000,
      samples: 4000,
    });

    expect(sendSpy).toHaveBeenLastCalledWith('b64chunk1', 1);

    chunkListener!({
      data: 'b64chunk2',
      seq: 2,
      timestamp: 1500,
      byteLength: 8000,
      samples: 4000,
    });

    expect(sendSpy).toHaveBeenLastCalledWith('b64chunk2', 2);

    const metrics = audioCaptureService.getMetrics();
    expect(metrics.chunksReceived).toBe(3);
    expect(metrics.chunksSent).toBe(3);
    expect(metrics.chunksDropped).toBe(0);
    expect(metrics.lastSeq).toBe(2);

    sendSpy.mockRestore();
  });

  it('tracks dropped chunks and preserves sequence gaps when wsService cannot send', async () => {
    const sendSpy = jest.spyOn(wsService, 'sendAudioChunk');
    // First chunk succeeds, second chunk fails (drop), third chunk succeeds
    sendSpy.mockReturnValueOnce(true).mockReturnValueOnce(false).mockReturnValueOnce(true);

    await audioCaptureService.startCapture();

    // Chunk 0 sent
    chunkListener!({
      data: 'b64chunk0',
      seq: 0,
      timestamp: 1000,
      byteLength: 8000,
      samples: 4000,
    });

    // Chunk 1 dropped (e.g. socket reconnecting)
    chunkListener!({
      data: 'b64chunk1',
      seq: 1,
      timestamp: 1250,
      byteLength: 8000,
      samples: 4000,
    });

    // Chunk 2 sent (gap: seq jumps 0 -> 2)
    chunkListener!({
      data: 'b64chunk2',
      seq: 2,
      timestamp: 1500,
      byteLength: 8000,
      samples: 4000,
    });

    expect(sendSpy).toHaveBeenCalledTimes(3);
    expect(sendSpy).toHaveBeenNthCalledWith(1, 'b64chunk0', 0);
    expect(sendSpy).toHaveBeenNthCalledWith(2, 'b64chunk1', 1);
    expect(sendSpy).toHaveBeenNthCalledWith(3, 'b64chunk2', 2);

    const metrics = audioCaptureService.getMetrics();
    expect(metrics.chunksReceived).toBe(3);
    expect(metrics.chunksSent).toBe(2);
    expect(metrics.chunksDropped).toBe(1);
    expect(metrics.lastSeq).toBe(2);

    sendSpy.mockRestore();
  });

  it('handles native capture error events', async () => {
    const errorHandler = jest.fn();
    const unsub = audioCaptureService.onError(errorHandler);

    await audioCaptureService.startCapture();

    expect(errorListener).toBeDefined();
    errorListener!({ code: 'MIC_UNAVAILABLE', message: 'Mic in use' });

    expect(errorHandler).toHaveBeenCalledWith({
      code: 'MIC_UNAVAILABLE',
      message: 'Mic in use',
    });

    unsub();
  });

  it('stops capture cleanly and tears down subscriptions', async () => {
    await audioCaptureService.startCapture();
    expect(audioCaptureService.isActive()).toBe(true);

    await audioCaptureService.stopCapture();
    expect(audioCaptureService.isActive()).toBe(false);
    expect(mockStopCapture).toHaveBeenCalledTimes(1);
  });

  it('calculates real RMS and emits onAudioLevel', async () => {
    const levelSpy = jest.fn();
    const unsub = audioCaptureService.onAudioLevel(levelSpy);

    await audioCaptureService.startCapture();
    expect(chunkListener).toBeDefined();

    // Base64 chunk for zero signal (silence)
    chunkListener!({ data: 'AAAAAAAAAAAAAAAA', seq: 1 });
    expect(levelSpy).toHaveBeenCalledWith(0);

    unsub();
  });
});
