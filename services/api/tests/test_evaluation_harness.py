"""
Evaluation harness: dataset representation, leakage auditing, calibration,
robustness transforms and streaming aggregation.
"""

import numpy as np
import pytest

from evaluation.calibration.calibrate import (
    CALIBRATION_VERSION, IsotonicCalibrator, PlattCalibrator, brier_score,
    evaluate_calibration, expected_calibration_error, load, reliability_curve, save,
)
from evaluation.datasets.base import (
    BONAFIDE, SPOOF, Sample, audit_split_disjointness, find_duplicate_paths,
    label_distribution, read_manifest, split_stats, validate_labels, write_manifest,
)
from evaluation.metrics.detection import roc_auc
from evaluation.robustness.transforms import CONDITIONS, apply_condition
from evaluation.runners.streaming import (
    agg_ema, agg_median, compare_aggregators, count_isolated_flips,
    decisions_confirm, decisions_hysteresis, detection_delay,
)


def make(n_bona=3, n_spoof=3, split="test", speaker_prefix="S"):
    out = []
    for i in range(n_bona):
        out.append(Sample(f"/a/bona_{split}_{i}.wav", BONAFIDE, "ds", split,
                          speaker_id=f"{speaker_prefix}{i}"))
    for i in range(n_spoof):
        out.append(Sample(f"/a/spoof_{split}_{i}.wav", SPOOF, "ds", split,
                          speaker_id=f"{speaker_prefix}{i}", system_id=f"A{i:02d}"))
    return out


# ── Dataset representation ───────────────────────────────────────────────────

def test_label_distribution_and_split_stats():
    samples = make(4, 6)
    assert label_distribution(samples) == {"bonafide": 4, "spoof": 6}
    stats = split_stats(samples, "test")
    assert stats.n_total == 10 and stats.n_bonafide == 4 and stats.n_spoof == 6


def test_validate_labels_requires_both_classes():
    validate_labels(make(2, 2))
    with pytest.raises(ValueError):
        validate_labels(make(3, 0))
    with pytest.raises(ValueError):
        validate_labels(make(0, 3))


def test_validate_labels_rejects_out_of_range_values():
    bad = make(1, 1)
    bad[0].label = 2
    with pytest.raises(ValueError):
        validate_labels(bad)


def test_duplicate_paths_are_detected():
    samples = make(2, 2)
    samples.append(Sample(samples[0].audio_path, BONAFIDE, "ds", "test"))
    assert samples[0].audio_path in find_duplicate_paths(samples)


def test_manifest_roundtrip_preserves_every_field(tmp_path):
    samples = make(2, 2)
    path = write_manifest(samples, tmp_path / "m.csv")
    restored = read_manifest(path)
    assert len(restored) == len(samples)
    assert [s.label for s in restored] == [s.label for s in samples]
    assert [s.system_id for s in restored] == [s.system_id for s in samples]


# ── Leakage audit (mandatory) ────────────────────────────────────────────────

def test_disjoint_splits_are_reported_clean():
    samples = make(3, 3, split="calib", speaker_prefix="C") + \
              make(3, 3, split="test", speaker_prefix="T")
    report = audit_split_disjointness(samples, ["calib", "test"])
    assert report["clean"] is True
    assert report["file_overlap"]["calib|test"] == 0
    assert report["speaker_overlap"]["calib|test"] == []


def test_file_overlap_between_splits_is_flagged():
    samples = make(2, 2, split="calib")
    leaked = Sample(samples[0].audio_path, BONAFIDE, "ds", "test")
    report = audit_split_disjointness(samples + [leaked], ["calib", "test"])
    assert report["clean"] is False
    assert report["file_overlap"]["calib|test"] == 1


def test_speaker_overlap_is_reported_even_when_files_differ():
    """Speaker leakage is subtler than file leakage and must be surfaced."""
    calib = make(2, 2, split="calib", speaker_prefix="X")
    test = make(2, 2, split="test", speaker_prefix="X")   # same speakers
    report = audit_split_disjointness(calib + test, ["calib", "test"])
    assert report["file_overlap"]["calib|test"] == 0
    assert report["speaker_overlap"]["calib|test"] != []


# ── Calibration ──────────────────────────────────────────────────────────────

@pytest.fixture
def miscalibrated():
    rng = np.random.default_rng(7)
    y = rng.integers(0, 2, 3000)
    s = np.where(y == 1, rng.beta(5, 1.5, 3000), rng.beta(1.5, 5, 3000))
    return y, s


def test_platt_improves_calibration_without_changing_ranking(miscalibrated):
    y, s = miscalibrated
    cal = PlattCalibrator().fit(s, y)
    p = cal.predict(s)
    assert brier_score(y, p) < brier_score(y, s)
    assert roc_auc(y, p) == pytest.approx(roc_auc(y, s), abs=1e-6)


def test_isotonic_improves_calibration_and_stays_monotonic(miscalibrated):
    y, s = miscalibrated
    cal = IsotonicCalibrator().fit(s, y)
    p = cal.predict(s)
    assert expected_calibration_error(y, p) <= expected_calibration_error(y, s)
    order = np.argsort(s)
    assert np.all(np.diff(cal.predict(s[order])) >= -1e-9)


def test_calibrator_persists_and_reloads(tmp_path, miscalibrated):
    y, s = miscalibrated
    cal = PlattCalibrator().fit(s, y)
    path = save(cal, tmp_path / "cal.json")
    restored = load(path)
    assert np.allclose(restored.predict(s), cal.predict(s))
    assert restored.version == CALIBRATION_VERSION


def test_evaluate_calibration_reports_before_and_after(miscalibrated):
    y, s = miscalibrated
    p = PlattCalibrator().fit(s, y).predict(s)
    report = evaluate_calibration(y, s, p)
    assert report["brier_calibrated"] < report["brier_raw"]
    assert len(report["reliability_raw"]) == 10


def test_reliability_curve_bins_cover_the_unit_interval(miscalibrated):
    y, s = miscalibrated
    rows = reliability_curve(y, s, n_bins=10)
    assert rows[0]["bin_lower"] == 0.0 and rows[-1]["bin_upper"] == 1.0


def test_calibration_fitted_on_one_split_is_applied_to_another(miscalibrated):
    """Calibration must be fittable on A and evaluable on a disjoint B."""
    y, s = miscalibrated
    half = len(y) // 2
    cal = PlattCalibrator().fit(s[:half], y[:half])
    held_out = cal.predict(s[half:])
    assert brier_score(y[half:], held_out) < brier_score(y[half:], s[half:])


# ── Robustness transforms ────────────────────────────────────────────────────

@pytest.fixture
def speech():
    t = np.arange(16000 * 3) / 16000.0
    sig = 0.3 * np.sin(2 * np.pi * 180 * t) * (1 + 0.5 * np.sin(2 * np.pi * 4 * t))
    return sig.astype(np.float32)


@pytest.mark.parametrize("condition", sorted(CONDITIONS))
def test_every_condition_is_finite_and_deterministic(condition, speech):
    a = apply_condition(condition, speech, seed=11)
    b = apply_condition(condition, speech, seed=11)
    assert np.all(np.isfinite(a))
    assert np.array_equal(a, b), "conditions must be reproducible for a given seed"
    assert np.max(np.abs(a)) <= 1.0 + 1e-6


def test_noise_conditions_lower_the_snr_monotonically(speech):
    from evaluation.robustness.transforms import add_noise

    def residual_power(snr):
        return float(np.mean((add_noise(speech, snr, seed=3) - speech) ** 2))

    assert residual_power(0) > residual_power(10) > residual_power(20)


def test_bandlimiting_removes_high_frequency_energy():
    """
    Uses a broadband signal on purpose: a low-frequency tone has no energy above
    4 kHz to remove, so testing the filter on one would assert nothing.
    """
    from evaluation.robustness.transforms import telephone_band

    rng = np.random.default_rng(5)
    broadband = (rng.standard_normal(16000 * 2) * 0.2).astype(np.float32)

    def high_energy(x):
        spec = np.abs(np.fft.rfft(x))
        freqs = np.fft.rfftfreq(x.size, 1 / 16000)
        return float(np.sum(spec[freqs > 4000] ** 2))

    before, after = high_energy(broadband), high_energy(telephone_band(broadband))
    assert before > 0, "the probe signal must actually contain high-frequency energy"
    assert after < before * 0.05, f"band-limiting should remove most HF energy ({after:.3g} vs {before:.3g})"


def test_clipping_reduces_peak_amplitude(speech):
    from evaluation.robustness.transforms import clip_signal

    out = clip_signal(speech, 0.1)
    assert np.max(np.abs(out)) <= 0.1 + 1e-6
    assert np.max(np.abs(out)) < np.max(np.abs(speech))


def test_unknown_condition_raises():
    with pytest.raises(KeyError):
        apply_condition("does_not_exist", np.zeros(1000, np.float32))


# ── Streaming aggregation ────────────────────────────────────────────────────

def test_ema_and_median_reduce_jitter_from_an_isolated_spike():
    series = [0.1, 0.1, 0.1, 0.95, 0.1, 0.1, 0.1]
    for smoothed in (agg_ema(series, 0.4), agg_median(series, 3)):
        assert max(smoothed) < max(series)


def test_confirmation_suppresses_a_single_window_false_alert():
    series = [0.1, 0.1, 0.9, 0.1, 0.1]          # one anomalous window
    raw = [int(s >= 0.5) for s in series]
    confirmed = decisions_confirm(series, 0.5, n=2)
    assert sum(raw) == 1
    assert sum(confirmed) == 0, "a lone window must not raise an alert"


def test_confirmation_still_detects_a_sustained_change():
    series = [0.1, 0.1, 0.9, 0.9, 0.9]
    assert decisions_confirm(series, 0.5, n=2)[-1] == 1


def test_hysteresis_holds_state_through_a_dip():
    series = [0.9, 0.9, 0.5, 0.9]              # dips but stays above clear_at
    assert decisions_hysteresis(series, raise_at=0.7, clear_at=0.4) == [1, 1, 1, 1]


def test_isolated_flip_counter():
    assert count_isolated_flips([0, 0, 1, 0, 0]) == 1
    assert count_isolated_flips([0, 0, 1, 1, 1]) == 0


def test_detection_delay_measures_sustained_decisions_only():
    # Blip at index 2, sustained detection from index 5.
    decisions = [0, 0, 1, 0, 0, 1, 1, 1]
    assert detection_delay([0] * 8, decisions, transition_window=1, hop_ms=1000) == 4.0


def test_detection_delay_is_none_when_never_sustained():
    assert detection_delay([0] * 5, [0, 0, 1, 0, 0], 0) is None


def test_compare_aggregators_reports_every_strategy():
    series = [0.1, 0.9, 0.1, 0.9, 0.1, 0.9]
    out = compare_aggregators(series, 0.5)
    for key in ("raw", "ema_0.4", "median_3", "confirm_2", "hysteresis"):
        assert key in out
    assert out["median_3"]["isolated_flips"] <= out["raw"]["isolated_flips"]
