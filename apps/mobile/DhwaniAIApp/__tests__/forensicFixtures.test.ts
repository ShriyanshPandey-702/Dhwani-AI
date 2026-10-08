import {
  getForensicDemoFixture,
  ELEVENLABS_FORENSIC_FIXTURE,
  AI_GENERATED_FORENSIC_FIXTURE,
  REAL_HUMAN_FORENSIC_FIXTURE,
  AMR_CLONED_FORENSIC_FIXTURE,
  normalizeAudioFilename,
} from '../src/utils/recordingFixtures';

describe('Forensic Demo Fixtures Mapping', () => {
  describe('normalizeAudioFilename', () => {
    it('normalizes filenames with directory paths and case', () => {
      expect(normalizeAudioFilename('/sdcard/final audio/Ai_Generated_Voice.wav')).toBe('ai_generated_voice.wav');
      expect(normalizeAudioFilename('Real_Human_Voice.ogg')).toBe('real_human_voice.ogg');
      expect(normalizeAudioFilename('C:\\Users\\audio\\Amr_Cloned_Voice.wav')).toBe('amr_cloned_voice.wav');
    });
  });

  describe('getForensicDemoFixture', () => {
    it('maps ElevenLabs file to 93 CRITICAL BLOCK exactly', () => {
      const filename = 'ElevenLabs_2026-09-19T12_01_32_Max - Elearning and Documentary_pvc_sp100_s50_sb75_se0_b_m2.mp3';
      const fixture = getForensicDemoFixture(filename);
      expect(fixture).toBe(ELEVENLABS_FORENSIC_FIXTURE);
      expect(fixture.risk_score).toBe(93);
      expect(fixture.risk_state).toBe('critical');
      expect(fixture.decision).toBe('BLOCK');
    });

    it('maps Ai_Generated_Voice.wav to 94 CRITICAL BLOCK', () => {
      const fixture = getForensicDemoFixture('Ai_Generated_Voice.wav');
      expect(fixture).toBe(AI_GENERATED_FORENSIC_FIXTURE);
      expect(fixture.risk_score).toBe(94);
      expect(fixture.risk_state).toBe('critical');
      expect(fixture.decision).toBe('BLOCK');
    });

    it('maps Real_Human_Voice.ogg to 14 LOW ALLOW', () => {
      const fixture = getForensicDemoFixture('Real_Human_Voice.ogg');
      expect(fixture).toBe(REAL_HUMAN_FORENSIC_FIXTURE);
      expect(fixture.risk_score).toBe(14);
      expect(fixture.risk_state).toBe('low');
      expect(fixture.decision).toBe('ALLOW');
    });

    it('maps Amr_Cloned_Voice.wav to 76 HIGH VERIFY', () => {
      const fixture = getForensicDemoFixture('Amr_Cloned_Voice.wav');
      expect(fixture).toBe(AMR_CLONED_FORENSIC_FIXTURE);
      expect(fixture.risk_score).toBe(76);
      expect(fixture.risk_state).toBe('high');
      expect(fixture.decision).toBe('VERIFY');
    });

    it('returns null for unknown files so real ML backend is used', () => {
      expect(getForensicDemoFixture('some_random_recording.wav')).toBeNull();
      expect(getForensicDemoFixture('')).toBeNull();
    });
  });
});
