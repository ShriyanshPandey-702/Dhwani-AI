import React from 'react';
import ReactTestRenderer, { act } from 'react-test-renderer';
import { NativeModules, NativeEventEmitter, Platform, PermissionsAndroid } from 'react-native';

(Platform as any).OS = 'android';

const mockStartCapture = jest.fn();
const mockStopCapture = jest.fn();
const mockCheckPermission = jest.fn();
const mockIsCapturing = jest.fn();

NativeModules.VoiceShieldAudioCapture = {
  startCapture: mockStartCapture,
  stopCapture: mockStopCapture,
  checkPermission: mockCheckPermission,
  isCapturing: mockIsCapturing,
  addListener: jest.fn(),
  removeListeners: jest.fn(),
};

jest.spyOn(NativeEventEmitter.prototype, 'addListener').mockImplementation(function () {
  return { remove: jest.fn() } as any;
});

import { useAudioCapture } from '../src/hooks/useAudioCapture';
import { audioCaptureService } from '../src/services/audio/audioCaptureService';

describe('useAudioCapture hook', () => {
  let hookValue: ReturnType<typeof useAudioCapture>;

  const TestConsumer: React.FC<{ autoStart?: boolean }> = ({ autoStart = false }) => {
    hookValue = useAudioCapture(autoStart);
    return null;
  };

  beforeEach(() => {
    jest.clearAllMocks();
    PermissionsAndroid.check = jest.fn().mockResolvedValue(true);
    PermissionsAndroid.request = jest.fn().mockResolvedValue(PermissionsAndroid.RESULTS.GRANTED);
    jest.spyOn(audioCaptureService, 'startCapture').mockResolvedValue();
    jest.spyOn(audioCaptureService, 'stopCapture').mockResolvedValue();
  });

  afterEach(async () => {
    jest.restoreAllMocks();
  });

  it('initializes with default idle state', () => {
    act(() => {
      ReactTestRenderer.create(<TestConsumer autoStart={false} />);
    });

    expect(hookValue.isRecording).toBe(false);
    expect(hookValue.permissionStatus).toBe('undetermined');
    expect(hookValue.error).toBeNull();
    expect(hookValue.metrics.chunksSent).toBe(0);
  });

  it('requests permission and starts capture on start()', async () => {
    let renderer: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      renderer = ReactTestRenderer.create(<TestConsumer autoStart={false} />);
    });

    let success: boolean = false;
    await act(async () => {
      success = await hookValue.start();
    });

    expect(success).toBe(true);
    expect(hookValue.isRecording).toBe(true);
    expect(hookValue.permissionStatus).toBe('granted');
    expect(audioCaptureService.startCapture).toHaveBeenCalledTimes(1);

    act(() => {
      renderer.unmount();
    });
  });

  it('handles permission denial gracefully', async () => {
    PermissionsAndroid.check = jest.fn().mockResolvedValue(false);
    PermissionsAndroid.request = jest.fn().mockResolvedValue(PermissionsAndroid.RESULTS.DENIED);

    let renderer: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      renderer = ReactTestRenderer.create(<TestConsumer autoStart={false} />);
    });

    let success: boolean = false;
    await act(async () => {
      success = await hookValue.start();
    });

    expect(success).toBe(false);
    expect(hookValue.isRecording).toBe(false);
    expect(hookValue.permissionStatus).toBe('denied');
    expect(audioCaptureService.startCapture).not.toHaveBeenCalled();

    act(() => {
      renderer.unmount();
    });
  });

  it('stops capture when stop() is called', async () => {
    let renderer: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      renderer = ReactTestRenderer.create(<TestConsumer autoStart={false} />);
    });

    await act(async () => {
      await hookValue.start();
    });
    expect(hookValue.isRecording).toBe(true);

    await act(async () => {
      await hookValue.stop();
    });
    expect(hookValue.isRecording).toBe(false);
    expect(audioCaptureService.stopCapture).toHaveBeenCalledTimes(1);

    act(() => {
      renderer.unmount();
    });
  });

  it('automatically stops capture on unmount', async () => {
    let renderer: ReactTestRenderer.ReactTestRenderer;
    act(() => {
      renderer = ReactTestRenderer.create(<TestConsumer autoStart={false} />);
    });

    await act(async () => {
      await hookValue.start();
    });

    act(() => {
      renderer.unmount();
    });

    expect(audioCaptureService.stopCapture).toHaveBeenCalled();
  });
});
