"""
Phase 1 training-pipeline tests.

These exist to make the scientific guarantees mechanical rather than trusted:
no test-set leakage, deterministic seeds, correct freezing, frozen BatchNorm
that genuinely does not drift, and checkpoints that round-trip and stay
compatible with the production streaming contract.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parents[3]
for p in (str(REPO), str(REPO / "services" / "api")):
    if p not in sys.path:
        sys.path.insert(0, p)

from app.ml.authenticity.aasist import MODEL_CONFIGS, NB_SAMP, SAMPLE_RATE  # noqa: E402
from app.ml.authenticity.vendor.aasist_model import Model  # noqa: E402
from training import data as tdata  # noqa: E402
from training.schemes import (  # noqa: E402
    SCHEMES, apply_scheme, frozen_bn_running_stats, set_train_mode,
)

DATA_ROOT = REPO / "data" / "external" / "LA_extract_full"
has_data = DATA_ROOT.is_dir()


def fresh_model():
    return Model(MODEL_CONFIGS["AASIST-L"])


# ── Split correctness / leakage ──────────────────────────────────────────────

def test_only_train_and_dev_splits_are_loadable():
    """Test corpora must be unreachable from the training package."""
    for forbidden in ("eval", "test", "mlaad", "wavefake", "in_the_wild"):
        with pytest.raises(ValueError, match="not permitted"):
            tdata.load_items(DATA_ROOT, forbidden)


def test_allowed_splits_are_exactly_train_and_dev():
    assert tdata.ALLOWED_SPLITS == ("train", "dev")


@pytest.mark.skipif(not has_data, reason="ASVspoof LA not present")
def test_train_and_dev_are_speaker_disjoint_and_file_disjoint():
    tr = tdata.load_items(DATA_ROOT, "train")
    dv = tdata.load_items(DATA_ROOT, "dev")
    assert {i.path for i in tr} & {i.path for i in dv} == set()
    assert {i.speaker_id for i in tr} & {i.speaker_id for i in dv} == set()


@pytest.mark.skipif(not has_data, reason="ASVspoof LA not present")
def test_training_data_contains_no_test_corpus_paths():
    tr = tdata.load_items(DATA_ROOT, "train")
    banned = ("InTheWild", "MLAAD", "WaveFake", "LJSpeech", "_eval")
    assert not [i for i in tr if any(b in i.path for b in banned)]


# ── Class balancing ──────────────────────────────────────────────────────────

@pytest.mark.skipif(not has_data, reason="ASVspoof LA not present")
def test_balanced_subset_is_one_to_one_and_covers_all_attacks():
    tr = tdata.load_items(DATA_ROOT, "train")
    sel = tdata.balanced_subset(tr, seed=1337)
    d = tdata.distribution(sel)
    assert d["bonafide"] == d["spoof"], d
    systems = {i.system_id for i in sel if i.label == tdata.SPOOF}
    assert systems == {"A01", "A02", "A03", "A04", "A05", "A06"}, systems


@pytest.mark.skipif(not has_data, reason="ASVspoof LA not present")
def test_balanced_subset_is_deterministic_for_a_fixed_seed():
    tr = tdata.load_items(DATA_ROOT, "train")
    a = [i.path for i in tdata.balanced_subset(tr, seed=1337, per_class=50)]
    b = [i.path for i in tdata.balanced_subset(tr, seed=1337, per_class=50)]
    c = [i.path for i in tdata.balanced_subset(tr, seed=2026, per_class=50)]
    assert a == b
    assert a != c


# ── Freezing schemes ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("scheme,expected", [
    ("A", 322), ("B1", 34514), ("B2", 66234), ("C", 85306),
])
def test_trainable_parameter_counts_are_exact(scheme, expected):
    info = apply_scheme(fresh_model(), scheme)
    assert info.trainable_params == expected
    assert info.total_params == 85306


def test_scheme_a_trains_only_the_head():
    m = fresh_model()
    apply_scheme(m, "A")
    trainable = {n for n, p in m.named_parameters() if p.requires_grad}
    assert trainable == {"out_layer.weight", "out_layer.bias"}


def test_scheme_c_leaves_nothing_frozen():
    m = fresh_model()
    info = apply_scheme(m, "C")
    assert all(p.requires_grad for p in m.parameters())
    assert info.frozen_bn_modules == 0


def test_sinc_front_end_has_no_trainable_parameters():
    """So 'freezing the front-end' is not a meaningful scheme — documented, not offered."""
    m = fresh_model()
    conv = dict(m.named_modules())["conv_time"]
    assert sum(p.numel() for p in conv.parameters()) == 0


# ── BatchNorm freezing actually holds ────────────────────────────────────────

@pytest.mark.parametrize("scheme", ["A", "B1", "B2"])
def test_frozen_batchnorm_modules_are_in_eval_mode(scheme):
    m = fresh_model()
    apply_scheme(m, scheme)
    set_train_mode(m, scheme)
    frozen = frozen_bn_running_stats(m, scheme)
    assert frozen, "expected at least one frozen BatchNorm"
    for name, mod in m.named_modules():
        if name in frozen:
            assert not mod.training, f"{name} should be in eval mode"


@pytest.mark.parametrize("scheme", ["A", "B1", "B2"])
def test_frozen_batchnorm_running_stats_do_not_drift(scheme):
    """requires_grad=False alone would NOT prevent this; eval() mode does."""
    torch.manual_seed(0)
    m = fresh_model()
    apply_scheme(m, scheme)
    set_train_mode(m, scheme)
    before = frozen_bn_running_stats(m, scheme)
    m(torch.randn(2, NB_SAMP))          # forward passes would update BN stats
    m(torch.randn(2, NB_SAMP))
    after = frozen_bn_running_stats(m, scheme)
    for name in before:
        assert torch.equal(before[name][0], after[name][0]), f"{name} mean drifted"
        assert torch.equal(before[name][1], after[name][1]), f"{name} var drifted"


def test_unfrozen_batchnorm_does_drift_in_scheme_c():
    """Control for the test above: without freezing, stats really do move."""
    torch.manual_seed(0)
    m = fresh_model()
    apply_scheme(m, "C")
    set_train_mode(m, "C")
    bn = dict(m.named_modules())["first_bn"]
    before = bn.running_mean.detach().clone()
    m(torch.randn(2, NB_SAMP))
    assert not torch.equal(before, bn.running_mean)


# ── Label convention ─────────────────────────────────────────────────────────

def test_dataset_labels_are_inverted_into_the_aasist_convention():
    """
    AASIST output index 1 = bona fide; our labels are 0 = bona fide.
    Training against un-inverted targets teaches the opposite of the
    pretrained behaviour, so the mapping is asserted here.
    """
    from training.train import to_model_target
    labels = torch.tensor([tdata.BONAFIDE, tdata.SPOOF])
    assert to_model_target(labels).tolist() == [1, 0]


# ── Determinism ──────────────────────────────────────────────────────────────

def test_seed_everything_makes_torch_deterministic():
    from training.train import seed_everything
    seed_everything(1337); a = torch.randn(8)
    seed_everything(1337); b = torch.randn(8)
    seed_everything(2026); c = torch.randn(8)
    assert torch.equal(a, b)
    assert not torch.equal(a, c)


# ── Preprocessing parity with inference ──────────────────────────────────────

def test_fit_length_matches_the_inference_implementation():
    from app.ml.authenticity.aasist import AASISTDetector
    rng = np.random.default_rng(0)
    for n in (1000, NB_SAMP, NB_SAMP * 2 + 7):
        a = rng.standard_normal(n).astype(np.float32)
        assert np.array_equal(tdata.fit_length(a), AASISTDetector._fit_length(a))


def test_dataset_emits_exactly_the_inference_window():
    item = tdata.Item(path="missing.flac", label=tdata.BONAFIDE, speaker_id="X",
                      system_id="-")
    x, y = tdata.ASVspoofWindows([item])[0]
    assert x.shape == (NB_SAMP,)
    assert x.dtype == torch.float32
    assert y == tdata.BONAFIDE


# ── Checkpoint save/load + SHA-256 + inference compatibility ─────────────────

def test_checkpoint_round_trips_and_hashes_stably(tmp_path):
    torch.manual_seed(0)
    m = fresh_model()
    p = tmp_path / "ck.pth"
    torch.save(m.state_dict(), p)

    def sha(path):
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 20), b""):
                h.update(c)
        return h.hexdigest()

    first = sha(p)
    m2 = fresh_model()
    m2.load_state_dict(torch.load(p, map_location="cpu"), strict=True)
    torch.save(m2.state_dict(), p)
    assert sha(p) == first
    for (n1, p1), (n2, p2) in zip(m.named_parameters(), m2.named_parameters()):
        assert n1 == n2 and torch.equal(p1, p2)


def test_finetuned_checkpoint_stays_loadable_by_the_production_detector(tmp_path):
    """A Phase 1 checkpoint must drop into the existing loader with strict=True."""
    torch.manual_seed(0)
    m = fresh_model()
    apply_scheme(m, "C")
    p = tmp_path / "phase1.pth"
    torch.save(m.state_dict(), p)
    fresh = Model(MODEL_CONFIGS["AASIST-L"])
    fresh.load_state_dict(torch.load(p, map_location="cpu"), strict=True)  # must not raise


# ── Output schema + streaming contract ───────────────────────────────────────

def test_model_output_schema_is_unchanged():
    m = fresh_model(); m.eval()
    with torch.no_grad():
        out = m(torch.zeros(2, NB_SAMP))
    assert isinstance(out, (tuple, list)) and len(out) == 2
    assert out[1].shape == (2, 2), "two logits per sample"


def test_streaming_window_contract_is_unchanged():
    from app.core.config import settings
    assert SAMPLE_RATE == 16000
    assert NB_SAMP == 64600
    assert settings.ANALYSIS_WINDOW_MS == 4038
    assert settings.ANALYSIS_HOP_MS == 1000


def test_freq_aug_flag_is_accepted_and_off_by_default():
    import inspect
    sig = inspect.signature(Model.forward)
    assert sig.parameters["Freq_aug"].default is False
    m = fresh_model(); m.eval()
    with torch.no_grad():
        m(torch.zeros(1, NB_SAMP), Freq_aug=True)   # must not raise
