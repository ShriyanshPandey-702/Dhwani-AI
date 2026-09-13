"""
Risk Engine — fuses authenticity, identity, context, consequence and
challenge/verification evidence into a Security Risk Index (0–100) and a
five-state risk level.

Design rules enforced here:
  * Evidence streams stay logically independent until this fusion step.
    A context signal (e.g. "OTP requested") never mutates the authenticity
    score, and a speaker mismatch is never reported as proof of synthesis.
  * Missing or stale evidence is never converted into a verdict. The engine
    reports INSUFFICIENT_EVIDENCE and lets the policy engine decide.
  * Weights and thresholds come from the active policy, so calibration does
    not require code changes.

This engine is REAL (deterministic, tested). The ML detectors that feed it are
currently heuristic stubs — see app/ml/*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ── Risk states ───────────────────────────────────────────────────────────────
INSUFFICIENT = "insufficient_evidence"
LOW = "low"
SUSPICIOUS = "suspicious"
HIGH = "high"
CRITICAL = "critical"

STATE_ORDER = [INSUFFICIENT, LOW, SUSPICIOUS, HIGH, CRITICAL]


@dataclass
class EvidenceBundle:
    """All signals available at a single analysis window."""

    # Authenticity: 0.0 (genuine) → 1.0 (strong synthetic indicators)
    authenticity: Optional[float] = None
    authenticity_confidence: float = 0.0

    # Identity cosine similarity to the enrolled reference: 0.0 → 1.0
    identity_similarity: Optional[float] = None
    identity_confidence: float = 0.0

    # Context risk: 0.0 (benign) → 1.0 (high-consequence request)
    context_risk: Optional[float] = None
    context_confidence: float = 0.0

    # Consequence level of what the caller is asking for
    consequence: str = "low"

    # Interactive evidence: "passed" | "failed" | None
    challenge_outcome: Optional[str] = None
    # "approved" | "rejected" | None
    verification_outcome: Optional[str] = None

    # Set when the stream is unreliable (network loss, no audio, decode failure)
    stale: bool = False

    reasons: List[str] = field(default_factory=list)


@dataclass
class RiskResult:
    score: int
    state: str
    reasons: List[str]
    # 0.0–1.0 — how much of the evidence surface is actually populated
    evidence_confidence: float
    # Per-stream point contribution to the final score (for explainability)
    contributions: Dict[str, float]


_DEFAULT_WEIGHTS = {
    "authenticity": 0.50,
    "identity": 0.25,
    "context": 0.25,
}

_DEFAULT_THRESHOLDS = {
    "low": 20,
    "suspicious": 40,
    "high": 65,
    "critical": 85,
}

_CONSEQUENCE_MULTIPLIER = {
    "low": 1.0,
    "medium": 1.15,
    "high": 1.30,
    "critical": 1.50,
}

# Points added/removed by interactive evidence
_CHALLENGE_DELTA = {"failed": 20.0, "passed": -12.0}
_VERIFICATION_DELTA = {"rejected": 25.0, "approved": -20.0}


def compute_risk(
    evidence: EvidenceBundle,
    policy_config: dict | None = None,
) -> RiskResult:
    """
    Fuse an evidence bundle into a Security Risk Index.

    Returns a RiskResult. Never raises on partial evidence — an absent stream
    simply contributes nothing and lowers `evidence_confidence`.
    """
    cfg = policy_config or {}
    weights = cfg.get("weights", _DEFAULT_WEIGHTS)
    thresholds = cfg.get("thresholds", _DEFAULT_THRESHOLDS)
    multipliers = cfg.get("consequence_multiplier", _CONSEQUENCE_MULTIPLIER)

    reasons: List[str] = []
    contributions: Dict[str, float] = {"authenticity": 0.0, "identity": 0.0, "context": 0.0}

    # ── Stale stream: report insufficient evidence, do not guess ──────────────
    if evidence.stale:
        reasons.append("evidence_stale")
        return RiskResult(0, INSUFFICIENT, reasons, 0.0, contributions)

    available: List[str] = []
    confidences: List[float] = []

    # ── Authenticity stream (independent) ────────────────────────────────────
    if evidence.authenticity is not None:
        auth_raw = _clamp01(evidence.authenticity)
        contributions["authenticity"] = auth_raw * weights.get("authenticity", 0.50) * 100
        available.append("authenticity")
        confidences.append(_clamp01(evidence.authenticity_confidence))
        if auth_raw > 0.70:
            reasons.append("voice_authenticity_anomaly")
        elif auth_raw > 0.40:
            reasons.append("moderate_synthetic_indicators")
    else:
        reasons.append("authenticity_evidence_pending")

    # ── Identity stream (independent) ────────────────────────────────────────
    if evidence.identity_similarity is not None:
        id_risk = _clamp01(1.0 - _clamp01(evidence.identity_similarity))
        contributions["identity"] = id_risk * weights.get("identity", 0.25) * 100
        available.append("identity")
        confidences.append(_clamp01(evidence.identity_confidence))
        if id_risk > 0.50:
            reasons.append("speaker_identity_mismatch")
        elif id_risk > 0.30:
            reasons.append("speaker_identity_inconsistency")
    else:
        reasons.append("no_enrolled_speaker_reference")

    # ── Context stream (independent) ─────────────────────────────────────────
    if evidence.context_risk is not None:
        ctx_raw = _clamp01(evidence.context_risk)
        contributions["context"] = ctx_raw * weights.get("context", 0.25) * 100
        available.append("context")
        confidences.append(_clamp01(evidence.context_confidence))
        if ctx_raw > 0.70:
            reasons.append("high_consequence_request")
        elif ctx_raw > 0.40:
            reasons.append("suspicious_conversation_context")
    else:
        reasons.append("context_evidence_pending")

    # ── No stream at all → insufficient evidence ─────────────────────────────
    if not available:
        return RiskResult(0, INSUFFICIENT, reasons, 0.0, contributions)

    raw = sum(contributions.values())

    # ── Consequence multiplier ───────────────────────────────────────────────
    mult = multipliers.get(evidence.consequence, 1.0)
    if mult > 1.0:
        reasons.append(f"consequence_{evidence.consequence}")
    raw *= mult

    # ── Interactive evidence ─────────────────────────────────────────────────
    if evidence.challenge_outcome in _CHALLENGE_DELTA:
        raw += _CHALLENGE_DELTA[evidence.challenge_outcome]
        reasons.append(f"challenge_{evidence.challenge_outcome}")
    if evidence.verification_outcome in _VERIFICATION_DELTA:
        raw += _VERIFICATION_DELTA[evidence.verification_outcome]
        reasons.append(f"verification_{evidence.verification_outcome}")

    score = int(round(max(0.0, min(100.0, raw))))

    # ── Evidence confidence: coverage × mean per-stream confidence ───────────
    coverage = len(available) / 3.0
    mean_conf = sum(confidences) / len(confidences) if confidences else 0.0
    evidence_confidence = round(coverage * mean_conf, 3)

    state = classify_state(score, thresholds)
    return RiskResult(score, state, reasons, evidence_confidence, contributions)


def classify_state(score: int, thresholds: dict | None = None) -> str:
    """Map a 0–100 score to a risk state using the active thresholds."""
    t = thresholds or _DEFAULT_THRESHOLDS
    if score >= t.get("critical", 85):
        return CRITICAL
    if score >= t.get("high", 65):
        return HIGH
    if score >= t.get("suspicious", 40):
        return SUSPICIOUS
    if score >= t.get("low", 20):
        return LOW
    return INSUFFICIENT


def risk_trend(history: List[int], window: int = 5) -> str:
    """
    Return "rising" | "falling" | "stable" from the tail of a score history.
    Used for the dashboard's trend arrow.
    """
    tail = [h for h in history if h is not None][-window:]
    if len(tail) < 2:
        return "stable"
    delta = tail[-1] - tail[0]
    if delta >= 5:
        return "rising"
    if delta <= -5:
        return "falling"
    return "stable"


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))
