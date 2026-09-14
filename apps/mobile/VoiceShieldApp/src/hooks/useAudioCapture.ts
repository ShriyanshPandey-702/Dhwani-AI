import { useState, useEffect, useCallback, useRef } from 'react';
import { Platform, PermissionsAndroid, PermissionStatus } from 'react-native';
import {
  audioCaptureService,
  AudioCaptureMetrics,
} from '../services/audio/audioCaptureService';

export type MicPermissionState = 'undetermined' | 'granted' | 'denied' | 'blocked';

export interface UseAudioCaptureReturn {
  isRecording: boolean;
  permissionStatus: MicPermissionState;
  error: string | null;
  metrics: AudioCaptureMetrics;
  requestPermission: () => Promise<boolean>;
  start: () => Promise<boolean>;
  stop: () => Promise<void>;
}

/**
 * React hook managing native audio capture lifecycle and permissions.
 *
 * Automatically stops audio capture and releases native resources when the
 * consuming component unmounts.
 */
export const useAudioCapture = (autoStart: boolean = false): UseAudioCaptureReturn => {
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [permissionStatus, setPermissionStatus] = useState<MicPermissionState>('undetermined');
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<AudioCaptureMetrics>(audioCaptureService.getMetrics());

  const isMountedRef = useRef<boolean>(true);

  // Poll metrics periodically while recording for UI telemetry
  useEffect(() => {
    if (!isRecording) {
      return;
    }

    const interval = setInterval(() => {
      if (isMountedRef.current) {
        setMetrics(audioCaptureService.getMetrics());
      }
    }, 500);

    return () => clearInterval(interval);
  }, [isRecording]);

  // Subscribe to audio capture errors
  useEffect(() => {
    const unsub = audioCaptureService.onError(err => {
      if (isMountedRef.current) {
        setError(`${err.code}: ${err.message}`);
        setIsRecording(false);
      }
    });

    return () => {
      unsub();
    };
  }, []);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (Platform.OS !== 'android') {
      setPermissionStatus('denied');
      return false;
    }

    try {
      const hasPermission = await PermissionsAndroid.check(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      );

      if (hasPermission) {
        if (isMountedRef.current) {
          setPermissionStatus('granted');
        }
        return true;
      }

      const status: PermissionStatus = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
        {
          title: 'Microphone Permission',
          message:
            'VoiceShield requires microphone access to analyze voice authenticity during monitored calls.',
          buttonNeutral: 'Ask Me Later',
          buttonNegative: 'Cancel',
          buttonPositive: 'Grant Access',
        },
      );

      if (status === PermissionsAndroid.RESULTS.GRANTED) {
        if (isMountedRef.current) {
          setPermissionStatus('granted');
        }
        return true;
      } else if (status === PermissionsAndroid.RESULTS.NEVER_ASK_AGAIN) {
        if (isMountedRef.current) {
          setPermissionStatus('blocked');
        }
        return false;
      } else {
        if (isMountedRef.current) {
          setPermissionStatus('denied');
        }
        return false;
      }
    } catch (e: any) {
      if (isMountedRef.current) {
        setError(e?.message || 'Permission request failed');
        setPermissionStatus('denied');
      }
      return false;
    }
  }, []);

  const start = useCallback(async (): Promise<boolean> => {
    setError(null);

    const hasPerm = await requestPermission();
    if (!hasPerm) {
      return false;
    }

    try {
      await audioCaptureService.startCapture();
      if (isMountedRef.current) {
        setIsRecording(true);
        setMetrics(audioCaptureService.getMetrics());
      }
      return true;
    } catch (e: any) {
      if (isMountedRef.current) {
        setError(e?.message || 'Failed to start microphone capture');
        setIsRecording(false);
      }
      return false;
    }
  }, [requestPermission]);

  const stop = useCallback(async (): Promise<void> => {
    try {
      await audioCaptureService.stopCapture();
    } finally {
      if (isMountedRef.current) {
        setIsRecording(false);
        setMetrics(audioCaptureService.getMetrics());
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;

    if (autoStart) {
      start();
    }

    return () => {
      isMountedRef.current = false;
      audioCaptureService.stopCapture();
    };
  }, [autoStart, start]);

  return {
    isRecording,
    permissionStatus,
    error,
    metrics,
    requestPermission,
    start,
    stop,
  };
};
