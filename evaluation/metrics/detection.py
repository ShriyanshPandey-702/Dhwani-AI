"""
Detection metrics for anti-spoofing evaluation.

Label convention, fixed across the whole harness and never inverted:

    BONAFIDE = 0      genuine human speech
    SPOOF    = 1      synthetic / manipulated speech

A *score* is the model's synthetic probability: higher means more spoof-like.
A sample is called SPOOF when `score >= threshold`.

Error definitions used throughout (stated because the field overloads them):

    FAR  False Acceptance Rate  — spoof wrongly accepted as bona fide
                                = FN / (number of spoof)
    FRR  False Rejection Rate   — bona fide wrongly rejected as spoof
                                = FP / (number of bona fide)
    EER  the operating point where FAR and FRR meet

Note the asymmetry: "accept" means accepting the caller as genuine, so a *false
acceptance* is a missed spoof. This is the security-relevant error.

In the biometric PAD vocabulary the same quantities are:
    APCER = FAR (attack presentation classified as bona fide)
    BPCER = FRR (bona fide presentation classified as attack)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

BONAFIDE = 0
SPOOF = 1


@dataclass
class ConfusionMatrix:
    """Counts at one threshold. Positive class = SPOOF."""

    tp: int   # spoof correctly flagged
    fp: int   # bona fide wrongly flagged  → drives FRR
    tn: int   # bona fide correctly passed
    fn: int   # spoof wrongly passed       → drives FAR

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ThresholdMetrics:
    threshold: float
    far: float
    frr: float
    tpr: float
    tnr: float
    precision: float
    recall: float
    f1: float
    balanced_accuracy: float
    accuracy: float
    confusion: ConfusionMatrix

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confusion"] = self.confusion.to_dict()
        return d


def _validate(labels: np.ndarray, scores: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    labels = np.asarray(labels).astype(int).ravel()
    scores = np.asarray(scores, dtype=float).ravel()
    if labels.shape != scores.shape:
        raise ValueError(f"labels {labels.shape} and scores {scores.shape} differ")
    if labels.size == 0:
        raise ValueError("no samples")
    bad = set(np.unique(labels)) - {BONAFIDE, SPOOF}
    if bad:
        raise ValueError(f"labels must be 0 (bona fide) or 1 (spoof); saw {bad}")
    if not np.all(np.isfinite(scores)):
        raise ValueError("scores contain NaN or inf")
    return labels, scores


def confusion_at(labels, scores, threshold: float) -> ConfusionMatrix:
    """Confusion counts when calling SPOOF iff score >= threshold."""
    labels, scores = _validate(labels, scores)
    predicted_spoof = scores >= threshold
    is_spoof = labels == SPOOF
    return ConfusionMatrix(
        tp=int(np.sum(predicted_spoof & is_spoof)),
        fp=int(np.sum(predicted_spoof & ~is_spoof)),
        tn=int(np.sum(~predicted_spoof & ~is_spoof)),
        fn=int(np.sum(~predicted_spoof & is_spoof)),
    )


def metrics_at(labels, scores, threshold: float) -> ThresholdMetrics:
    """Every headline metric at a single operating point."""
    cm = confusion_at(labels, scores, threshold)
    n_spoof = cm.tp + cm.fn
    n_bona = cm.tn + cm.fp
    total = n_spoof + n_bona

    far = cm.fn / n_spoof if n_spoof else 0.0        # spoof accepted as genuine
    frr = cm.fp / n_bona if n_bona else 0.0          # genuine rejected as spoof
    tpr = cm.tp / n_spoof if n_spoof else 0.0
    tnr = cm.tn / n_bona if n_bona else 0.0
    precision = cm.tp / (cm.tp + cm.fp) if (cm.tp + cm.fp) else 0.0
    f1 = (2 * precision * tpr / (precision + tpr)) if (precision + tpr) else 0.0

    return ThresholdMetrics(
        threshold=float(threshold),
        far=far, frr=frr, tpr=tpr, tnr=tnr,
        precision=precision, recall=tpr, f1=f1,
        balanced_accuracy=(tpr + tnr) / 2.0,
        accuracy=(cm.tp + cm.tn) / total if total else 0.0,
        confusion=cm,
    )


def roc_curve(labels, scores) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    ROC over all distinct score thresholds.

    Returns (fpr, tpr, thresholds) with the positive class = SPOOF. `fpr` here
    is the bona-fide rejection rate, i.e. FRR.
    """
    labels, scores = _validate(labels, scores)
    order = np.argsort(-scores, kind="mergesort")
    s = scores[order]
    y = (labels[order] == SPOOF).astype(int)

    distinct = np.where(np.diff(s))[0]
    idx = np.r_[distinct, y.size - 1]

    tps = np.cumsum(y)[idx]
    fps = 1 + idx - tps
    n_pos, n_neg = int(y.sum()), int(y.size - y.sum())

    tpr = tps / n_pos if n_pos else np.zeros_like(tps, dtype=float)
    fpr = fps / n_neg if n_neg else np.zeros_like(fps, dtype=float)
    return np.r_[0.0, fpr], np.r_[0.0, tpr], np.r_[np.inf, s[idx]]


def roc_auc(labels, scores) -> float:
    """
    Threshold-independent ranking quality, via the Mann-Whitney statistic so
    ties are handled correctly.
    """
    labels, scores = _validate(labels, scores)
    pos = scores[labels == SPOOF]
    neg = scores[labels == BONAFIDE]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    ranks = _rankdata(np.concatenate([pos, neg]))
    return float((ranks[: pos.size].sum() - pos.size * (pos.size + 1) / 2.0)
                 / (pos.size * neg.size))


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks, ties shared (equivalent to scipy.stats.rankdata)."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(a.size, dtype=float)
    sorted_a = a[order]
    i = 0
    while i < a.size:
        j = i
        while j + 1 < a.size and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def pr_auc(labels, scores) -> float:
    """Average precision for the SPOOF class."""
    labels, scores = _validate(labels, scores)
    order = np.argsort(-scores, kind="mergesort")
    y = (labels[order] == SPOOF).astype(int)
    n_pos = int(y.sum())
    if n_pos == 0:
        return float("nan")
    tps = np.cumsum(y)
    precision = tps / np.arange(1, y.size + 1)
    return float(np.sum(precision * y) / n_pos)


def eer(labels, scores) -> Tuple[float, float]:
    """
    Equal Error Rate and the threshold achieving it.

    Returns (eer, threshold). Found by scanning the ROC for the crossing of
    FAR (= 1 - TPR) and FRR (= FPR), then interpolating between the bracketing
    points rather than snapping to the nearest one.
    """
    fpr, tpr, thresholds = roc_curve(labels, scores)
    frr = fpr
    far = 1.0 - tpr
    diff = far - frr

    sign_change = np.where(np.diff(np.sign(diff)))[0]
    if sign_change.size == 0:
        i = int(np.argmin(np.abs(diff)))
        return float((far[i] + frr[i]) / 2.0), float(thresholds[i])

    i = int(sign_change[0])
    d0, d1 = diff[i], diff[i + 1]
    t = 0.0 if d1 == d0 else d0 / (d0 - d1)
    value = float((far[i] + t * (far[i + 1] - far[i])
                   + frr[i] + t * (frr[i + 1] - frr[i])) / 2.0)
    lo, hi = thresholds[i], thresholds[i + 1]
    threshold = float(hi if not np.isfinite(lo) else lo + t * (hi - lo))
    return value, threshold


def threshold_sweep(labels, scores, thresholds: Optional[Sequence[float]] = None
                    ) -> List[ThresholdMetrics]:
    """Metrics across an explicit grid of operating points."""
    if thresholds is None:
        thresholds = np.round(np.arange(0.0, 1.0001, 0.01), 4)
    return [metrics_at(labels, scores, float(t)) for t in thresholds]


def find_threshold_for_far(labels, scores, target_far: float) -> Tuple[float, ThresholdMetrics]:
    """
    HIGHEST threshold whose FAR is at or below `target_far`.

    Security-oriented selection: bound the missed-spoof rate first, then take
    the most permissive threshold that still respects the bound, so the FRR
    cost is the smallest one compatible with it.

    The direction matters. FAR rises monotonically with the threshold (a higher
    bar flags fewer samples as spoof, so more spoof slips through), which makes
    the *lowest* qualifying threshold trivially 0.0 — flag everything, FAR 0,
    FRR 1. That is not an operating point, it is a refusal to operate.
    """
    grid = np.round(np.arange(0.0, 1.0001, 0.001), 5)
    best = None
    for t in grid:
        m = metrics_at(labels, scores, float(t))
        if m.far <= target_far:
            best = m          # keep going; we want the largest qualifying t
        else:
            break             # FAR is monotonic, so no later t can qualify
    if best is None:
        best = metrics_at(labels, scores, 0.0)
    return best.threshold, best


def summarise(labels, scores, threshold: float) -> Dict:
    """Everything needed for one row of a results table."""
    e, e_threshold = eer(labels, scores)
    m = metrics_at(labels, scores, threshold)
    labels_arr, _ = _validate(labels, scores)
    return {
        "n_total": int(labels_arr.size),
        "n_bonafide": int(np.sum(labels_arr == BONAFIDE)),
        "n_spoof": int(np.sum(labels_arr == SPOOF)),
        "roc_auc": roc_auc(labels, scores),
        "pr_auc": pr_auc(labels, scores),
        "eer": e,
        "eer_threshold": e_threshold,
        "operating_threshold": float(threshold),
        "far": m.far,
        "frr": m.frr,
        "apcer": m.far,     # PAD vocabulary for the same quantity
        "bpcer": m.frr,
        "tpr": m.tpr,
        "tnr": m.tnr,
        "precision": m.precision,
        "f1": m.f1,
        "balanced_accuracy": m.balanced_accuracy,
        "accuracy": m.accuracy,
        "confusion": m.confusion.to_dict(),
    }
