/**
 * useLiveDemoPlayback Hook
 * =========================
 * Drives the Dhwani AI Live Analysis Presentation Demo.
 *
 * Single Source of Truth:
 *   Native audio playback position (`audio.currentTime`) drives every visual state:
 *   - Live Risk Score (smoothly interpolated)
 *   - Real audio waveform (fluctuating with audio, flat line in silence)
 *   - Progressive live transcript (Hindi, silence, cloned, silence, AI-generated)
 *   - Warning card, Decision panel, Authenticity, Identity, Active Liveness, Consequences, Events
 *
 * Full Playback Controls:
 *   - start()
 *   - pause()   -> freezes audio, score, waveform, transcript, and UI state
 *   - resume()  -> continues from exact currentTime
 *   - restart() -> resets audio to 0s, restarts from 0
 *   - stop()    -> stops audio, resets to initial state
 *   - seek(t)   -> seeks audio and timeline
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { NativeModules, Platform } from 'react-native';
import {
  DEMO_TOTAL_DURATION,
  getDemoPhase,
  getDemoTranscript,
  getDemoTargetRisk,
  getDemoWaveform,
  getDemoMultimodalState,
  DemoPhase,
  DemoTranscriptState,
  DemoRiskState,
  DemoMultimodalState,
} from '../utils/demoLiveEngine';

export type PlaybackStatus = 'idle' | 'playing' | 'paused' | 'ended';

export interface UseLiveDemoPlaybackReturn {
  currentTime: number;
  totalDuration: number;
  playbackStatus: PlaybackStatus;
  phase: DemoPhase;
  displayedScore: number;
  riskState: DemoRiskState['riskState'];
  riskTrend: DemoRiskState['riskTrend'];
  sublabel: string;
  transcriptState: DemoTranscriptState;
  waveformState: { rms: number; bars: number[]; isSilence: boolean };
  multimodalState: DemoMultimodalState;
  start: () => Promise<void>;
  pause: () => Promise<void>;
  resume: () => Promise<void>;
  restart: () => Promise<void>;
  stop: () => Promise<void>;
  seek: (seconds: number) => Promise<void>;
}

const DEMO_AUDIO_ASSET = 'recording_samples/demo_merged_actual.wav';
const TICK_INTERVAL_MS = 50; // 20 fps update loop for fluid UI response

export const useLiveDemoPlayback = (autoStart: boolean = true): UseLiveDemoPlaybackReturn => {
  const [currentTime, setCurrentTime] = useState<number>(0);
  const [playbackStatus, setPlaybackStatus] = useState<PlaybackStatus>('idle');
  const [displayedScore, setDisplayedScore] = useState<number>(0);

  const currentTimeRef = useRef<number>(0);
  const displayedScoreRef = useRef<number>(0);
  const playbackStatusRef = useRef<PlaybackStatus>('idle');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fallback high-res timer tracking
  const wallClockStartRef = useRef<number>(0);
  const wallClockOffsetRef = useRef<number>(0);

  const nativeModule = NativeModules.VoiceShieldAudioCapture;

  // ── Sync loop: polls native MediaPlayer or runs high-precision wallclock ──
  const tick = useCallback(async () => {
    if (playbackStatusRef.current !== 'playing') return;

    let newCurrentTime = currentTimeRef.current;

    // 1. Try querying native MediaPlayer position while playing
    let polledNative = false;
    if (Platform.OS === 'android' && nativeModule?.getMediaStatus) {
      try {
        const status = await nativeModule.getMediaStatus();
        if (playbackStatusRef.current !== 'playing') return;
        if (status && typeof status.positionMs === 'number' && status.positionMs > 0) {
          const posSec = status.positionMs / 1000;
          if (status.isPlaying) {
            newCurrentTime = Math.min(DEMO_TOTAL_DURATION, posSec);
            wallClockStartRef.current = Date.now() - newCurrentTime * 1000;
            polledNative = true;
          }
        }
      } catch {}
    }

    if (playbackStatusRef.current !== 'playing') return;

    // 2. High-precision fallback / post-audio decay progression
    if (!polledNative) {
      const now = Date.now();
      const elapsed = (now - wallClockStartRef.current) / 1000 + wallClockOffsetRef.current;
      newCurrentTime = Math.min(DEMO_TOTAL_DURATION, Math.max(0, elapsed));
    }

    currentTimeRef.current = newCurrentTime;
    setCurrentTime(newCurrentTime);

    // 3. Smooth Score Interpolation: displayedScore += (targetScore - displayedScore) * 0.18
    const riskInfo = getDemoTargetRisk(newCurrentTime);
    const target = riskInfo.targetScore;
    const current = displayedScoreRef.current;
    const diff = target - current;

    let nextScore: number;
    if (Math.abs(diff) < 0.5) {
      nextScore = target;
    } else {
      nextScore = current + diff * 0.18;
    }

    displayedScoreRef.current = nextScore;
    setDisplayedScore(Math.round(nextScore));

    // 4. Complete session when total duration elapsed and score has fully decayed to 0
    if (newCurrentTime >= DEMO_TOTAL_DURATION && Math.round(nextScore) <= 0) {
      displayedScoreRef.current = 0;
      setDisplayedScore(0);
      playbackStatusRef.current = 'ended';
      setPlaybackStatus('ended');
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, [nativeModule]);

  const startTickLoop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(tick, TICK_INTERVAL_MS);
  }, [tick]);

  const stopTickLoop = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  // ── Playback Controls ──────────────────────────────────────────────────────

  const start = useCallback(async () => {
    playbackStatusRef.current = 'playing';
    setPlaybackStatus('playing');
    currentTimeRef.current = 0;
    setCurrentTime(0);
    displayedScoreRef.current = 0;
    setDisplayedScore(0);
    wallClockStartRef.current = Date.now();
    wallClockOffsetRef.current = 0;

    startTickLoop();

    if (Platform.OS === 'android' && nativeModule?.playMediaUri) {
      try {
        await nativeModule.playMediaUri(DEMO_AUDIO_ASSET);
      } catch (err) {
        console.warn('[LiveDemo] Native playMediaUri failed, using internal clock:', err);
      }
    }
  }, [nativeModule, startTickLoop]);

  const pause = useCallback(async () => {
    playbackStatusRef.current = 'paused';
    setPlaybackStatus('paused');
    stopTickLoop();

    // Freeze wallclock offset
    wallClockOffsetRef.current = currentTimeRef.current;

    if (Platform.OS === 'android' && nativeModule?.pauseMediaUri) {
      try {
        await nativeModule.pauseMediaUri();
      } catch {}
    }
  }, [nativeModule, stopTickLoop]);

  const resume = useCallback(async () => {
    playbackStatusRef.current = 'playing';
    setPlaybackStatus('playing');
    wallClockStartRef.current = Date.now();
    wallClockOffsetRef.current = currentTimeRef.current;

    startTickLoop();

    if (Platform.OS === 'android' && nativeModule?.resumeMediaUri) {
      try {
        await nativeModule.resumeMediaUri();
      } catch {
        // If resume failed, try playMediaUri + seek
        try {
          await nativeModule.playMediaUri(DEMO_AUDIO_ASSET);
          if (nativeModule.seekMediaUri) {
            await nativeModule.seekMediaUri(Math.round(currentTimeRef.current * 1000));
          }
        } catch {}
      }
    }
  }, [nativeModule, startTickLoop]);

  const restart = useCallback(async () => {
    currentTimeRef.current = 0;
    setCurrentTime(0);
    displayedScoreRef.current = 0;
    setDisplayedScore(0);
    wallClockStartRef.current = Date.now();
    wallClockOffsetRef.current = 0;
    playbackStatusRef.current = 'playing';
    setPlaybackStatus('playing');

    startTickLoop();

    if (Platform.OS === 'android' && nativeModule) {
      try {
        if (nativeModule.seekMediaUri) {
          await nativeModule.seekMediaUri(0);
          await nativeModule.resumeMediaUri();
        } else {
          await nativeModule.stopMediaPlayback();
          await nativeModule.playMediaUri(DEMO_AUDIO_ASSET);
        }
      } catch {
        try {
          await nativeModule.playMediaUri(DEMO_AUDIO_ASSET);
        } catch {}
      }
    }
  }, [nativeModule, startTickLoop]);

  const stop = useCallback(async () => {
    stopTickLoop();
    playbackStatusRef.current = 'idle';
    setPlaybackStatus('idle');
    currentTimeRef.current = 0;
    setCurrentTime(0);
    displayedScoreRef.current = 0;
    setDisplayedScore(0);
    wallClockOffsetRef.current = 0;

    if (Platform.OS === 'android' && nativeModule?.stopMediaPlayback) {
      try {
        await nativeModule.stopMediaPlayback();
      } catch {}
    }
  }, [nativeModule, stopTickLoop]);

  const seek = useCallback(
    async (seconds: number) => {
      const clamped = Math.max(0, Math.min(DEMO_TOTAL_DURATION, seconds));
      currentTimeRef.current = clamped;
      setCurrentTime(clamped);
      wallClockStartRef.current = Date.now();
      wallClockOffsetRef.current = clamped;

      const riskInfo = getDemoTargetRisk(clamped);
      displayedScoreRef.current = riskInfo.targetScore;
      setDisplayedScore(riskInfo.targetScore);

      if (Platform.OS === 'android' && nativeModule?.seekMediaUri) {
        try {
          await nativeModule.seekMediaUri(Math.round(clamped * 1000));
        } catch {}
      }
    },
    [nativeModule]
  );

  // Auto-start on mount if requested
  useEffect(() => {
    if (autoStart) {
      start().catch(() => {});
    }
    return () => {
      stop().catch(() => {});
    };
  }, [autoStart, start, stop]);

  // Derived states driven strictly by currentTime
  const phase = getDemoPhase(currentTime);
  const riskInfo = getDemoTargetRisk(currentTime);
  const transcriptState = getDemoTranscript(currentTime);
  const waveformState = getDemoWaveform(currentTime);
  const multimodalState = getDemoMultimodalState(currentTime, displayedScore);

  return {
    currentTime,
    totalDuration: DEMO_TOTAL_DURATION,
    playbackStatus,
    phase,
    displayedScore,
    riskState: riskInfo.riskState,
    riskTrend: riskInfo.riskTrend,
    sublabel: riskInfo.sublabel,
    transcriptState,
    waveformState,
    multimodalState,
    start,
    pause,
    resume,
    restart,
    stop,
    seek,
  };
};
