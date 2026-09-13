"""
Detection-metric correctness.

These are the numbers every claim in the evaluation rests on, so they are
tested against hand-computable cases rather than against themselves.
"""

import numpy as np
import pytest

from evaluation.metrics.detection import (
    BONAFIDE, SPOOF, confusion_at, eer, find_threshold_for_far, metrics_at,
    pr_auc, roc_auc, roc_curve, summarise, threshold_sweep,
)


# ── Label convention ─────────────────────────────────────────────────────────

def test_label_constants_are_not_inverted():
    assert BONAFIDE == 0 and SPOOF == 1


def test_non_binary_labels_are_rejected():
    with pytest.raises(ValueError):
        roc_auc([0, 1, 2], [0.1, 0.2, 0.3])


def test_non_finite_scores_are_rejected():
    with pytest.raises(ValueError):
        roc_auc([0, 1], [0.1, np.nan])


def test_mismatched_lengths_are_rejected():
    with pytest.raises(ValueError):
        roc_auc([0, 1, 1], [0.1, 0.2])


# ── Confusion / FAR / FRR semantics ──────────────────────────────────────────

def test_confusion_counts_are_hand_checkable():
    # 2 bona fide (0.1, 0.9), 2 spoof (0.2, 0.8); threshold 0.5
    labels = [BONAFIDE, BONAFIDE, SPOOF, SPOOF]
    scores = [0.1, 0.9, 0.2, 0.8]
    cm = confusion_at(labels, scores, 0.5)
    assert cm.tn == 1   # bona fide 0.1 passed
    assert cm.fp == 1   # bona fide 0.9 wrongly flagged
    assert cm.fn == 1   # spoof 0.2 wrongly passed
    assert cm.tp == 1   # spoof 0.8 flagged


def test_far_is_missed_spoof_and_frr_is_rejected_genuine():
    """The security-critical direction: FAR counts spoofs let through."""
    labels = [BONAFIDE] * 10 + [SPOOF] * 10
    scores = [0.0] * 10 + [0.0] * 8 + [1.0] * 2   # 8 spoofs score like bona fide
    m = metrics_at(labels, scores, 0.5)
    assert m.far == pytest.approx(0.8)    # 8 of 10 spoof accepted
    assert m.frr == pytest.approx(0.0)    # no bona fide rejected


def test_threshold_zero_flags_everything_and_one_flags_almost_nothing():
    labels = [BONAFIDE] * 5 + [SPOOF] * 5
    scores = [0.2] * 5 + [0.8] * 5
    at_zero = metrics_at(labels, scores, 0.0)
    assert at_zero.frr == pytest.approx(1.0) and at_zero.far == pytest.approx(0.0)
    at_one = metrics_at(labels, scores, 1.0)
    assert at_one.far == pytest.approx(1.0) and at_one.frr == pytest.approx(0.0)


# ── ROC / AUC ────────────────────────────────────────────────────────────────

def test_auc_is_one_for_perfect_separation():
    assert roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(1.0)


def test_auc_is_zero_for_perfectly_inverted_scores():
    assert roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(0.0)


def test_auc_is_half_for_constant_scores():
    assert roc_auc([0, 1] * 50, [0.5] * 100) == pytest.approx(0.5)


def test_auc_handles_ties_by_averaging_ranks():
    # One tie straddling the classes → AUC strictly between 0.5 and 1.
    auc = roc_auc([0, 0, 1, 1], [0.1, 0.5, 0.5, 0.9])
    assert 0.5 < auc < 1.0


def test_roc_curve_is_monotonic_and_anchored():
    fpr, tpr, _ = roc_curve([0] * 20 + [1] * 20,
                            list(np.linspace(0, 0.6, 20)) + list(np.linspace(0.4, 1, 20)))
    assert fpr[0] == 0.0 and tpr[0] == 0.0
    assert np.all(np.diff(fpr) >= -1e-12)
    assert np.all(np.diff(tpr) >= -1e-12)


def test_pr_auc_is_one_for_perfect_separation():
    assert pr_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == pytest.approx(1.0)


# ── EER ──────────────────────────────────────────────────────────────────────

def test_eer_is_zero_for_perfect_separation():
    value, _ = eer([0] * 50 + [1] * 50, [0.1] * 50 + [0.9] * 50)
    assert value == pytest.approx(0.0, abs=1e-9)


def test_eer_is_half_for_random_scores():
    value, _ = eer([0, 1] * 200, [0.5] * 400)
    assert value == pytest.approx(0.5, abs=0.02)


def test_eer_threshold_gives_roughly_equal_errors():
    rng = np.random.default_rng(0)
    labels = np.r_[np.zeros(600, int), np.ones(600, int)]
    scores = np.r_[rng.normal(0.35, 0.15, 600), rng.normal(0.65, 0.15, 600)]
    scores = np.clip(scores, 0, 1)
    value, threshold = eer(labels, scores)
    m = metrics_at(labels, scores, threshold)
    assert abs(m.far - m.frr) < 0.06
    assert value == pytest.approx((m.far + m.frr) / 2, abs=0.06)


# ── Threshold sweep and security-oriented selection ──────────────────────────

def test_threshold_sweep_covers_the_range_and_far_falls_as_frr_rises():
    rng = np.random.default_rng(1)
    labels = np.r_[np.zeros(300, int), np.ones(300, int)]
    scores = np.clip(np.r_[rng.normal(0.3, 0.15, 300), rng.normal(0.7, 0.15, 300)], 0, 1)
    sweep = threshold_sweep(labels, scores)
    assert len(sweep) == 101
    assert sweep[0].threshold == 0.0 and sweep[-1].threshold == pytest.approx(1.0)
    # FAR rises with threshold, FRR falls — the fundamental tradeoff.
    assert sweep[0].far <= sweep[-1].far
    assert sweep[0].frr >= sweep[-1].frr


def test_find_threshold_for_far_bounds_the_missed_spoof_rate():
    rng = np.random.default_rng(2)
    labels = np.r_[np.zeros(400, int), np.ones(400, int)]
    scores = np.clip(np.r_[rng.normal(0.3, 0.12, 400), rng.normal(0.7, 0.12, 400)], 0, 1)
    threshold, m = find_threshold_for_far(labels, scores, target_far=0.05)
    assert m.far <= 0.05 + 1e-9
    assert 0.0 <= threshold <= 1.0


def test_summarise_reports_both_pad_and_biometric_names():
    labels = [0] * 10 + [1] * 10
    scores = [0.2] * 10 + [0.8] * 10
    out = summarise(labels, scores, 0.5)
    assert out["apcer"] == out["far"]
    assert out["bpcer"] == out["frr"]
    assert out["n_bonafide"] == 10 and out["n_spoof"] == 10


# ── Security-threshold selection direction ───────────────────────────────────

def test_far_bounded_threshold_is_the_highest_qualifying_one():
    """
    FAR rises with the threshold, so the *lowest* threshold meeting a FAR bound
    is trivially 0.0 — which flags everything and rejects every genuine caller.
    The selector must return the highest qualifying threshold instead.
    """
    labels = [BONAFIDE] * 100 + [SPOOF] * 100
    scores = [0.1] * 100 + [0.9] * 100          # cleanly separable
    threshold, m = find_threshold_for_far(labels, scores, 0.01)

    assert threshold > 0.0, "threshold 0.0 rejects every bona fide caller"
    assert m.far <= 0.01
    assert m.frr < 1.0, "a usable operating point must not reject everyone"
    # The best available point here sits between the two clusters.
    assert 0.1 < threshold <= 0.9


def test_far_bounded_threshold_minimises_frr_subject_to_the_bound():
    rng = np.random.default_rng(11)
    labels = np.r_[np.zeros(500, int), np.ones(500, int)]
    scores = np.clip(np.r_[rng.normal(0.25, 0.12, 500), rng.normal(0.75, 0.12, 500)], 0, 1)

    threshold, chosen = find_threshold_for_far(labels, scores, 0.02)
    assert chosen.far <= 0.02
    # Any higher threshold must break the bound — otherwise we left usability
    # on the table.
    higher = metrics_at(labels, scores, min(1.0, threshold + 0.05))
    assert higher.far > 0.02 or higher.frr >= chosen.frr


def test_with_no_separation_a_far_bound_costs_every_genuine_caller():
    """
    When the scores carry no information, bounding FAR at 0 is only achievable
    by flagging everything — FRR 1.0. The selector must return that point
    honestly rather than pretending a usable threshold exists.
    """
    labels = [BONAFIDE] * 10 + [SPOOF] * 10
    scores = [0.5] * 20                         # no separation at all
    threshold, m = find_threshold_for_far(labels, scores, 0.0)
    assert m.far == 0.0
    assert m.frr == 1.0, "with no separation, a zero-FAR bound rejects everyone"
    # `score >= threshold` means 0.5 still flags every sample, so 0.5 is the
    # highest qualifying threshold, not 0.0.
    assert threshold == pytest.approx(0.5)
