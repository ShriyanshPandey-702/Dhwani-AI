import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import { Text } from 'react-native';
import { ConsequencesPanel } from '../src/components/ConsequencesPanel';
import {
  ELEVENLABS_FORENSIC_FIXTURE,
  AMR_CLONED_FORENSIC_FIXTURE,
  REAL_HUMAN_FORENSIC_FIXTURE,
} from '../src/utils/recordingFixtures';

const textOf = (tree: ReactTestRenderer.ReactTestRenderer): string =>
  tree.root
    .findAllByType(Text)
    .flatMap(node =>
      React.Children.toArray(node.props.children).filter(
        (c): c is string | number => typeof c === 'string' || typeof c === 'number',
      ),
    )
    .join(' | ');

describe('Consequences & Threats Panel in Forensic Analysis', () => {
  let mounted: ReactTestRenderer.ReactTestRenderer[] = [];

  const render = (element: React.ReactElement) => {
    let tree!: ReactTestRenderer.ReactTestRenderer;
    ReactTestRenderer.act(() => {
      tree = ReactTestRenderer.create(element);
    });
    mounted.push(tree);
    return tree;
  };

  afterEach(() => {
    ReactTestRenderer.act(() => {
      while (mounted.length) {
        mounted.pop()!.unmount();
      }
    });
  });

  describe('TEST 1: ElevenLabs audio with score 93', () => {
    it('shows CRITICAL threat level, HIGH transaction consequence, 93 / 100 score, and active threat signals', () => {
      const fixture = ELEVENLABS_FORENSIC_FIXTURE;
      const tree = render(
        <ConsequencesPanel
          context={fixture.context as any}
          score={fixture.risk_score}
          riskState={fixture.risk_state}
          authenticity={fixture.authenticity}
          identity={fixture.identity}
          reasons={fixture.reasons}
        />,
      );
      const text = textOf(tree);

      // Verify Context Threat Score
      expect(text).toContain('93 / 100');
      expect(text).not.toContain('undefined / 100');

      // Verify Threat Level
      expect(text).toContain('Threat Level');
      expect(text).toContain('CRITICAL');

      // Verify Transaction Consequence
      expect(text).toContain('Transaction Consequence');
      expect(text).toContain('HIGH');

      // Verify Active Threat Signals
      expect(text).not.toContain('None Detected');
      expect(text).toContain('Synthetic / AI-Generated Voice');
      expect(text).toContain('Voice Cloning Indicators');
      expect(text).toContain('Authenticity Anomaly');
      expect(text).toContain('Speaker Mismatch');
    });
  });

  describe('TEST 2: Second audio with score 73', () => {
    it('shows HIGH threat level, HIGH transaction consequence, 73 / 100 score, and active threat signals', () => {
      const secondAudioReport = {
        risk_score: 73,
        risk_state: 'high',
        authenticity: {
          is_synthetic: true,
          synthetic_probability: 0.73,
          raw_score: 0.73,
          artifacts_detected: ['Voice Conversion Artifacts', 'Sub-band Inconsistencies'],
        },
        identity: {
          speaker_match: false,
          similarity_score: 0.38,
        },
        reasons: ['Acoustic features characteristic of fine-tuned voice cloning model'],
        context: {
          transcript: 'Please approve the wire transfer of funds right away.',
          intent_flag: 'FINANCIAL_URGENCY',
          confidence: 0.91,
        },
      };

      const tree = render(
        <ConsequencesPanel
          context={secondAudioReport.context as any}
          score={secondAudioReport.risk_score}
          riskState={secondAudioReport.risk_state}
          authenticity={secondAudioReport.authenticity}
          identity={secondAudioReport.identity}
          reasons={secondAudioReport.reasons}
        />,
      );
      const text = textOf(tree);

      // Verify Context Threat Score
      expect(text).toContain('73 / 100');
      expect(text).not.toContain('undefined / 100');

      // Verify Threat Level
      expect(text).toContain('Threat Level');
      expect(text).toContain('HIGH');

      // Verify Transaction Consequence
      expect(text).toContain('Transaction Consequence');
      expect(text).toContain('HIGH');

      // Verify Active Threat Signals
      expect(text).not.toContain('None Detected');
      expect(text).toContain('Synthetic / AI-Generated Voice');
      expect(text).toContain('Voice Cloning Indicators');
      expect(text).toContain('Authenticity Anomaly');
      expect(text).toContain('Speaker Mismatch');
    });
  });

  describe('TEST 3: Lower-score forensic audio (Real Human Voice)', () => {
    it('decreases consequence accordingly (LOW / LOW, 14 / 100, None Detected)', () => {
      const fixture = REAL_HUMAN_FORENSIC_FIXTURE;
      const tree = render(
        <ConsequencesPanel
          context={fixture.context as any}
          score={fixture.risk_score}
          riskState={fixture.risk_state}
          authenticity={fixture.authenticity}
          identity={fixture.identity}
          reasons={fixture.reasons}
        />,
      );
      const text = textOf(tree);

      expect(text).toContain('14 / 100');
      expect(text).not.toContain('undefined / 100');
      expect(text).toContain('Threat Level');
      expect(text).toContain('LOW');
      expect(text).toContain('Transaction Consequence');
      expect(text).toContain('None Detected');
    });
  });

  describe('TEST 4: Score-driven mapping tiers (30–59 → MEDIUM)', () => {
    it('maps score 45 to MEDIUM threat level and MEDIUM consequence', () => {
      const tree = render(
        <ConsequencesPanel
          context={{ transcript: 'Testing audio sample' } as any}
          score={45}
        />,
      );
      const text = textOf(tree);

      expect(text).toContain('45 / 100');
      expect(text).toContain('MEDIUM');
    });
  });

  describe('TEST 5: Dynamic switching from 93-score audio to 73-score audio', () => {
    it('updates dynamically without retaining stale values from previous analysis', () => {
      let tree!: ReactTestRenderer.ReactTestRenderer;

      // 1. First analyze 93-score audio
      ReactTestRenderer.act(() => {
        tree = ReactTestRenderer.create(
          <ConsequencesPanel
            context={ELEVENLABS_FORENSIC_FIXTURE.context as any}
            score={93}
            riskState="critical"
            authenticity={ELEVENLABS_FORENSIC_FIXTURE.authenticity}
            identity={ELEVENLABS_FORENSIC_FIXTURE.identity}
            reasons={ELEVENLABS_FORENSIC_FIXTURE.reasons}
          />,
        );
      });
      mounted.push(tree);

      let text = textOf(tree);
      expect(text).toContain('93 / 100');
      expect(text).toContain('CRITICAL');

      // 2. Switch to 73-score audio
      ReactTestRenderer.act(() => {
        tree.update(
          <ConsequencesPanel
            context={{ transcript: 'Second audio transcript', intent_flag: 'FINANCIAL_URGENCY' } as any}
            score={73}
            riskState="high"
            authenticity={{ is_synthetic: true, raw_score: 0.73, artifacts_detected: ['Voice Conversion'] }}
            identity={{ speaker_match: false, similarity_score: 0.38 }}
            reasons={['Voice cloning']}
          />,
        );
      });

      text = textOf(tree);
      // Confirmed updated to 73 / HIGH
      expect(text).toContain('73 / 100');
      expect(text).toContain('HIGH');
      // Confirmed 93 and CRITICAL are no longer present
      expect(text).not.toContain('93 / 100');
      expect(text).not.toContain('CRITICAL');
    });
  });

  describe('TEST 6: Backward compatibility when no score or transcript is present', () => {
    it('displays Insufficient Evidence when awaiting transcribed speech in live call', () => {
      const tree = render(<ConsequencesPanel context={null} />);
      const text = textOf(tree);

      expect(text).toContain('Insufficient Evidence');
      expect(text).toContain('Consequence analysis requires transcribed speech');
    });
  });
});
