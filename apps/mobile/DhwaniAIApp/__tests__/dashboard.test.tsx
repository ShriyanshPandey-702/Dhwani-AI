/**
 * Dashboard rendering — the Zustand → UI half of the real-time data flow.
 *
 * Each panel is rendered from the same evidence shapes the backend emits, and
 * asserted on its visible text.
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import { Text } from 'react-native';

import { AuthenticityPanel } from '../src/components/AuthenticityPanel';
import { IdentityPanel } from '../src/components/IdentityPanel';
import { ContextPanel } from '../src/components/ContextPanel';
import { EventTimeline } from '../src/components/EventTimeline';
import { DecisionPanel } from '../src/components/DecisionPanel';
import { RiskGauge } from '../src/components/RiskGauge';
import { RiskSparkline } from '../src/components/RiskSparkline';
import { PipelineModeBanner } from '../src/components/PipelineModeBanner';
import { StatCard } from '../src/components/StatCard';
import {
  AuthenticityEvidence, ContextEvidence, IdentityEvidence,
  RiskObservation, TimelineEntry,
} from '../src/types';

/** Flatten every string rendered inside a tree. */
const textOf = (tree: ReactTestRenderer.ReactTestRenderer): string =>
  tree.root
    .findAllByType(Text)
    .flatMap(node =>
      React.Children.toArray(node.props.children).filter(
        (c): c is string | number => typeof c === 'string' || typeof c === 'number',
      ),
    )
    .join(' | ');

// Trees are unmounted after every test so effect cleanups run — the risk
// gauge's pulse animation would otherwise keep timers alive and hang the suite.
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

const AUTHENTICITY: AuthenticityEvidence = {
  score: 68, spoof_probability: 0.68, confidence: 0.91,
  acoustic_anomaly: 'HIGH', spectral_anomaly: 'MEDIUM', prosody_anomaly: 'HIGH',
  model_version: 'heuristic-dsp-stub-v0.2', is_mock: true,
};

const IDENTITY: IdentityEvidence = {
  match_score: 82, confidence: 0.87, consistency: 'GOOD',
  enrollment_status: 'VERIFIED', model_version: 'ecapa-stub-v0.2', is_mock: true,
};

const CONTEXT: ContextEvidence = {
  score: 81, confidence: 0.89, urgency: true, financial_request: true,
  otp_request: true, credential_request: false,
  sensitive_information_request: false, social_engineering: true,
  authority_claim: true, consequence: 'critical',
  transcript: 'Please read me the OTP.', detected_phrases: ['otp'],
  model_version: 'rules-v0.2', is_mock: false, transcript_is_mock: true,
};

// ── Risk gauge ────────────────────────────────────────────────────────────────

describe('RiskGauge', () => {
  it('renders the score, state and trend', () => {
    const text = textOf(
      render(<RiskGauge score={74} state="high" trend="rising" />),
    );
    expect(text).toContain('74');
    expect(text).toContain('HIGH');
    expect(text).toContain('Risk increasing');
  });

  it('renders an insufficient-evidence state without claiming safety', () => {
    const text = textOf(
      render(<RiskGauge score={0} state="insufficient_evidence" trend="stable" />),
    );
    expect(text).toContain('INSUFFICIENT EVIDENCE');
    expect(text).not.toContain('SAFE');
  });
});

// ── Live risk graph ───────────────────────────────────────────────────────────

describe('RiskSparkline', () => {
  it('shows an empty state rather than a fabricated curve', () => {
    const text = textOf(render(<RiskSparkline history={[]} />));
    expect(text).toContain('awaiting data');
    expect(text).toContain('Waiting for the first risk observation');
  });

  it('plots one bar per observation and labels the latest', () => {
    const history: RiskObservation[] = [
      { score: 21, state: 'low', at: 1 },
      { score: 44, state: 'suspicious', at: 2 },
      { score: 74, state: 'high', at: 3 },
    ];
    const text = textOf(render(<RiskSparkline history={history} />));
    expect(text).toContain('3 obs');
    expect(text).toContain('now · 74');
  });

  it('only draws the most recent window of observations', () => {
    const history: RiskObservation[] = Array.from({ length: 90 }, (_, i) => ({
      score: i, state: 'low' as const, at: i,
    }));
    const text = textOf(render(<RiskSparkline history={history} window={60} />));
    expect(text).toContain('60 obs');
  });
});

// ── Evidence panels ───────────────────────────────────────────────────────────

describe('AuthenticityPanel', () => {
  it('renders every authenticity metric the spec requires', () => {
    const text = textOf(render(<AuthenticityPanel authenticity={AUTHENTICITY} />));
    expect(text).toContain('68');
    expect(text).toContain('68%');
    expect(text).toContain('Acoustic Anomaly');
    expect(text).toContain('Spectral Anomaly');
    expect(text).toContain('Prosody / Temporal Anomaly');
    expect(text).toContain('HIGH');
    expect(text).toContain('MEDIUM');
  });

  it('labels the stub so mock scores are not read as AI detection', () => {
    const text = textOf(render(<AuthenticityPanel authenticity={AUTHENTICITY} />));
    expect(text).toContain('not a trained deepfake model');
  });

  it('names the real model, and does not call it a stub, under real ML', () => {
    const text = textOf(
      render(
        <AuthenticityPanel
          authenticity={{
            ...AUTHENTICITY,
            is_mock: false,
            model_name: 'AASIST',
            model_version: 'AASIST-L+cascade@asvspoof2019la',
            pipeline_mode: 'real_ml',
          }}
        />,
      ),
    );
    expect(text).toContain('AASIST');
    expect(text).toContain('not evaluated on this channel');
    expect(text).not.toContain('not a trained deepfake model');
  });

  it('still marks a heuristic fallback as a stub, never as real ML', () => {
    const text = textOf(
      render(
        <AuthenticityPanel
          authenticity={{
            ...AUTHENTICITY,
            is_mock: true,
            model_name: 'heuristic-dsp',
            pipeline_mode: 'heuristic_fallback',
          }}
        />,
      ),
    );
    expect(text).toContain('not a trained deepfake model');
    expect(text).not.toContain('AASIST');
  });

  it('shows a pending state before any audio is analysed', () => {
    const text = textOf(render(<AuthenticityPanel authenticity={null} />));
    expect(text).toContain('Awaiting sufficient audio');
  });

  it('does not render conversation-context signals', () => {
    const text = textOf(render(<AuthenticityPanel authenticity={AUTHENTICITY} />));
    expect(text).not.toContain('OTP');
    expect(text).not.toContain('Financial');
  });
});

describe('IdentityPanel', () => {
  it('renders match score, confidence, consistency and enrollment', () => {
    const text = textOf(render(<IdentityPanel identity={IDENTITY} />));
    expect(text).toContain('82%');
    expect(text).toContain('87%');
    expect(text).toContain('GOOD');
    expect(text).toContain('VERIFIED');
  });

  it('reports a missing enrolment rather than assuming a match', () => {
    const text = textOf(
      render(<IdentityPanel identity={{ ...IDENTITY, enrollment_status: 'NOT_ENROLLED' }} />),
    );
    expect(text).toContain('NOT ENROLLED');
    expect(text).toContain('no reference');
  });

  it('does not imply a mismatch means synthetic speech', () => {
    const text = textOf(
      render(<IdentityPanel identity={{ ...IDENTITY, match_score: 20, enrollment_status: 'MISMATCH' }} />),
    );
    expect(text).toContain('MISMATCH');
    expect(text).not.toContain('synthetic');
  });
});

describe('ContextPanel', () => {
  it('renders every contextual signal the spec requires', () => {
    const text = textOf(render(<ContextPanel context={CONTEXT} />));
    expect(text).toContain('Urgency');
    expect(text).toContain('Financial Request');
    expect(text).toContain('OTP Request');
    expect(text).toContain('Credential Request');
    expect(text).toContain('Sensitive Information');
    expect(text).toContain('Social Engineering');
    expect(text).toContain('Transaction Consequence');
    expect(text).toContain('DETECTED');
    expect(text).toContain('CRITICAL');
  });

  it('shows NO for signals that were not detected', () => {
    const text = textOf(render(<ContextPanel context={CONTEXT} />));
    expect(text).toContain('NO');
  });

  it('labels a scripted transcript as a stub', () => {
    const text = textOf(render(<ContextPanel context={CONTEXT} />));
    expect(text).toContain('not real speech recognition');
    expect(text).toContain('rules-v0.2');
  });

  it('names the real STT model when the transcript is genuine', () => {
    const text = textOf(
      render(
        <ContextPanel
          context={{
            ...CONTEXT,
            transcript_is_mock: false,
            transcript_model: 'faster-whisper',
            transcript_language: 'en',
          }}
        />,
      ),
    );
    expect(text).toContain('faster-whisper');
    expect(text).toContain('en');
    expect(text).not.toContain('not real speech recognition');
  });
});

// ── Timeline ──────────────────────────────────────────────────────────────────

describe('EventTimeline', () => {
  it('renders an empty state with no events', () => {
    const text = textOf(render(<EventTimeline events={[]} />));
    expect(text).toContain('No security events detected yet');
  });

  it('renders event labels with their stream', () => {
    const events: TimelineEntry[] = [
      { id: '1', label: 'OTP request detected', stream: 'context', severity: 'critical', at: Date.now() },
      { id: '2', label: 'Voice anomaly detected', stream: 'authenticity', severity: 'warning', at: Date.now() },
    ];
    const text = textOf(render(<EventTimeline events={events} />));
    expect(text).toContain('OTP request detected');
    expect(text).toContain('Voice anomaly detected');
    expect(text).toContain('CONTEXT');
    expect(text).toContain('VOICE');
    expect(text).toContain('2 total');
  });
});

// ── Decision ──────────────────────────────────────────────────────────────────

describe('DecisionPanel', () => {
  it('renders the verification decision with human-readable reasons', () => {
    const text = textOf(
      render(
        <DecisionPanel
          decision="VERIFY"
          reasons={['voice_authenticity_anomaly', 'high_consequence_request']}
          recommendedAction="Independent verification"
          evidenceConfidence={0.73}
        />,
      ),
    );
    expect(text).toContain('VERIFICATION REQUIRED');
    expect(text).toContain('Voice authenticity anomaly');
    expect(text).toContain('High-consequence request detected');
    expect(text).toContain('Independent verification');
    // The percentage is interpolated, so it arrives as separate text nodes.
    expect(text).toMatch(/Evidence sufficiency\s*\|?\s*73\s*\|?\s*%/);
  });

  it('renders a hold decision', () => {
    const text = textOf(
      render(
        <DecisionPanel decision="HOLD" reasons={[]} recommendedAction="Hold" evidenceConfidence={0.5} />,
      ),
    );
    expect(text).toContain('ACTION HELD');
  });

  it('renders an allow decision without alarm language', () => {
    const text = textOf(
      render(
        <DecisionPanel decision="ALLOW" reasons={[]} recommendedAction="" evidenceConfidence={0.9} />,
      ),
    );
    expect(text).toContain('NO ACTION REQUIRED');
  });

  it('falls back gracefully on an unrecognised decision', () => {
    const text = textOf(
      render(
        <DecisionPanel
          decision={'WOBBLE' as never}
          reasons={[]}
          recommendedAction=""
          evidenceConfidence={0}
        />,
      ),
    );
    expect(text).toContain('NO ACTION REQUIRED');
  });
});

// ── Mock labelling ────────────────────────────────────────────────────────────

describe('PipelineModeBanner', () => {
  it('states plainly when the dashboard is driven by mock audio', () => {
    const text = textOf(render(<PipelineModeBanner mode="mock" />));
    expect(text).toContain('DEMO');
    expect(text).toContain('Not AI detection results');
  });

  it('states when audio is live', () => {
    const text = textOf(render(<PipelineModeBanner mode="live" />));
    expect(text).toContain('LIVE AUDIO');
  });
});

// ── Home overview tiles ───────────────────────────────────────────────────────

describe('StatCard', () => {
  it('renders a value and label', () => {
    const text = textOf(render(<StatCard value={12} label="Calls" />));
    expect(text).toContain('12');
    expect(text).toContain('Calls');
  });

  it('renders independent alerts and holds values without duplication', () => {
    // Canonical data: 4 incidents (1 ALLOW, 1 VERIFY, 1 HOLD, 1 BLOCK)
    // Alerts = 3 (VERIFY, HOLD, BLOCK)
    // Holds = 1 (HOLD)
    const alertsCard = textOf(render(<StatCard value={3} label="Alerts" />));
    const holdsCard = textOf(render(<StatCard value={1} label="Holds" />));

    expect(alertsCard).toContain('3');
    expect(alertsCard).toContain('Alerts');
    expect(holdsCard).toContain('1');
    expect(holdsCard).toContain('Holds');
    expect(alertsCard).not.toEqual(holdsCard);
  });
});
