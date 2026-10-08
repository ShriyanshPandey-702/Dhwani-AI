import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import { AuthenticityPanel } from '../src/components/AuthenticityPanel';
import { IdentityPanel } from '../src/components/IdentityPanel';
import {
  ELEVENLABS_FORENSIC_FIXTURE,
  AMR_CLONED_FORENSIC_FIXTURE,
  REAL_HUMAN_FORENSIC_FIXTURE,
  SPEAKER_COMPARISON_FIXTURE,
} from '../src/utils/recordingFixtures';

// Helper to extract all rendered text content from ReactTestRenderer
const textOf = (tree: ReactTestRenderer.ReactTestRenderer): string =>
  tree.root
    .findAll(node => typeof node.props.children === 'string' || Array.isArray(node.props.children))
    .flatMap(node =>
      React.Children.toArray(node.props.children).filter(
        (c): c is string | number => typeof c === 'string' || typeof c === 'number',
      ),
    )
    .join(' | ');

const mounted: ReactTestRenderer.ReactTestRenderer[] = [];

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

describe('Forensic Voice Authenticity & Speaker Identity Tests', () => {
  // ── TEST A: ElevenLabs Audio (Case 1) ───────────────────────────────────────
  it('TEST A: ElevenLabs (93 / CRITICAL) displays elevated authenticity and high anomaly bands', () => {
    const fixture = ELEVENLABS_FORENSIC_FIXTURE;

    const authText = textOf(
      render(
        <AuthenticityPanel
          authenticity={fixture.authenticity as any}
          reasons={fixture.reasons}
          score={fixture.risk_score}
        />,
      ),
    );

    // AASIST-L must show elevated result, not "Insufficient speech"
    expect(authText).not.toContain('Insufficient speech');
    expect(authText).toContain('AASIST-L (Local)');
    expect(authText).toContain('97%');

    // Acoustic, Spectral, Prosody must all be HIGH
    expect(authText).toContain('Acoustic');
    expect(authText).toContain('Spectral');
    expect(authText).toContain('Prosody');
    expect(authText).toContain('HIGH');
    expect(authText).not.toContain('LOW');

    // Speaker Identity without reference must truthfully report NOT ENROLLED / UNAVAILABLE
    const idText = textOf(
      render(
        <IdentityPanel
          identity={fixture.identity as any}
          hasReference={false}
        />,
      ),
    );

    expect(idText).toContain('NOT ENROLLED');
    expect(idText).toContain('UNAVAILABLE');
    expect(idText).toContain('no reference');
    expect(idText).not.toContain('SAME SPEAKER');
  });

  // ── TEST B: Second Audio / AMR Cloned (Case 2) ──────────────────────────────
  it('TEST B: Second Audio (76/73 / HIGH) displays elevated authenticity and high anomaly bands', () => {
    const fixture = AMR_CLONED_FORENSIC_FIXTURE;

    const authText = textOf(
      render(
        <AuthenticityPanel
          authenticity={fixture.authenticity as any}
          reasons={fixture.reasons}
          score={fixture.risk_score}
        />,
      ),
    );

    // AASIST-L must show elevated result, not "Insufficient speech"
    expect(authText).not.toContain('Insufficient speech');
    expect(authText).toContain('AASIST-L (Local)');
    expect(authText).toContain('78%');

    // Acoustic, Spectral, Prosody must be HIGH
    expect(authText).toContain('Acoustic');
    expect(authText).toContain('Spectral');
    expect(authText).toContain('Prosody');
    expect(authText).toContain('HIGH');
    expect(authText).not.toContain('LOW');

    // Speaker Identity without reference must truthfully report NOT ENROLLED / UNAVAILABLE
    const idText = textOf(
      render(
        <IdentityPanel
          identity={fixture.identity as any}
          hasReference={false}
        />,
      ),
    );

    expect(idText).toContain('NOT ENROLLED');
    expect(idText).toContain('UNAVAILABLE');
    expect(idText).toContain('no reference');
  });

  // ── TEST C: Real Human Audio (Low-Risk Case) ────────────────────────────────
  it('TEST C: Real Human (14 / LOW) displays low-risk authentic presentation and LOW anomaly bands', () => {
    const fixture = REAL_HUMAN_FORENSIC_FIXTURE;

    const authText = textOf(
      render(
        <AuthenticityPanel
          authenticity={fixture.authenticity as any}
          reasons={fixture.reasons}
          score={fixture.risk_score}
        />,
      ),
    );

    expect(authText).not.toContain('Insufficient speech');
    expect(authText).toContain('AASIST-L (Local)');
    expect(authText).toContain('5%');

    // Acoustic, Spectral, Prosody must be LOW
    expect(authText).toContain('Acoustic');
    expect(authText).toContain('Spectral');
    expect(authText).toContain('Prosody');
    expect(authText).toContain('LOW');
    expect(authText).not.toContain('HIGH');
  });

  // ── TEST D: Speaker Identity evidence-driven with and without reference ──────
  it('TEST D: Speaker Identity does NOT fabricate data when no reference, and shows real data when reference exists', () => {
    // 1. Without reference: truthful state
    const noRefText = textOf(
      render(
        <IdentityPanel
          identity={ELEVENLABS_FORENSIC_FIXTURE.identity as any}
          hasReference={false}
        />,
      ),
    );
    expect(noRefText).toContain('NOT ENROLLED');
    expect(noRefText).toContain('UNAVAILABLE');
    expect(noRefText).toContain('no reference');

    // 2. With reference and ECAPA comparison data: honest comparison results
    const withRefText = textOf(
      render(
        <IdentityPanel
          identity={ELEVENLABS_FORENSIC_FIXTURE.identity as any}
          comparison={SPEAKER_COMPARISON_FIXTURE}
          hasReference={true}
        />,
      ),
    );
    expect(withRefText).not.toContain('UNAVAILABLE');
    expect(withRefText).toContain('38%'); // similarity
    expect(withRefText).toContain('60%'); // threshold
    expect(withRefText).toContain('89%'); // confidence
    expect(withRefText).toContain('MISMATCH');
  });

  // ── TEST E: Dynamic Switching (93 -> 76 -> 14 -> 93) ────────────────────────
  it('TEST E: Dynamic switching updates values without retaining stale data', () => {
    // 1. ElevenLabs (93)
    let auth = render(
      <AuthenticityPanel
        authenticity={ELEVENLABS_FORENSIC_FIXTURE.authenticity as any}
        reasons={ELEVENLABS_FORENSIC_FIXTURE.reasons}
        score={ELEVENLABS_FORENSIC_FIXTURE.risk_score}
      />,
    );
    let text = textOf(auth);
    expect(text).toContain('97%');
    expect(text).toContain('HIGH');
    expect(text).not.toContain('LOW');

    // 2. Second Audio (76)
    auth = render(
      <AuthenticityPanel
        authenticity={AMR_CLONED_FORENSIC_FIXTURE.authenticity as any}
        reasons={AMR_CLONED_FORENSIC_FIXTURE.reasons}
        score={AMR_CLONED_FORENSIC_FIXTURE.risk_score}
      />,
    );
    text = textOf(auth);
    expect(text).toContain('78%');
    expect(text).toContain('HIGH');
    expect(text).not.toContain('LOW');

    // 3. Human Audio (14)
    auth = render(
      <AuthenticityPanel
        authenticity={REAL_HUMAN_FORENSIC_FIXTURE.authenticity as any}
        reasons={REAL_HUMAN_FORENSIC_FIXTURE.reasons}
        score={REAL_HUMAN_FORENSIC_FIXTURE.risk_score}
      />,
    );
    text = textOf(auth);
    expect(text).toContain('5%');
    expect(text).toContain('LOW');
    expect(text).not.toContain('HIGH');

    // 4. Return to ElevenLabs (93)
    auth = render(
      <AuthenticityPanel
        authenticity={ELEVENLABS_FORENSIC_FIXTURE.authenticity as any}
        reasons={ELEVENLABS_FORENSIC_FIXTURE.reasons}
        score={ELEVENLABS_FORENSIC_FIXTURE.risk_score}
      />,
    );
    text = textOf(auth);
    expect(text).toContain('97%');
    expect(text).toContain('HIGH');
    expect(text).not.toContain('LOW');
  });

  // ── Genuine Insufficient Speech ────────────────────────────────────────────
  it('displays "Insufficient speech" when speech is genuinely insufficient', () => {
    const text = textOf(
      render(
        <AuthenticityPanel
          authenticity={{
            score: 0,
            spoof_probability: null as any,
            confidence: 0,
            acoustic_anomaly: 'LOW',
            spectral_anomaly: 'LOW',
            prosody_anomaly: 'LOW',
            model_version: 'AASIST-L',
            is_mock: false,
          }}
          reasons={['audio_duration_less_than_window_size']}
        />,
      ),
    );
    expect(text).toContain('Insufficient speech');
  });
});
