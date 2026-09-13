"""
Streaming score stability.

Uses the EXISTING `StreamWindower` from the production pipeline — this harness
measures the deployed behaviour, it does not substitute its own windowing.

What is measured per stream:
  * score variance and jitter (mean absolute change between adjacent windows)
  * detection delay: seconds from a transition to a sustained correct decision
  * windows-to-decision under each aggregation strategy
  * false alerts caused by a single anomalous window

Aggregation strategies compared (none is adopted unless it measurably helps):
  raw          the per-window score, unchanged
  ema          exponential moving average
  median_k     rolling median over k windows
  confirm_n    require n consecutive windows past the threshold before flipping
  hysteresis   separate raise/clear thresholds
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(REPO_ROOT), str(API_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

SR = 16000


# ── Aggregators ──────────────────────────────────────────────────────────────

def agg_raw(scores: Sequence[float]) -> List[float]:
    return list(scores)


def agg_ema(scores: Sequence[float], alpha: float = 0.4) -> List[float]:
    out, state = [], None
    for s in scores:
        state = s if state is None else alpha * s + (1 - alpha) * state
        out.append(state)
    return out


def agg_median(scores: Sequence[float], k: int = 3) -> List[float]:
    out = []
    for i in range(len(scores)):
        window = scores[max(0, i - k + 1): i + 1]
        out.append(float(np.median(window)))
    return out


def decisions_confirm(scores: Sequence[float], threshold: float, n: int = 2) -> List[int]:
    """Flip state only after `n` consecutive windows agree — suppresses blips."""
    out, state, run, last = [], 0, 0, None
    for s in scores:
        proposed = int(s >= threshold)
        run = run + 1 if proposed == last else 1
        last = proposed
        if run >= n:
            state = proposed
        out.append(state)
    return out


def decisions_hysteresis(scores: Sequence[float], raise_at: float, clear_at: float
                         ) -> List[int]:
    """Raise on `raise_at`, clear only below `clear_at` (clear_at < raise_at)."""
    out, state = [], 0
    for s in scores:
        if state == 0 and s >= raise_at:
            state = 1
        elif state == 1 and s < clear_at:
            state = 0
        out.append(state)
    return out


# ── Stream construction ──────────────────────────────────────────────────────

def concat_with_transition(a: np.ndarray, b: np.ndarray, sr: int = SR) -> np.ndarray:
    """Splice two clips to create a bona-fide ↔ spoof transition."""
    return np.concatenate([np.asarray(a, np.float32), np.asarray(b, np.float32)])


def frames_of(audio: np.ndarray, frame_ms: int = 1000, sr: int = SR) -> List[np.ndarray]:
    n = int(sr * frame_ms / 1000)
    return [audio[i:i + n] for i in range(0, max(0, len(audio) - n + 1), n)]


@dataclass
class StreamResult:
    name: str
    scores: List[float] = field(default_factory=list)
    window_index: List[int] = field(default_factory=list)
    frames_pushed: int = 0
    windows_scored: int = 0
    skipped_no_window: int = 0
    skipped_no_evidence: int = 0

    def stats(self) -> Dict:
        s = np.asarray(self.scores, dtype=float)
        if s.size == 0:
            return {"n": 0}
        jitter = float(np.mean(np.abs(np.diff(s)))) if s.size > 1 else 0.0
        return {
            "n": int(s.size),
            "mean": float(np.mean(s)),
            "std": float(np.std(s)),
            "variance": float(np.var(s)),
            "min": float(np.min(s)),
            "max": float(np.max(s)),
            "range": float(np.max(s) - np.min(s)),
            "jitter_mean_abs_delta": jitter,
            "frames_pushed": self.frames_pushed,
            "windows_scored": self.windows_scored,
            "skipped_no_window": self.skipped_no_window,
            "skipped_no_evidence": self.skipped_no_evidence,
        }


def run_stream(audio: np.ndarray, detector, windower, session: str,
               name: str = "stream", frame_ms: int = 1000) -> StreamResult:
    """
    Push `audio` through the production windower one frame at a time and score
    each emitted window with the real model.
    """
    import torch

    from app.ml.preprocessing.audio import MIN_SPEECH_ENERGY

    windower.reset(session)
    result = StreamResult(name=name)

    for frame in frames_of(audio, frame_ms):
        result.frames_pushed += 1
        window = windower.push(session, frame)
        if window is None:
            result.skipped_no_window += 1
            continue
        if float(np.mean(window.astype(np.float64) ** 2)) < MIN_SPEECH_ENERGY:
            result.skipped_no_evidence += 1
            continue
        x = torch.from_numpy(detector._fit_length(window)).unsqueeze(0).to(detector._device)
        with torch.no_grad():
            _, logits = detector._models[detector.variant](x)
            p_bonafide = torch.softmax(logits, dim=1)[0, 1].item()
        result.scores.append(float(1.0 - p_bonafide))
        result.window_index.append(result.frames_pushed)
        result.windows_scored += 1

    windower.reset(session)
    return result


def detection_delay(scores: Sequence[float], decisions: Sequence[int],
                    transition_window: int, hop_ms: int = 1000) -> Optional[float]:
    """
    Seconds from `transition_window` to the first *sustained* positive decision
    (positive and staying positive to the end). None if never sustained.
    """
    for i in range(transition_window, len(decisions)):
        if decisions[i] == 1 and all(d == 1 for d in decisions[i:]):
            return (i - transition_window) * hop_ms / 1000.0
    return None


def count_isolated_flips(decisions: Sequence[int]) -> int:
    """Single-window state changes that immediately revert — spurious alerts."""
    flips = 0
    for i in range(1, len(decisions) - 1):
        if decisions[i] != decisions[i - 1] and decisions[i] != decisions[i + 1]:
            flips += 1
    return flips


def compare_aggregators(scores: Sequence[float], threshold: float) -> Dict:
    """Stability vs responsiveness for each strategy on one score series."""
    variants = {
        "raw": agg_raw(scores),
        "ema_0.4": agg_ema(scores, 0.4),
        "median_3": agg_median(scores, 3),
        "median_5": agg_median(scores, 5),
    }
    out: Dict[str, Dict] = {}
    for name, series in variants.items():
        arr = np.asarray(series, dtype=float)
        decisions = [int(v >= threshold) for v in series]
        out[name] = {
            "std": float(np.std(arr)),
            "jitter": float(np.mean(np.abs(np.diff(arr)))) if arr.size > 1 else 0.0,
            "isolated_flips": count_isolated_flips(decisions),
        }
    for name, decisions in {
        "confirm_2": decisions_confirm(scores, threshold, 2),
        "confirm_3": decisions_confirm(scores, threshold, 3),
        "hysteresis": decisions_hysteresis(scores, threshold, max(0.0, threshold - 0.15)),
    }.items():
        out[name] = {
            "std": float(np.std(np.asarray(scores, dtype=float))),
            "jitter": None,
            "isolated_flips": count_isolated_flips(decisions),
        }
    return out
