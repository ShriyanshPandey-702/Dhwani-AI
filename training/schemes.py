"""
Phase 1 freezing schemes.

The ONLY intended experimental variable is *which layers are trainable*.
Everything else (data, preprocessing, loss, optimiser family, seed, epochs,
batch strategy, metrics) is held fixed across A / B1 / B2 / C.

Two implementation details that are easy to get wrong and are handled here:

1. `conv_time` (the sinc front-end) has **zero trainable parameters** — the
   band-pass filters are computed in __init__ and are not nn.Parameters. So
   "freezing the front-end" is not a meaningful scheme and is not offered.

2. Freezing `requires_grad` is NOT enough for BatchNorm. A BN module in train()
   keeps updating `running_mean`/`running_var` regardless of requires_grad, so
   a "frozen" block would still drift. `apply_scheme` therefore also forces the
   BN modules inside frozen sub-trees into eval() on every epoch via
   `set_train_mode`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

import torch.nn as nn

SCHEMES = ("A", "B1", "B2", "C")


def _is_frozen_name(scheme: str) -> Callable[[str], bool]:
    """True when the parameter/module name belongs to the frozen sub-tree."""
    if scheme == "A":
        return lambda n: not n.startswith("out_layer")
    if scheme == "B1":
        return lambda n: n.startswith("encoder")
    if scheme == "B2":
        return lambda n: n.startswith("encoder.0") or n.startswith("encoder.1")
    if scheme == "C":
        return lambda n: False
    raise ValueError(f"unknown scheme {scheme!r}")


@dataclass
class SchemeInfo:
    scheme: str
    trainable_params: int
    total_params: int
    frozen_bn_modules: int
    trainable_tensor_names: List[str]

    def to_dict(self) -> Dict:
        return {
            "scheme": self.scheme,
            "trainable_params": self.trainable_params,
            "total_params": self.total_params,
            "trainable_fraction": round(self.trainable_params / self.total_params, 6),
            "frozen_batchnorm_modules": self.frozen_bn_modules,
            "n_trainable_tensors": len(self.trainable_tensor_names),
        }


def apply_scheme(model: nn.Module, scheme: str) -> SchemeInfo:
    """Set requires_grad per the scheme and report exactly what it produced."""
    frozen = _is_frozen_name(scheme)
    for name, p in model.named_parameters():
        p.requires_grad_(not frozen(name))

    frozen_bn = [n for n, m in model.named_modules()
                 if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d)) and frozen(n)]

    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    names = [n for n, p in model.named_parameters() if p.requires_grad]
    return SchemeInfo(scheme, trainable, total, len(frozen_bn), names)


def set_train_mode(model: nn.Module, scheme: str) -> None:
    """
    Put the model in train mode, then force frozen BatchNorm back to eval.

    Must be called at the start of every epoch: `model.train()` resets the whole
    tree, so the BN override has to be re-applied.
    """
    model.train()
    frozen = _is_frozen_name(scheme)
    for name, m in model.named_modules():
        if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d)) and frozen(name):
            m.eval()


def frozen_bn_running_stats(model: nn.Module, scheme: str) -> Dict[str, tuple]:
    """Snapshot frozen BN running stats so a test can prove they never move."""
    frozen = _is_frozen_name(scheme)
    out = {}
    for name, m in model.named_modules():
        if isinstance(m, (nn.BatchNorm1d, nn.BatchNorm2d)) and frozen(name):
            out[name] = (m.running_mean.detach().clone(),
                         m.running_var.detach().clone())
    return out
