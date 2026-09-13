"""
Phase 1 dataset: ASVspoof 2019 LA train/dev only.

TRAIN-ALLOWED   ASVspoof 2019 LA train  (A01-A06, 20 speakers) — ODC-BY
VALIDATION-ONLY ASVspoof 2019 LA dev    (A01-A06, 20 speakers, disjoint)
EXCLUDED        everything else (see docs/phase1_training.md §3)

The loader refuses, by construction, to open any corpus other than these two.
That refusal is tested (`tests/test_phase1_training.py`).

Preprocessing is imported from the *inference* path so training and inference
cannot drift: same 16 kHz mono, same 64600-sample tile/centre-crop policy.
"""

from __future__ import annotations

import collections
import random
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import torch
from torch.utils.data import Dataset

# Only these two splits may ever be constructed.
ALLOWED_SPLITS = ("train", "dev")

BONAFIDE = 0
SPOOF = 1
SAMPLE_RATE = 16000
NB_SAMP = 64600


@dataclass(frozen=True)
class Item:
    path: str
    label: int
    speaker_id: str
    system_id: str


def _protocol_dir(root: Path) -> Path:
    for c in (root / "ASVspoof2019_LA_cm_protocols",
              root / "LA" / "ASVspoof2019_LA_cm_protocols"):
        if c.is_dir():
            return c
    raise FileNotFoundError(f"protocol directory not found under {root}")


def _audio_dir(root: Path, split: str) -> Path:
    name = {"train": "ASVspoof2019_LA_train", "dev": "ASVspoof2019_LA_dev"}[split]
    for c in (root / name / "flac", root / "LA" / name / "flac"):
        if c.is_dir():
            return c
    raise FileNotFoundError(f"audio for split '{split}' not found under {root}")


_PROTOCOL_FILE = {"train": "ASVspoof2019.LA.cm.train.trn.txt",
                  "dev": "ASVspoof2019.LA.cm.dev.trl.txt"}


def load_items(root: str | Path, split: str) -> List[Item]:
    """Read one ASVspoof LA split. Raises for any split that is not train/dev."""
    if split not in ALLOWED_SPLITS:
        raise ValueError(
            f"split {split!r} is not permitted in training. Phase 1 may only use "
            f"{ALLOWED_SPLITS}; eval/MLAAD/WaveFake/In-the-Wild are TEST-ONLY."
        )
    root = Path(root)
    proto = _protocol_dir(root) / _PROTOCOL_FILE[split]
    audio = _audio_dir(root, split)
    items: List[Item] = []
    for line in open(proto):
        parts = line.split()
        if len(parts) < 5:
            continue
        speaker, fname, _, system, key = parts[0], parts[1], parts[2], parts[3], parts[4]
        p = audio / f"{fname}.flac"
        if not p.is_file():
            continue
        items.append(Item(str(p), BONAFIDE if key == "bonafide" else SPOOF,
                          speaker, system))
    return items


def balanced_subset(items: Sequence[Item], seed: int,
                    per_class: Optional[int] = None) -> List[Item]:
    """
    1:1 class balance, spoof spread evenly over attack systems.

    Chosen over class-weighted loss and over raw 8.84:1 training because it
    keeps *every* bona-fide example (the minority class carrying the domain
    information we care about) while giving the spoof side equal weight without
    inventing a loss-scaling hyperparameter. Rationale in
    docs/phase1_training.md §5.
    """
    rng = random.Random(seed)
    bona = [i for i in items if i.label == BONAFIDE]
    spoof = [i for i in items if i.label == SPOOF]
    n = per_class if per_class is not None else len(bona)
    n = min(n, len(bona))

    bona_sel = rng.sample(bona, n)

    by_sys: dict = collections.defaultdict(list)
    for s in spoof:
        by_sys[s.system_id].append(s)
    for k in by_sys:
        rng.shuffle(by_sys[k])
    keys = sorted(by_sys)
    spoof_sel: List[Item] = []
    i = 0
    while len(spoof_sel) < n and any(by_sys[k] for k in keys):
        k = keys[i % len(keys)]
        if by_sys[k]:
            spoof_sel.append(by_sys[k].pop())
        i += 1
    out = bona_sel + spoof_sel[:n]
    rng.shuffle(out)
    return out


def fit_length(audio: np.ndarray, nb_samp: int = NB_SAMP) -> np.ndarray:
    """Identical to AASISTDetector._fit_length — tile short, centre-crop long."""
    n = len(audio)
    if n == nb_samp:
        return audio
    if n < nb_samp:
        reps = int(nb_samp / max(1, n)) + 1
        return np.tile(audio, reps)[:nb_samp]
    start = (n - nb_samp) // 2
    return audio[start:start + nb_samp]


def read_audio(path: str, target_sr: int = SAMPLE_RATE) -> Optional[np.ndarray]:
    import soundfile as sf
    try:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
    except Exception:
        return None
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != target_sr:
        from scipy import signal as sps
        g = np.gcd(int(sr), int(target_sr))
        audio = sps.resample_poly(audio, target_sr // g, sr // g)
    return np.ascontiguousarray(audio, dtype=np.float32)


class ASVspoofWindows(Dataset):
    """One fixed-length window per utterance, matching inference exactly."""

    def __init__(self, items: Sequence[Item], augment=None, nb_samp: int = NB_SAMP):
        self.items = list(items)
        self.augment = augment
        self.nb_samp = nb_samp

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        it = self.items[idx]
        audio = read_audio(it.path)
        if audio is None:
            audio = np.zeros(self.nb_samp, dtype=np.float32)
        audio = fit_length(audio, self.nb_samp)
        if self.augment is not None:
            audio = self.augment(audio)
            audio = fit_length(np.asarray(audio, dtype=np.float32), self.nb_samp)
        return torch.from_numpy(np.ascontiguousarray(audio, dtype=np.float32)), it.label


def distribution(items: Sequence[Item]) -> dict:
    c = collections.Counter(i.label for i in items)
    return {"bonafide": c[BONAFIDE], "spoof": c[SPOOF], "total": len(items)}
