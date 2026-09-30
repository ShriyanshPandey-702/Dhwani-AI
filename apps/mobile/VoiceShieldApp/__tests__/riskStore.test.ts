/**
 * Live dashboard store — event handling, edge cases and reset semantics.
 *
 * These are the WebSocket → Zustand half of the real-time data flow. They run
 * without a socket by feeding events straight into `applyEvent`.
 */

import { MAX_HISTORY, useRiskStore } from '../src/store/riskStore';
import {
  alertEvent, audioQuality, challengeResult, challengeStarted, detectedEvent,
  policyDecision, resetEventCounters, riskUpdate, sessionStarted,
  verificationRequested, verificationResult,
} from './helpers/events';

const apply = (event: unknown) => useRiskStore.getState().applyEvent(event);
const state = () => useRiskStore.getState();

beforeEach(() => {
  useRiskStore.getState().reset();
  resetEventCounters();
});

// ── Risk gauge, state and graph ───────────────────────────────────────────────

describe('risk updates', () => {
  it('updates score, state and trend from a risk_update', () => {
    apply(riskUpdate({ risk_score: 74, risk_state: 'high', risk_trend: 'rising' }));

    expect(state().riskScore).toBe(74);
    expect(state().riskState).toBe('high');
    expect(state().riskTrend).toBe('rising');
    expect(state().lastUpdated).not.toBeNull();
  });

  it('appends one graph observation per risk_update', () => {
    apply(riskUpdate({ risk_score: 20 }));
    apply(riskUpdate({ risk_score: 45 }));
    apply(riskUpdate({ risk_score: 71 }));

    expect(state().riskHistory.map(p => p.score)).toEqual([20, 45, 71]);
  });

  it('bounds the graph history', () => {
    for (let i = 0; i < MAX_HISTORY + 40; i += 1) {
      apply(riskUpdate({ risk_score: i % 100 }));
    }
    expect(state().riskHistory).toHaveLength(MAX_HISTORY);
  });

  it('records the risk state alongside each observation', () => {
    apply(riskUpdate({ risk_score: 90, risk_state: 'critical' }));
    expect(state().riskHistory[0].state).toBe('critical');
  });

  it('carries the evidence confidence through', () => {
    apply(riskUpdate({ evidence_confidence: 0.73 }));
    expect(state().evidenceConfidence).toBeCloseTo(0.73);
  });
});

// ── Independent evidence streams ──────────────────────────────────────────────

describe('evidence streams', () => {
  it('updates authenticity, identity and context independently', () => {
    apply(riskUpdate());

    expect(state().authenticity?.spoof_probability).toBeCloseTo(0.4);
    expect(state().identity?.match_score).toBe(82);
    expect(state().context?.urgency).toBe(true);
  });

  it('does not wipe a stream that an update omits', () => {
    apply(riskUpdate());
    const identityBefore = state().identity;

    apply(riskUpdate({ identity: null, risk_score: 60 }));

    expect(state().identity).toEqual(identityBefore);
    expect(state().riskScore).toBe(60);
  });

  it('keeps context signals out of the authenticity object', () => {
    apply(riskUpdate({
      context: { ...riskUpdate().context!, otp_request: true },
    }));

    expect(state().context?.otp_request).toBe(true);
    expect(state().authenticity).not.toHaveProperty('otp_request');
  });

  it('records audio quality and activity separately from risk', () => {
    apply(audioQuality());
    expect(state().audioQuality?.quality).toBe('GOOD');
    expect(state().audioActive).toBe(true);
    expect(state().riskScore).toBe(0);
  });
});

// ── Timeline and alerts ───────────────────────────────────────────────────────

describe('timeline and alerts', () => {
  it('prepends detected events so the newest is first', () => {
    apply(detectedEvent({ label: 'Voice anomaly detected' }));
    apply(detectedEvent({ label: 'Financial request detected' }));

    expect(state().detectedEvents.map(e => e.label)).toEqual([
      'Financial request detected',
      'Voice anomaly detected',
    ]);
  });

  it('records alerts and allows dismissing one', () => {
    apply(alertEvent({ message: 'Elevated risk' }));
    expect(state().alerts).toHaveLength(1);

    useRiskStore.getState().dismissAlert(state().alerts[0].id);
    expect(state().alerts).toHaveLength(0);
  });

  it('keeps the alert severity and recommendation', () => {
    apply(alertEvent({ severity: 'critical', recommended_action: 'Hold' }));
    expect(state().alerts[0].severity).toBe('critical');
    expect(state().alerts[0].recommendedAction).toBe('Hold');
  });
});

// ── Security decision ─────────────────────────────────────────────────────────

describe('security decision', () => {
  it('updates the decision from a risk_update', () => {
    apply(riskUpdate({ decision: 'VERIFY', reasons: ['high_consequence_request'] }));
    expect(state().decision).toBe('VERIFY');
    expect(state().decisionReasons).toEqual(['high_consequence_request']);
  });

  it('updates the decision and recommendation from a policy_decision', () => {
    apply(policyDecision());
    expect(state().decision).toBe('HOLD');
    expect(state().recommendedAction).toContain('Hold');
  });

  it('walks ALLOW → VERIFY → HOLD as events arrive', () => {
    const seen: string[] = [];
    apply(riskUpdate({ decision: 'ALLOW', risk_score: 10 }));
    seen.push(state().decision);
    apply(riskUpdate({ decision: 'VERIFY', risk_score: 70 }));
    seen.push(state().decision);
    apply(riskUpdate({ decision: 'HOLD', risk_score: 92 }));
    seen.push(state().decision);

    expect(seen).toEqual(['ALLOW', 'VERIFY', 'HOLD']);
  });
});

// ── Challenge and verification ────────────────────────────────────────────────

describe('challenge and verification', () => {
  it('tracks the challenge lifecycle', () => {
    apply(challengeStarted());
    expect(state().challengeState).toBe('started');
    expect(state().challengeText).toContain('full name');

    apply(challengeResult({ outcome: 'failed' }));
    expect(state().challengeState).toBe('failed');
  });

  it('tracks a passed challenge', () => {
    apply(challengeStarted());
    apply(challengeResult({ outcome: 'passed' }));
    expect(state().challengeState).toBe('passed');
  });

  it('tracks the verification lifecycle', () => {
    apply(verificationRequested());
    expect(state().verificationState).toBe('requested');
    expect(state().verificationMethod).toBe('trusted_device');

    apply(verificationResult({ outcome: 'approved' }));
    expect(state().verificationState).toBe('approved');
  });

  it('tracks a rejected verification', () => {
    apply(verificationRequested());
    apply(verificationResult({ outcome: 'rejected' }));
    expect(state().verificationState).toBe('rejected');
  });
});

// ── Session lifecycle ─────────────────────────────────────────────────────────

describe('session lifecycle', () => {
  it('records the pipeline mode so mock data is labelled', () => {
    apply(sessionStarted({ pipeline_mode: 'mock' }));
    expect(state().pipelineMode).toBe('mock');
    expect(state().sessionStatus).toBe('monitoring');
  });

  it('marks live audio when the backend reports it', () => {
    apply(sessionStarted({ pipeline_mode: 'live' }));
    expect(state().pipelineMode).toBe('live');
  });

  it('captures the incident id when the session ends', () => {
    apply(sessionStarted());
    apply({
      type: 'session_ended', event_id: 'e-end', seq: 99,
      session_id: 'sess-test', timestamp: new Date().toISOString(),
      reason: 'disconnected', peak_risk_score: 93,
      peak_risk_state: 'critical', incident_id: 'inc-1',
    });

    expect(state().sessionStatus).toBe('ended');
    expect(state().incidentId).toBe('inc-1');
  });
});

// ── Edge cases the spec calls out ─────────────────────────────────────────────

describe('edge cases', () => {
  it('drops duplicate events', () => {
    const event = riskUpdate({ risk_score: 50 });
    apply(event);
    apply(event);

    expect(state().riskHistory).toHaveLength(1);
  });

  it('drops out-of-order (stale) events', () => {
    apply(riskUpdate({ seq: 10, risk_score: 80, event_id: 'a' }));
    apply(riskUpdate({ seq: 4, risk_score: 5, event_id: 'b' }));

    expect(state().riskScore).toBe(80);
    expect(state().riskHistory).toHaveLength(1);
  });

  it('accepts a sequence restart after a reconnect', () => {
    apply(riskUpdate({ seq: 40, risk_score: 70, event_id: 'a' }));
    apply(riskUpdate({ seq: 1, risk_score: 12, event_id: 'b' }));

    expect(state().riskScore).toBe(12);
  });

  it('ignores malformed events without throwing', () => {
    const bad: unknown[] = [
      null, undefined, 42, 'risk_update', [], {}, { type: 123 },
      { type: 'risk_update' },
    ];

    expect(() => bad.forEach(apply)).not.toThrow();
    expect(state().riskScore).toBe(0);
  });

  it('survives a risk_update with missing fields', () => {
    expect(() =>
      apply({
        type: 'risk_update', event_id: 'partial', seq: 1,
        session_id: 'sess-test', timestamp: 'not-a-date',
      }),
    ).not.toThrow();

    expect(state().riskHistory).toHaveLength(1);
    expect(Number.isFinite(state().riskHistory[0].at)).toBe(true);
  });

  it('ignores unknown event types', () => {
    apply({
      type: 'quantum_flux', event_id: 'x', seq: 1,
      session_id: 'sess-test', timestamp: new Date().toISOString(),
    });

    expect(state().riskScore).toBe(0);
    expect(state().detectedEvents).toHaveLength(0);
  });

  it('ignores pong frames', () => {
    expect(() => apply({ type: 'pong', timestamp: 1 })).not.toThrow();
    expect(state().lastUpdated).toBeNull();
  });

  it('records a backend error without clearing the dashboard', () => {
    apply(riskUpdate({ risk_score: 66 }));
    apply({
      type: 'error', event_id: 'err', seq: 50,
      session_id: 'sess-test', timestamp: new Date().toISOString(),
      detail: 'Analysis failed for one window', code: 'analysis_error',
    });

    expect(state().lastError).toBe('Analysis failed for one window');
    expect(state().riskScore).toBe(66);
  });

  it('bounds the de-duplication buffer', () => {
    for (let i = 0; i < 500; i += 1) {
      apply(detectedEvent({ event_id: `dedupe-${i}` }));
    }
    expect(state().seenEventIds.length).toBeLessThanOrEqual(400);
  });
});

// ── Reset between calls ───────────────────────────────────────────────────────

describe('reset', () => {
  it('clears the whole dashboard between calls', () => {
    apply(sessionStarted());
    apply(riskUpdate({ risk_score: 88, risk_state: 'critical' }));
    apply(detectedEvent());
    apply(alertEvent());
    apply(challengeStarted());
    apply(verificationRequested());

    useRiskStore.getState().reset();

    const s = state();
    expect(s.riskScore).toBe(0);
    expect(s.riskState).toBe('insufficient_evidence');
    expect(s.riskHistory).toHaveLength(0);
    expect(s.detectedEvents).toHaveLength(0);
    expect(s.alerts).toHaveLength(0);
    expect(s.authenticity).toBeNull();
    expect(s.identity).toBeNull();
    expect(s.context).toBeNull();
    expect(s.challengeState).toBe('idle');
    expect(s.verificationState).toBe('idle');
    expect(s.decision).toBe('ALLOW');
    expect(s.lastSeq).toBe(0);
    expect(s.seenEventIds).toHaveLength(0);
  });

  it('accepts the same event ids again after a reset', () => {
    apply(riskUpdate({ event_id: 'reused', seq: 1, risk_score: 30 }));
    useRiskStore.getState().reset();
    apply(riskUpdate({ event_id: 'reused', seq: 1, risk_score: 30 }));

    expect(state().riskHistory).toHaveLength(1);
  });

  it('updates live transcript from transcript_update event', () => {
    apply({
      type: 'transcript_update',
      event_id: 'tr-1',
      seq: 1,
      session_id: 's-1',
      timestamp: new Date().toISOString(),
      transcript: 'Hello, I am calling from your bank',
      is_final: false,
    });

    expect(state().context?.transcript).toBe('Hello, I am calling from your bank');
  });
});
