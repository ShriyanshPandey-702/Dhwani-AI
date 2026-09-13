"""
Score calibration.

An AASIST softmax output is a decision score, not a probability. A sample
scoring 0.9 does not mean "90% likely to be spoof". Calibration learns a
monotonic map from raw score to a probability that means what it says.

RULES ENFORCED HERE:
  * A calibrator is FIT on a calibration split and never on the test split.
  * The raw score is always retained. Calibration adds a field; it never
    overwrites the model output.
  * Both methods are monotonic, so ranking metrics (ROC-AUC, EER) are unchanged
    by calibration. Only the probability scale, Brier score and ECE move.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

CALIBRATION_VERSION = "cal-v1"


# ── Calibration quality metrics ──────────────────────────────────────────────

def brier_score(labels, probabilities) -> float:
    """Mean squared error of the probability against the outcome. Lower is better."""
    y = np.asarray(labels, dtype=float).ravel()
    p = np.asarray(probabilities, dtype=float).ravel()
    return float(np.mean((p - y) ** 2))


def expected_calibration_error(labels, probabilities, n_bins: int = 15) -> float:
    """
    ECE with equal-width bins: the average gap between predicted confidence and
    observed frequency, weighted by bin population.
    """
    y = np.asarray(labels, dtype=float).ravel()
    p = np.asarray(probabilities, dtype=float).ravel()
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p > lo) & (p <= hi) if lo > 0 else (p >= lo) & (p <= hi)
        if not np.any(mask):
            continue
        total += (np.sum(mask) / y.size) * abs(float(np.mean(y[mask])) - float(np.mean(p[mask])))
    return float(total)


def reliability_curve(labels, probabilities, n_bins: int = 10) -> List[Dict]:
    """Per-bin predicted vs observed rates — the reliability diagram, as data."""
    y = np.asarray(labels, dtype=float).ravel()
    p = np.asarray(probabilities, dtype=float).ravel()
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        mask = (p > lo) & (p <= hi) if lo > 0 else (p >= lo) & (p <= hi)
        n = int(np.sum(mask))
        rows.append({
            "bin_lower": round(float(lo), 4),
            "bin_upper": round(float(hi), 4),
            "n": n,
            "mean_predicted": round(float(np.mean(p[mask])), 5) if n else None,
            "observed_spoof_rate": round(float(np.mean(y[mask])), 5) if n else None,
        })
    return rows


# ── Calibrators ──────────────────────────────────────────────────────────────

@dataclass
class PlattCalibrator:
    """
    Logistic (Platt) calibration: p = sigmoid(a * s + b).

    Two parameters, so it is stable on modest calibration sets, but it can only
    apply a sigmoid-shaped correction.
    """

    a: float = 1.0
    b: float = 0.0
    method: str = "platt"
    version: str = CALIBRATION_VERSION

    def fit(self, scores, labels, iterations: int = 500, lr: float = 0.5) -> "PlattCalibrator":
        s = np.asarray(scores, dtype=np.float64).ravel()
        y = np.asarray(labels, dtype=np.float64).ravel()
        a, b = 1.0, 0.0
        n = max(1, s.size)
        for _ in range(iterations):
            p = 1.0 / (1.0 + np.exp(-(a * s + b)))
            err = p - y
            ga = float(np.dot(err, s) / n)
            gb = float(np.sum(err) / n)
            a -= lr * ga
            b -= lr * gb
        self.a, self.b = float(a), float(b)
        return self

    def predict(self, scores) -> np.ndarray:
        s = np.asarray(scores, dtype=np.float64).ravel()
        return (1.0 / (1.0 + np.exp(-(self.a * s + self.b)))).astype(float)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class IsotonicCalibrator:
    """
    Isotonic regression: a free-form monotonic step function fitted by
    pool-adjacent-violators. More flexible than Platt, and correspondingly
    more prone to overfitting a small calibration set.
    """

    x: List[float] = field(default_factory=list)
    y: List[float] = field(default_factory=list)
    method: str = "isotonic"
    version: str = CALIBRATION_VERSION

    def fit(self, scores, labels) -> "IsotonicCalibrator":
        s = np.asarray(scores, dtype=np.float64).ravel()
        y = np.asarray(labels, dtype=np.float64).ravel()
        order = np.argsort(s, kind="mergesort")
        s, y = s[order], y[order]

        # Pool adjacent violators.
        values = list(y)
        weights = [1.0] * len(y)
        positions = list(range(len(y)))
        i = 0
        while i < len(values) - 1:
            if values[i] > values[i + 1]:
                total_w = weights[i] + weights[i + 1]
                pooled = (values[i] * weights[i] + values[i + 1] * weights[i + 1]) / total_w
                values[i:i + 2] = [pooled]
                weights[i:i + 2] = [total_w]
                positions[i:i + 2] = [positions[i]]
                i = max(i - 1, 0)
            else:
                i += 1

        fitted, idx = [], 0
        for value, weight in zip(values, weights):
            fitted.extend([value] * int(round(weight)))
        fitted = fitted[: s.size]
        self.x = [float(v) for v in s]
        self.y = [float(v) for v in fitted]
        return self

    def predict(self, scores) -> np.ndarray:
        if not self.x:
            return np.asarray(scores, dtype=float).ravel()
        s = np.asarray(scores, dtype=np.float64).ravel()
        return np.interp(s, np.asarray(self.x), np.asarray(self.y),
                         left=self.y[0], right=self.y[-1]).astype(float)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_calibration(labels, raw_scores, calibrated, n_bins: int = 15) -> Dict:
    """Before/after comparison on whichever split the caller supplies."""
    return {
        "brier_raw": brier_score(labels, raw_scores),
        "brier_calibrated": brier_score(labels, calibrated),
        "ece_raw": expected_calibration_error(labels, raw_scores, n_bins),
        "ece_calibrated": expected_calibration_error(labels, calibrated, n_bins),
        "n_bins": n_bins,
        "reliability_raw": reliability_curve(labels, raw_scores),
        "reliability_calibrated": reliability_curve(labels, calibrated),
    }


def save(calibrator, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(calibrator.to_dict(), indent=2))
    return out


def load(path: str | Path):
    data = json.loads(Path(path).read_text())
    if data.get("method") == "platt":
        return PlattCalibrator(a=data["a"], b=data["b"], version=data.get("version", ""))
    if data.get("method") == "isotonic":
        return IsotonicCalibrator(x=data["x"], y=data["y"], version=data.get("version", ""))
    raise ValueError(f"unknown calibration method {data.get('method')!r}")
