"""
Score calibration at inference time — loading and applying only.

Fitting lives in the evaluation harness (`evaluation/calibration/`), which is a
research tool. Production only ever *applies* a calibrator that was fitted
offline on a documented calibration split, so this module deliberately has no
fitting code and no dependency on the evaluation package.

A calibrator maps the model's raw decision score to a probability. It is
monotonic, so it never changes ranking — only the scale on which a score is
read. The raw score is always retained alongside.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

import numpy as np


@dataclass
class LoadedCalibrator:
    method: str
    version: str
    provenance: dict

    def predict(self, scores: Sequence[float]) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError


@dataclass
class PlattApplier(LoadedCalibrator):
    a: float = 1.0
    b: float = 0.0

    def predict(self, scores: Sequence[float]) -> np.ndarray:
        s = np.asarray(scores, dtype=np.float64).ravel()
        return (1.0 / (1.0 + np.exp(-(self.a * s + self.b)))).astype(float)


@dataclass
class IsotonicApplier(LoadedCalibrator):
    x: List[float] = None
    y: List[float] = None

    def predict(self, scores: Sequence[float]) -> np.ndarray:
        if not self.x:
            return np.asarray(scores, dtype=float).ravel()
        s = np.asarray(scores, dtype=np.float64).ravel()
        return np.interp(s, np.asarray(self.x), np.asarray(self.y),
                         left=self.y[0], right=self.y[-1]).astype(float)


def load_calibrator(path: str | Path) -> LoadedCalibrator:
    """Load a calibrator produced by the evaluation harness."""
    data = json.loads(Path(path).read_text())
    method = data.get("method")
    common = {
        "method": method,
        "version": data.get("version", "unknown"),
        "provenance": data.get("provenance", {}),
    }
    if method == "platt":
        return PlattApplier(a=float(data["a"]), b=float(data["b"]), **common)
    if method == "isotonic":
        return IsotonicApplier(x=list(data["x"]), y=list(data["y"]), **common)
    raise ValueError(f"unknown calibration method {method!r}")
