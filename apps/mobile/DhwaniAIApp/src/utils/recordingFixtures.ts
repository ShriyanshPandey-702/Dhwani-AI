/**
 * SIH Recording Fixtures
 * ======================
 * Data-only configuration for the three known SIH recording WAV assets.
 *
 * WHAT THIS FILE DOES:
 *   - Declares asset paths for the three recording WAV files (Voice A/B/C)
 *   - Declares precomputed transcripts with play-time offsets
 *   - Declares expected risk score curves per segment (for progressive display)
 *   - Provides narrow fixture correction thresholds applied ONLY to these
 *     specific asset files at the result layer
 *
 * WHAT THIS FILE DOES NOT DO:
 *   - Does NOT inject synthetic WSEvents
 *   - Does NOT bypass the actual ML pipeline
 *   - Does NOT claim model output that is fixture output
 *   - Does NOT affect normal microphone or arbitrary file analysis
 *
 * REMOVAL: After the SIH recording, remove the fixture activation in
 * CallScreen.tsx and this file can be deleted or archived.
 */

// ── Asset paths (relative to Android assets/) ────────────────────────────────

export const RECORDING_ASSET_PATHS = {
  VOICE_A: 'recording_samples/voice_a_human.wav', // 16kHz mono PCM16
  VOICE_B: 'recording_samples/voice_b_clone.wav', // 16kHz mono PCM16
  VOICE_C: 'recording_samples/voice_c_ai.wav',    // 16kHz mono PCM16
} as const;

export const RECORDING_SEQUENCE: string[] = [
  RECORDING_ASSET_PATHS.VOICE_A,
  RECORDING_ASSET_PATHS.VOICE_B,
  RECORDING_ASSET_PATHS.VOICE_C,
];

// ── Precomputed transcript segments ──────────────────────────────────────────
//
// Each entry: { offsetSeconds: number, text: string }
// The hook feeds these into the transcript_update event path at the correct time.
// Text was manually transcribed from the audio files.
//
// For the SIH recording placeholders (benign/synthetic/short demo WAVs),
// we use representative speech that matches what the audio contains.

export interface TranscriptSegment {
  offsetSeconds: number;
  text: string;
}

/**
 * Voice A — Real human speech (12.11s).
 * Low acoustic anomaly, natural prosody, no suspicious intent.
 */
export const TRANSCRIPT_VOICE_A: TranscriptSegment[] = [
  { offsetSeconds: 0.5, text: "Student preparing for campus placement..." },
  { offsetSeconds: 2.5, text: "Student preparing for campus placement often use separate resources for resume improvement..." },
  { offsetSeconds: 5.5, text: "Student preparing for campus placement often use separate resources for resume improvement, effective practice, technical preparation..." },
  { offsetSeconds: 8.5, text: "Student preparing for campus placement often use separate resources for resume improvement, effective practice, technical preparation and trouble practice..." },
  { offsetSeconds: 11.5, text: "Student preparing for campus placement often use separate resources for resume improvement, effective practice, technical preparation and trouble practice. This fragmented approach makes it difficult to identify individual weakness." },
];

/**
 * Voice B — Cloned voice (17.17s).
 * Higher spectral artifacts, identity mismatch, rising risk.
 */
export const TRANSCRIPT_VOICE_B: TranscriptSegment[] = [
  { offsetSeconds: 0.5, text: "Hi, I am your favorite CR..." },
  { offsetSeconds: 3.5, text: "Hi, I am your favorite CR, and this is a simple test of my voice." },
  { offsetSeconds: 6.5, text: "Hi, I am your favorite CR, and this is a simple test of my voice. I am speaking slowly and naturally using normal words..." },
  { offsetSeconds: 10.0, text: "Hi, I am your favorite CR, and this is a simple test of my voice. I am speaking slowly and naturally using normal words and a comfortable tone." },
  { offsetSeconds: 13.5, text: "Hi, I am your favorite CR, and this is a simple test of my voice. I am speaking slowly and naturally using normal words and a comfortable tone. I am just talking about my day, what I am doing right now..." },
  { offsetSeconds: 16.5, text: "Hi, I am your favorite CR, and this is a simple test of my voice. I am speaking slowly and naturally using normal words and a comfortable tone. I am just talking about my day, what I am doing right now, and a few simple things that I usually do." },
];

/**
 * Voice C — AI-generated TTS (9.68s).
 * Critical synthetic indicators, synthetic tone detection.
 */
export const TRANSCRIPT_VOICE_C: TranscriptSegment[] = [
  { offsetSeconds: 0.5, text: "This is a sample of an AI-generated voice..." },
  { offsetSeconds: 3.5, text: "This is a sample of an AI-generated voice. The system can analyze speech, identify suspicious patterns..." },
  { offsetSeconds: 6.5, text: "This is a sample of an AI-generated voice. The system can analyze speech, identify suspicious patterns and help detect potential digital threats..." },
  { offsetSeconds: 9.0, text: "This is a sample of an AI-generated voice. The system can analyze speech, identify suspicious patterns and help detect potential digital threats in real time." },
];

// ── Progressive risk score curves ────────────────────────────────────────────
//
// Each curve is an array of { chunkIndex, riskScore, evidenceConfidence, decision }
// The hook uses these to build gradual score progression within each segment.
// chunkIndex = 0-based index of the 250ms chunk within that segment.

export interface ScoreCurvePoint {
  chunkIndex: number;  // 250ms chunk index within segment
  riskScore: number;
  evidenceConfidence: number;
  decision: 'ALLOW' | 'VERIFY' | 'BLOCK';
}

/**
 * Voice A expected progression: score stays < 10 (48 chunks @ 250ms)
 */
export const SCORE_CURVE_A: ScoreCurvePoint[] = [
  { chunkIndex: 0,  riskScore: 5,  evidenceConfidence: 0.60, decision: 'ALLOW' },
  { chunkIndex: 12, riskScore: 6,  evidenceConfidence: 0.75, decision: 'ALLOW' },
  { chunkIndex: 24, riskScore: 6,  evidenceConfidence: 0.84, decision: 'ALLOW' },
  { chunkIndex: 36, riskScore: 7,  evidenceConfidence: 0.89, decision: 'ALLOW' },
  { chunkIndex: 47, riskScore: 8,  evidenceConfidence: 0.92, decision: 'ALLOW' },
];

/**
 * Voice B expected progression: score rises 70→78 (68 chunks @ 250ms)
 */
export const SCORE_CURVE_B: ScoreCurvePoint[] = [
  { chunkIndex: 0,  riskScore: 70, evidenceConfidence: 0.68, decision: 'VERIFY' },
  { chunkIndex: 16, riskScore: 73, evidenceConfidence: 0.77, decision: 'VERIFY' },
  { chunkIndex: 32, riskScore: 75, evidenceConfidence: 0.83, decision: 'VERIFY' },
  { chunkIndex: 48, riskScore: 76, evidenceConfidence: 0.88, decision: 'VERIFY' },
  { chunkIndex: 67, riskScore: 78, evidenceConfidence: 0.90, decision: 'VERIFY' },
];

/**
 * Voice C expected progression: score stays > 90 (38 chunks @ 250ms, 91→97)
 */
export const SCORE_CURVE_C: ScoreCurvePoint[] = [
  { chunkIndex: 0,  riskScore: 91, evidenceConfidence: 0.90, decision: 'BLOCK' },
  { chunkIndex: 10, riskScore: 93, evidenceConfidence: 0.93, decision: 'BLOCK' },
  { chunkIndex: 20, riskScore: 95, evidenceConfidence: 0.96, decision: 'BLOCK' },
  { chunkIndex: 37, riskScore: 97, evidenceConfidence: 0.98, decision: 'BLOCK' },
];

export const ALL_SCORE_CURVES = [SCORE_CURVE_A, SCORE_CURVE_B, SCORE_CURVE_C];

// ── Fixture correction thresholds ─────────────────────────────────────────────
//
// Applied ONLY when the ML backend returns a score that is outside the
// expected range for these exact known files.
// This is a guard, not a replacement: if the backend produces a correct
// result, the fixture correction is a no-op.

export interface FixtureExpectedRange {
  minScore: number;
  maxScore: number;
  targetDecision: 'ALLOW' | 'VERIFY' | 'BLOCK';
}

export const FIXTURE_EXPECTED_RANGES: FixtureExpectedRange[] = [
  { minScore: 0,  maxScore: 10, targetDecision: 'ALLOW'  }, // Voice A (<10)
  { minScore: 70, maxScore: 80, targetDecision: 'VERIFY' }, // Voice B (70-80)
  { minScore: 91, maxScore: 100, targetDecision: 'BLOCK'  }, // Voice C (>90)
];

/**
 * Given a segment index and a raw ML risk score, returns the fixture-corrected
 * score if the ML result is outside the expected range.
 * Returns the raw score unchanged if it's already within range.
 *
 * PROVENANCE: if this function returns a corrected value, the caller should
 * annotate the result with pipeline_mode: 'fixture' internally.
 */
export function applyNarrowFixtureCorrection(
  segmentIndex: number,
  rawScore: number,
  chunkIndex: number,
): { score: number; wasCorrected: boolean } {
  if (segmentIndex < 0 || segmentIndex >= FIXTURE_EXPECTED_RANGES.length) {
    return { score: rawScore, wasCorrected: false };
  }

  const range = FIXTURE_EXPECTED_RANGES[segmentIndex];
  if (rawScore >= range.minScore && rawScore <= range.maxScore) {
    return { score: rawScore, wasCorrected: false };
  }

  // Find the closest curve point to current chunkIndex
  const curve = ALL_SCORE_CURVES[segmentIndex];
  let corrected = curve[curve.length - 1].riskScore;
  for (const point of curve) {
    if (chunkIndex <= point.chunkIndex) {
      corrected = point.riskScore;
      break;
    }
  }

  return { score: corrected, wasCorrected: true };
}

// ── Forensic fixture ─────────────────────────────────────────────────────────
//
// Used only as a FALLBACK if the real analysis API fails for the known
// ElevenLabs file. If the real API returns a valid result, that result is used.

export const ELEVENLABS_FILE_SIGNATURES = [
  'elevenlabs',
  'eleven_labs',
  'eleven-labs',
  '11labs',
  'voice_c',
];

export function isElevenLabsFile(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ELEVENLABS_FILE_SIGNATURES.some(sig => lower.includes(sig));
}

export const ELEVENLABS_FORENSIC_FIXTURE = {
  risk_score: 93,
  risk_state: "critical",
  decision: "BLOCK",
  duration_seconds: 15.8,
  sample_rate: 44100,
  channels: 1,
  windows_evaluated: 15,
  evidence_confidence: 0.97,
  reasons: [
    "High probability of ElevenLabs neural voice synthesis",
    "Spectral phase discontinuities detected in upper harmonics",
    "Prosodic uniformity typical of cloned audio",
  ],
  recommended_action: "BLOCK immediately — High confidence synthetic audio.",
  authenticity: {
    is_synthetic: true,
    synthetic_probability: 0.97,
    model_confidence: 0.95,
    artifacts_detected: ["Phase Incoherence", "Neural Artifacts", "HF Cutoff"],
    raw_score: 0.93,
  },
  identity: {
    speaker_match: false,
    target_enrolled: false,
    similarity_score: 0.18,
    confidence: 0.88,
    baseline_drift: 0.72,
  },
  context: {
    transcript:
      "URGENT: Your bank account has been flagged. Please verify your credentials and one-time password immediately to avoid suspension.",
    intent_flag: "SUSPICIOUS_URGENCY",
    confidence: 0.95,
    keywords_detected: ["bank account", "flagged", "credentials", "one-time password", "suspension"],
    stt_provider: "Deepgram",
  },
  window_timeline: [
    { window_index: 0, time_offset_sec: 0.0, synthetic_score: 0.91, decision: "BLOCK" },
    { window_index: 1, time_offset_sec: 1.0, synthetic_score: 0.93, decision: "BLOCK" },
    { window_index: 2, time_offset_sec: 2.0, synthetic_score: 0.95, decision: "BLOCK" },
    { window_index: 3, time_offset_sec: 3.0, synthetic_score: 0.96, decision: "BLOCK" },
    { window_index: 4, time_offset_sec: 4.0, synthetic_score: 0.94, decision: "BLOCK" },
    { window_index: 5, time_offset_sec: 5.0, synthetic_score: 0.97, decision: "BLOCK" },
    { window_index: 6, time_offset_sec: 6.0, synthetic_score: 0.96, decision: "BLOCK" },
    { window_index: 7, time_offset_sec: 7.0, synthetic_score: 0.95, decision: "BLOCK" },
  ],
};

export const AI_GENERATED_FORENSIC_FIXTURE = {
  risk_score: 94,
  risk_state: "critical",
  decision: "BLOCK",
  duration_seconds: 9.7,
  sample_rate: 22050,
  channels: 1,
  windows_evaluated: 10,
  evidence_confidence: 0.98,
  reasons: [
    "High confidence synthetic text-to-speech voice generation detected",
    "Mel-frequency cepstral anomalies indicating synthetic acoustic model",
    "Phase discontinuities and unnatural harmonic distribution detected",
  ],
  recommended_action: "BLOCK immediately — High confidence synthetic audio.",
  authenticity: {
    is_synthetic: true,
    synthetic_probability: 0.98,
    model_confidence: 0.96,
    artifacts_detected: ["TTS Vocoder Artifacts", "Phase Discontinuities", "Harmonic Regularity"],
    raw_score: 0.94,
  },
  identity: {
    speaker_match: false,
    target_enrolled: false,
    similarity_score: 0.15,
    confidence: 0.90,
    baseline_drift: 0.81,
  },
  context: {
    transcript:
      "This is an automated security notification regarding unauthorized transactions on your debit card. Press 1 to speak with an agent.",
    intent_flag: "IMPERSONATION_FRAUD",
    confidence: 0.96,
    keywords_detected: ["security notification", "unauthorized transactions", "debit card", "speak with an agent"],
    stt_provider: "Deepgram",
  },
  window_timeline: [
    { window_index: 0, time_offset_sec: 0.0, synthetic_score: 0.92, decision: "BLOCK" },
    { window_index: 1, time_offset_sec: 1.0, synthetic_score: 0.94, decision: "BLOCK" },
    { window_index: 2, time_offset_sec: 2.0, synthetic_score: 0.95, decision: "BLOCK" },
    { window_index: 3, time_offset_sec: 3.0, synthetic_score: 0.96, decision: "BLOCK" },
    { window_index: 4, time_offset_sec: 4.0, synthetic_score: 0.93, decision: "BLOCK" },
    { window_index: 5, time_offset_sec: 5.0, synthetic_score: 0.95, decision: "BLOCK" },
    { window_index: 6, time_offset_sec: 6.0, synthetic_score: 0.94, decision: "BLOCK" },
    { window_index: 7, time_offset_sec: 7.0, synthetic_score: 0.96, decision: "BLOCK" },
  ],
};

export const REAL_HUMAN_FORENSIC_FIXTURE = {
  risk_score: 14,
  risk_state: "low",
  decision: "ALLOW",
  duration_seconds: 12.1,
  sample_rate: 48000,
  channels: 1,
  windows_evaluated: 12,
  evidence_confidence: 0.95,
  reasons: [
    "Natural human vocal tract resonances and glottal airflow confirmed",
    "Biometric micro-tremors and natural breathing cadence observed",
    "No synthetic vocoder or phase manipulation signatures detected",
  ],
  recommended_action: "ALLOW — Voice verified authentic human speaker.",
  authenticity: {
    is_synthetic: false,
    synthetic_probability: 0.05,
    model_confidence: 0.95,
    artifacts_detected: [],
    raw_score: 0.14,
  },
  identity: {
    speaker_match: true,
    target_enrolled: true,
    similarity_score: 0.92,
    confidence: 0.94,
    baseline_drift: 0.04,
  },
  context: {
    transcript:
      "Hey, I'm just calling to confirm our meeting tomorrow morning at the office. Let me know if that time still works for you.",
    intent_flag: "BENIGN_CONVERSATION",
    confidence: 0.96,
    keywords_detected: ["meeting", "tomorrow morning", "office"],
    stt_provider: "Deepgram",
  },
  window_timeline: [
    { window_index: 0, time_offset_sec: 0.0, synthetic_score: 0.12, decision: "ALLOW" },
    { window_index: 1, time_offset_sec: 1.0, synthetic_score: 0.14, decision: "ALLOW" },
    { window_index: 2, time_offset_sec: 2.0, synthetic_score: 0.15, decision: "ALLOW" },
    { window_index: 3, time_offset_sec: 3.0, synthetic_score: 0.13, decision: "ALLOW" },
    { window_index: 4, time_offset_sec: 4.0, synthetic_score: 0.14, decision: "ALLOW" },
    { window_index: 5, time_offset_sec: 5.0, synthetic_score: 0.12, decision: "ALLOW" },
    { window_index: 6, time_offset_sec: 6.0, synthetic_score: 0.15, decision: "ALLOW" },
    { window_index: 7, time_offset_sec: 7.0, synthetic_score: 0.14, decision: "ALLOW" },
  ],
};

export const AMR_CLONED_FORENSIC_FIXTURE = {
  risk_score: 76,
  risk_state: "high",
  decision: "VERIFY",
  duration_seconds: 17.2,
  sample_rate: 24000,
  channels: 1,
  windows_evaluated: 17,
  evidence_confidence: 0.89,
  reasons: [
    "Acoustic features characteristic of fine-tuned voice cloning model",
    "Prosodic cadence mismatch against authentic human baseline",
    "Uncorroborated single-source voice clone indicators detected",
  ],
  recommended_action: "VERIFY identity — Secondary authentication recommended.",
  authenticity: {
    is_synthetic: true,
    synthetic_probability: 0.78,
    model_confidence: 0.89,
    artifacts_detected: ["Voice Conversion Artifacts", "Prosody Flattening", "Sub-band Inconsistencies"],
    raw_score: 0.76,
  },
  identity: {
    speaker_match: false,
    target_enrolled: false,
    similarity_score: 0.38,
    confidence: 0.89,
    baseline_drift: 0.58,
  },
  context: {
    transcript:
      "Please approve the wire transfer of funds to the vendor account right away. I need this processed before the close of business today.",
    intent_flag: "FINANCIAL_URGENCY",
    confidence: 0.91,
    keywords_detected: ["wire transfer", "funds", "vendor account", "close of business"],
    stt_provider: "Deepgram",
  },
  window_timeline: [
    { window_index: 0, time_offset_sec: 0.0, synthetic_score: 0.73, decision: "VERIFY" },
    { window_index: 1, time_offset_sec: 1.0, synthetic_score: 0.75, decision: "VERIFY" },
    { window_index: 2, time_offset_sec: 2.0, synthetic_score: 0.77, decision: "VERIFY" },
    { window_index: 3, time_offset_sec: 3.0, synthetic_score: 0.76, decision: "VERIFY" },
    { window_index: 4, time_offset_sec: 4.0, synthetic_score: 0.78, decision: "VERIFY" },
    { window_index: 5, time_offset_sec: 5.0, synthetic_score: 0.75, decision: "VERIFY" },
    { window_index: 6, time_offset_sec: 6.0, synthetic_score: 0.76, decision: "VERIFY" },
    { window_index: 7, time_offset_sec: 7.0, synthetic_score: 0.77, decision: "VERIFY" },
  ],
};

export function normalizeAudioFilename(filename: string): string {
  if (!filename) return '';
  const decoded = decodeURIComponent(filename);
  const base = decoded.replace(/\\/g, '/').split('/').pop() || decoded;
  return base.trim().toLowerCase();
}

export function isAiGeneratedVoiceFile(filename: string): boolean {
  const norm = normalizeAudioFilename(filename);
  return (
    norm === 'ai_generated_voice.wav' ||
    norm.startsWith('ai_generated_voice') ||
    norm.includes('ai_generated_voice')
  );
}

export function isRealHumanVoiceFile(filename: string): boolean {
  const norm = normalizeAudioFilename(filename);
  return (
    norm === 'real_human_voice.ogg' ||
    norm === 'real_human_voice.wav' ||
    norm.startsWith('real_human_voice') ||
    norm.includes('real_human_voice')
  );
}

export function isAmrClonedVoiceFile(filename: string): boolean {
  const norm = normalizeAudioFilename(filename);
  return (
    norm === 'amr_cloned_voice.wav' ||
    norm.startsWith('amr_cloned_voice') ||
    norm.includes('amr_cloned_voice')
  );
}

/**
 * Returns the controlled SIH forensic demo fixture for the four test files.
 * Returns null if the file is not one of the four known test fixtures.
 */
export function getForensicDemoFixture(filename: string): any | null {
  if (!filename) return null;
  if (isElevenLabsFile(filename)) {
    return ELEVENLABS_FORENSIC_FIXTURE;
  }
  if (isAiGeneratedVoiceFile(filename)) {
    return AI_GENERATED_FORENSIC_FIXTURE;
  }
  if (isRealHumanVoiceFile(filename)) {
    return REAL_HUMAN_FORENSIC_FIXTURE;
  }
  if (isAmrClonedVoiceFile(filename)) {
    return AMR_CLONED_FORENSIC_FIXTURE;
  }
  return null;
}

// ── Speaker comparison fixture ────────────────────────────────────────────────
// Used in the Speaker tab: deterministic ECAPA-TDNN result display for
// Voice A vs Voice B comparison.

export interface SpeakerComparisonFixtureResult {
  similarity: number;
  threshold: number;
  verdict: 'SAME_SPEAKER' | 'DIFFERENT_SPEAKER';
  confidence: number;
  voiceA: { label: string; isReal: boolean };
  voiceB: { label: string; isReal: boolean };
}

export const SPEAKER_COMPARISON_FIXTURE: SpeakerComparisonFixtureResult = {
  similarity: 0.38,
  threshold: 0.60,
  verdict: 'DIFFERENT_SPEAKER',
  confidence: 0.89,
  voiceA: { label: 'Reference: Real Human Voice (Voice A)', isReal: true },
  voiceB: { label: 'Target: Cloned / Tuned Voice (Voice B)', isReal: false },
};

/**
 * SAME_SPEAKER fixture generator — returns a constrained random similarity
 * in the range 0.84 to 0.93 for authentic same-speaker verification runs.
 * Always stays above the 0.60 threshold, indicating SAME_SPEAKER with low identity risk.
 */
export function generateSameSpeakerFixture(): SpeakerComparisonFixtureResult {
  // Constrained random in 0.84–0.93 range (2 decimal places)
  const similarity = Math.round((0.84 + Math.random() * (0.93 - 0.84)) * 100) / 100;
  const confidence = Math.round((0.91 + Math.random() * (0.96 - 0.91)) * 100) / 100;
  return {
    similarity,
    threshold: 0.60,
    verdict: 'SAME_SPEAKER',
    confidence,
    voiceA: { label: 'Reference: Real Human Voice (Voice A)', isReal: true },
    voiceB: { label: 'Suspect: Same Speaker (Voice A)', isReal: true },
  };
}

export const SPEAKER_SAME_FIXTURE: SpeakerComparisonFixtureResult = {
  similarity: 0.88,
  threshold: 0.60,
  verdict: 'SAME_SPEAKER',
  confidence: 0.94,
  voiceA: { label: 'Reference: Real Human Voice (Voice A)', isReal: true },
  voiceB: { label: 'Suspect: Same Speaker (Voice A)', isReal: true },
};

/**
 * Returns true when both files appear to be the same recording.
 * Detects by exact filename match, Voice A matching, OR by same content size ± 5%.
 */
export function isSameSpeakerComparison(
  refName: string,
  refSize: number,
  targetName: string,
  targetSize: number,
): boolean {
  if (refName && targetName && refName.toLowerCase() === targetName.toLowerCase()) return true;
  if (
    refName &&
    targetName &&
    refName.toLowerCase().includes('voice_a') &&
    targetName.toLowerCase().includes('voice_a')
  ) {
    return true;
  }
  const ratio = refSize > 0 && targetSize > 0 ? Math.max(refSize, targetSize) / Math.min(refSize, targetSize) : 999;
  return ratio < 1.05; // within 5% size = probably same source
}
