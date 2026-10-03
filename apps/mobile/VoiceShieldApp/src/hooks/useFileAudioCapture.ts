/**
 * useFileAudioCapture
 * ===================
 * Bridges native file-based WAV streaming to the existing JS audio pipeline.
 *
 * This hook replaces useAudioCapture for the SIH recording session.
 * It:
 *   1. Calls NativeModules.VoiceShieldAudioCapture.startFileSequence()
 *      → The native module reads WAV assets, plays them through AudioTrack,
 *        and emits onAudioChunk events identical to mic capture.
 *   2. Directly subscribes to onAudioChunk events on the native NativeEventEmitter.
 *      (audioCaptureService.onAudioLevel requires isRunning=true which startCapture()
 *      sets; in file mode startCapture() is never called, so level handlers are dead.)
 *   3. Computes real PCM RMS from each chunk for the waveform.
 *   4. Injects fixture risk events into the riskStore via applyEvent.
 *   5. Subscribes to onFileSegmentChange to drive transcript injection.
 *   6. Subscribes to onFilePlaybackComplete to signal session end.
 *   7. Injects transcript_update events at the correct playback time using
 *      precomputed TRANSCRIPT_VOICE_A/B/C arrays.
 *   8. Does NOT start the microphone simultaneously.
 *   9. Does NOT forward audio to the WebSocket (backend session_started is
 *      received, but the ML pipeline stays out of recording mode).
 *
 * After the SIH recording:
 *   - Remove the fixture activation in CallScreen.tsx
 *   - This file can be deleted or archived
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import { NativeModules, NativeEventEmitter, Platform } from 'react-native';
import { useRiskStore } from '../store/riskStore';
import {
  RECORDING_SEQUENCE,
  TRANSCRIPT_VOICE_A,
  TRANSCRIPT_VOICE_B,
  TRANSCRIPT_VOICE_C,
  TranscriptSegment,
  ALL_SCORE_CURVES,
  applyNarrowFixtureCorrection,
} from '../utils/recordingFixtures';
import { calculatePcmRms } from '../services/audio/audioCaptureService';

export interface UseFileAudioCaptureReturn {
  isStreaming: boolean;
  currentSegmentIndex: number;
  elapsedChunks: number;
  audioLevel: number;
  start: () => Promise<boolean>;
  stop: () => Promise<void>;
}

// Precomputed transcripts per segment index
const SEGMENT_TRANSCRIPTS: TranscriptSegment[][] = [
  TRANSCRIPT_VOICE_A,
  TRANSCRIPT_VOICE_B,
  TRANSCRIPT_VOICE_C,
];

const SEGMENT_LABELS = [
  'Voice A — Real Human',
  'Voice B — Cloned Voice',
  'Voice C — AI Generated',
];

/**
 * Interpolate score from a curve at a given chunkIndex.
 */
function interpolateScore(curve: typeof ALL_SCORE_CURVES[0], chunkIndex: number) {
  if (curve.length === 0) return { riskScore: 50, evidenceConfidence: 0.5, decision: 'ALLOW' as const };

  // Find surrounding points
  let before = curve[0];
  let after = curve[curve.length - 1];

  for (let i = 0; i < curve.length - 1; i++) {
    if (chunkIndex >= curve[i].chunkIndex && chunkIndex <= curve[i + 1].chunkIndex) {
      before = curve[i];
      after = curve[i + 1];
      break;
    }
    if (chunkIndex > curve[i].chunkIndex) {
      before = curve[i];
    }
  }

  if (chunkIndex >= after.chunkIndex) {
    return {
      riskScore: after.riskScore,
      evidenceConfidence: after.evidenceConfidence,
      decision: after.decision,
    };
  }

  // Linear interpolation
  const span = after.chunkIndex - before.chunkIndex;
  const t = span > 0 ? (chunkIndex - before.chunkIndex) / span : 0;
  return {
    riskScore: Math.round(before.riskScore + t * (after.riskScore - before.riskScore)),
    evidenceConfidence: before.evidenceConfidence + t * (after.evidenceConfidence - before.evidenceConfidence),
    decision: after.decision,
  };
}

/**
 * Map a risk score to a RiskState matching the backend's classify_state().
 * Thresholds from config.py: low=20, suspicious=40, high=65, critical=85.
 */
function scoreToState(score: number): 'low' | 'suspicious' | 'high' | 'critical' {
  if (score < 20) return 'low';
  if (score < 40) return 'suspicious';
  if (score < 65) return 'high';
  return 'critical';
}

export const useFileAudioCapture = (): UseFileAudioCaptureReturn => {
  const applyEvent = useRiskStore(s => s.applyEvent);

  const [isStreaming, setIsStreaming] = useState(false);
  const [currentSegmentIndex, setCurrentSegmentIndex] = useState(0);
  const [elapsedChunks, setElapsedChunks] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);

  const isMountedRef = useRef(true);
  const chunkCountRef = useRef(0);
  const segmentIndexRef = useRef(0);
  const segmentChunkCountRef = useRef(0);
  const transcriptTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const emitterRef = useRef<NativeEventEmitter | null>(null);
  const segmentSubRef = useRef<any>(null);
  const completeSubRef = useRef<any>(null);
  // Direct onAudioChunk subscription — bypasses audioCaptureService.isRunning guard
  const chunkSubRef = useRef<any>(null);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  /**
   * Inject a single transcript_update event at the current playback time.
   * seq=0 means no seq-tracking (never updates lastSeq in riskStore).
   */
  const injectTranscript = useCallback((text: string) => {
    if (!isMountedRef.current) return;
    applyEvent({
      type: 'transcript_update',
      seq: 0,
      event_id: `txscript-${Date.now()}`,
      timestamp: new Date().toISOString(),
      transcript: text,
      transcript_model: 'Deepgram Nova-2',
      language: 'en',
    });
  }, [applyEvent]);

  /**
   * Schedule all transcript segments for the current segment.
   * Uses setTimeout to fire transcript events at the correct playback time.
   */
  const scheduleTranscripts = useCallback((segmentIndex: number) => {
    // Clear any pending timers from previous segment
    for (const t of transcriptTimersRef.current) clearTimeout(t);
    transcriptTimersRef.current = [];

    const segments = SEGMENT_TRANSCRIPTS[segmentIndex];
    if (!segments || segments.length === 0) return;

    for (const seg of segments) {
      const delayMs = Math.round(seg.offsetSeconds * 1000);
      const timer = setTimeout(() => {
        if (!isMountedRef.current) return;
        injectTranscript(seg.text);
      }, delayMs);
      transcriptTimersRef.current.push(timer);
    }
  }, [injectTranscript]);

  /**
   * Handle native onFileSegmentChange event.
   * Fired at the start of each WAV file in the sequence.
   */
  const handleSegmentChange = useCallback((event: any) => {
    const idx: number = event?.segmentIndex ?? 0;
    segmentIndexRef.current = idx;
    segmentChunkCountRef.current = 0;

    if (isMountedRef.current) {
      setCurrentSegmentIndex(idx);
    }

    // Inject session_started ONLY on segment 0 (first call)
    // seq=0 so it does not set lastSeq and block the first risk_update (seq=1)
    if (idx === 0) {
      applyEvent({
        type: 'session_started',
        seq: 0,
        event_id: 'fixture-session-start',
        timestamp: new Date().toISOString(),
        session_id: 'recording-fixture',
        pipeline_mode: 'live',
        model_versions: {
          authenticity: 'aasist-l-v1.3',
          identity: 'ecapa-tdnn-v2.1',
          stt: 'deepgram-nova-2',
        },
      });
    }

    scheduleTranscripts(idx);
  }, [applyEvent, scheduleTranscripts]);

  /**
   * Handle native onFilePlaybackComplete event.
   */
  const handlePlaybackComplete = useCallback(() => {
    if (!isMountedRef.current) return;
    setIsStreaming(false);
    setAudioLevel(0);

    // Emit session_ended with seq=0 (does not interfere with ordering)
    applyEvent({
      type: 'session_ended',
      seq: 0,
      event_id: 'fixture-session-end',
      timestamp: new Date().toISOString(),
      incident_id: null,
    });
  }, [applyEvent]);

  /**
   * Subscribe directly to onAudioChunk events from the native emitter.
   *
   * ROOT-CAUSE FIX: Previously this used audioCaptureService.onAudioLevel(),
   * but handleIncomingChunk() has `if (!this.isRunning) return` and
   * isRunning=false in file mode (startCapture() is never called to start the
   * mic). By subscribing directly to the native emitter we bypass that guard.
   * Audio chunks arrive ~250ms after startFileSequence(), so risk events
   * appear immediately instead of staying at 0 for 10+ seconds.
   */
  const subscribeToChunks = useCallback(() => {
    if (chunkSubRef.current) {
      chunkSubRef.current.remove();
      chunkSubRef.current = null;
    }
    if (!emitterRef.current) return;

    chunkSubRef.current = emitterRef.current.addListener(
      'onAudioChunk',
      (payload: any) => {
        const base64Data = payload?.data as string;

        // Real PCM RMS from actual WAV data for the waveform animation
        const level = calculatePcmRms(base64Data);
        if (isMountedRef.current) {
          setAudioLevel(level);
        }

        // Track position within segment and across whole session
        const seg = segmentIndexRef.current;
        const chunkInSeg = segmentChunkCountRef.current;
        segmentChunkCountRef.current += 1;
        chunkCountRef.current += 1;

        if (isMountedRef.current) {
          setElapsedChunks(chunkCountRef.current);
        }

        const curve = ALL_SCORE_CURVES[seg];
        if (!curve) return;

        const interpolated = interpolateScore(curve, chunkInSeg);
        applyNarrowFixtureCorrection(seg, interpolated.riskScore, chunkInSeg);

        const riskState = scoreToState(interpolated.riskScore);
        const riskTrend = chunkInSeg < 2 ? 'stable' : (seg === 0 ? 'stable' : 'rising');

        const authData = seg === 0
          ? { score: interpolated.riskScore, spoof_probability: interpolated.riskScore / 100, label: 'GENUINE', acoustic_anomaly: 'NONE', model_version: 'aasist-l-v1.3', is_fixture: true }
          : { score: interpolated.riskScore, spoof_probability: interpolated.riskScore / 100, label: 'SPOOF', acoustic_anomaly: 'HIGH', model_version: 'aasist-l-v1.3', is_fixture: true };

        const identityData = seg === 0
          ? { match_score: null, enrollment_status: 'NOT_ENROLLED', confidence: 0 }
          : seg === 1
          ? { match_score: 38, enrollment_status: 'MISMATCH', confidence: 0.82 }
          : { match_score: 11, enrollment_status: 'MISMATCH', confidence: 0.96 };

        const reasons = seg === 0
          ? ['acoustic_pattern_genuine', 'prosody_natural']
          : seg === 1
          ? ['cloned_voice_high_confidence', 'spectral_artifact_detected', 'speaker_identity_mismatch']
          : ['neural_tts_fingerprint_detected', 'spectral_artifact_critical', 'phase_inconsistency_severe', 'zero_shot_tts_signature'];

        if (chunkInSeg === 0) {
          console.log(`[SIH-LIVE] SEGMENT_START seg=${seg} time=${Date.now()} initial_score=${interpolated.riskScore}`);
        }
        if (chunkInSeg === 0 || chunkInSeg % 8 === 0 || chunkInSeg === (curve[curve.length - 1]?.chunkIndex ?? 0)) {
          console.log(`[SIH-LIVE] PROGRESS seg=${seg} chunk=${chunkInSeg} score=${interpolated.riskScore} decision=${interpolated.decision}`);
        }

        // Monotonically increasing seq for risk_update events
        const seq = chunkCountRef.current;

        applyEvent({
          type: 'risk_update',
          seq,
          event_id: `fixture-risk-${seq}`,
          timestamp: new Date().toISOString(),
          risk_score: interpolated.riskScore,
          risk_state: riskState,
          risk_trend: riskTrend,
          evidence_confidence: interpolated.evidenceConfidence,
          decision: interpolated.decision,
          reasons,
          consequence: seg === 2 ? 'high' : seg === 1 ? 'medium' : 'low',
          pipeline_mode: 'live',
          authenticity: authData,
          identity: identityData,
        });

        // policy_decision on first chunk of each segment and every 8 chunks
        if (chunkInSeg === 0 || chunkInSeg % 8 === 0) {
          const recommendedActions: Record<string, string> = {
            ALLOW: 'No action required. Voice is authentic.',
            VERIFY: 'Pause call. Request secondary channel verification.',
            BLOCK: 'Terminate call immediately. Report incident to security team.',
          };
          applyEvent({
            type: 'policy_decision',
            seq: 0,  // seq=0 → no lastSeq update, never dropped
            event_id: `fixture-policy-${seq}-${chunkInSeg}`,
            timestamp: new Date().toISOString(),
            decision: interpolated.decision,
            reasons,
            recommended_action: recommendedActions[interpolated.decision],
          });
        }
      },
    );
  }, [applyEvent]);

  const start = useCallback(async (): Promise<boolean> => {
    if (Platform.OS !== 'android') {
      return false;
    }

    const nativeModule = NativeModules.VoiceShieldAudioCapture;
    if (!nativeModule) {
      return false;
    }

    try {
      // Set up native event emitter
      if (!emitterRef.current) {
        emitterRef.current = new NativeEventEmitter(nativeModule);
      }

      // Subscribe to segment change events
      segmentSubRef.current = emitterRef.current.addListener(
        'onFileSegmentChange',
        handleSegmentChange,
      );

      // Subscribe to playback complete
      completeSubRef.current = emitterRef.current.addListener(
        'onFilePlaybackComplete',
        handlePlaybackComplete,
      );

      // Reset counters for a fresh session
      chunkCountRef.current = 0;
      segmentIndexRef.current = 0;
      segmentChunkCountRef.current = 0;

      // Subscribe directly to onAudioChunk — bypasses audioCaptureService.isRunning guard
      // This is the fix for the 0-score startup delay.
      subscribeToChunks();

      if (isMountedRef.current) {
        setIsStreaming(true);
        setCurrentSegmentIndex(0);
        setElapsedChunks(0);
      }

      // Start the file sequence — native module handles all WAV streaming
      console.log(`[SIH-LIVE] START_CALLED time=${Date.now()}`);
      await nativeModule.startFileSequence(RECORDING_SEQUENCE);

      return true;
    } catch (e: any) {
      if (isMountedRef.current) {
        setIsStreaming(false);
      }
      return false;
    }
  }, [handleSegmentChange, handlePlaybackComplete, subscribeToChunks]);

  const stop = useCallback(async (): Promise<void> => {
    // Clear transcript timers
    for (const t of transcriptTimersRef.current) clearTimeout(t);
    transcriptTimersRef.current = [];

    // Unsubscribe all native event listeners
    segmentSubRef.current?.remove();
    segmentSubRef.current = null;
    completeSubRef.current?.remove();
    completeSubRef.current = null;
    chunkSubRef.current?.remove();
    chunkSubRef.current = null;

    // Stop native file streaming
    const nativeModule = NativeModules.VoiceShieldAudioCapture;
    if (nativeModule?.stopFileCapture) {
      try {
        await nativeModule.stopFileCapture();
      } catch {}
    }

    if (isMountedRef.current) {
      setIsStreaming(false);
      setAudioLevel(0);
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stop().catch(() => {});
    };
  }, [stop]);

  return {
    isStreaming,
    currentSegmentIndex,
    elapsedChunks,
    audioLevel,
    start,
    stop,
  };
};
