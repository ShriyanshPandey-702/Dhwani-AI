"""
Phase 1.8 Invariant Verification Utility.
========================================
Asserts that all frozen parameters, models, weights, thresholds, and geometry
remain bit-for-bit identical to the Phase 1.7 baseline before evaluation runs.
Fail-fast: Any violation raises InvariantViolationError.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[2]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(API_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

EXPECTED_INVARIANTS = {
    "aasist_checkpoint": "services/api/models/aasist/AASIST-L.pth",
    "aasist_sha256": "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a",
    "ecapa_model_source": "speechbrain/spkrec-ecapa-voxceleb",
    "aasist_nb_samp": 64600,
    "stream_window_samples": 64608,
    "stream_hop_samples": 16000,
    "stream_max_buffer_samples": 80608,
    "risk_weights": {
        "authenticity": 0.50,
        "identity": 0.25,
        "context": 0.25,
    },
    "policy_thresholds": {
        "low": 20,
        "suspicious": 40,
        "high": 65,
        "critical": 85,
    },
    "use_calibrated_score_for_fusion": False,
    "ml_pool_workers": 2,
    "max_pending_audio_chunks": 4,
}


class InvariantViolationError(RuntimeError):
    """Raised when any frozen invariant is violated."""


def verify_invariants(strict: bool = True) -> Dict[str, Any]:
    """
    Verify all frozen Phase 1.8 invariants against the live codebase.
    Returns audit dictionary if passed; raises InvariantViolationError if failed.
    """
    audit = {}

    # 1. AASIST-L Checkpoint and SHA-256
    ckpt_rel = EXPECTED_INVARIANTS["aasist_checkpoint"]
    ckpt_path = REPO_ROOT / ckpt_rel
    if not ckpt_path.is_file():
        raise InvariantViolationError(f"AASIST-L checkpoint missing at {ckpt_path}")

    with open(ckpt_path, "rb") as fh:
        actual_hash = hashlib.sha256(fh.read()).hexdigest()
    expected_hash = EXPECTED_INVARIANTS["aasist_sha256"]
    if actual_hash != expected_hash:
        raise InvariantViolationError(
            f"AASIST-L SHA-256 mismatch! Expected {expected_hash}, got {actual_hash}"
        )
    audit["aasist_sha256"] = {"status": "PASS", "value": actual_hash}

    # 2. AASIST NB_SAMP & fit_length
    from app.ml.authenticity.aasist import NB_SAMP, AASISTDetector
    if NB_SAMP != EXPECTED_INVARIANTS["aasist_nb_samp"]:
        raise InvariantViolationError(
            f"AASIST NB_SAMP mismatch! Expected {EXPECTED_INVARIANTS['aasist_nb_samp']}, got {NB_SAMP}"
        )
    audit["aasist_nb_samp"] = {"status": "PASS", "value": NB_SAMP}

    # Verify _fit_length center crop behavior
    import numpy as np
    dummy_input = np.arange(64608, dtype=np.float32)
    fitted = AASISTDetector._fit_length(dummy_input)
    if len(fitted) != 64600:
        raise InvariantViolationError(f"_fit_length output length != 64600: {len(fitted)}")
    # Center crop check: (64608 - 64600) // 2 = 4
    if fitted[0] != dummy_input[4] or fitted[-1] != dummy_input[64603]:
        raise InvariantViolationError("_fit_length center crop calculation mismatch")
    audit["aasist_fit_length"] = {"status": "PASS", "behavior": "center_crop_64608_to_64600"}

    # 3. StreamWindower Geometry
    from app.core.config import settings
    from app.ml.preprocessing.stream import StreamWindower
    windower = StreamWindower(
        window_ms=settings.ANALYSIS_WINDOW_MS,
        hop_ms=settings.ANALYSIS_HOP_MS,
    )
    if windower.window_samples != EXPECTED_INVARIANTS["stream_window_samples"]:
        raise InvariantViolationError(
            f"Window samples mismatch! Expected {EXPECTED_INVARIANTS['stream_window_samples']}, "
            f"got {windower.window_samples}"
        )
    if windower.hop_samples != EXPECTED_INVARIANTS["stream_hop_samples"]:
        raise InvariantViolationError(
            f"Hop samples mismatch! Expected {EXPECTED_INVARIANTS['stream_hop_samples']}, "
            f"got {windower.hop_samples}"
        )
    if windower._max_samples != EXPECTED_INVARIANTS["stream_max_buffer_samples"]:
        raise InvariantViolationError(
            f"Max buffer samples mismatch! Expected {EXPECTED_INVARIANTS['stream_max_buffer_samples']}, "
            f"got {windower._max_samples}"
        )
    audit["stream_windower"] = {
        "status": "PASS",
        "window_samples": windower.window_samples,
        "hop_samples": windower.hop_samples,
        "max_buffer": windower._max_samples,
    }

    # 4. ECAPA-TDNN Source
    from app.ml.identity.ecapa import HF_SOURCE
    if HF_SOURCE != EXPECTED_INVARIANTS["ecapa_model_source"]:
        raise InvariantViolationError(
            f"ECAPA HF_SOURCE mismatch! Expected {EXPECTED_INVARIANTS['ecapa_model_source']}, "
            f"got {HF_SOURCE}"
        )
    audit["ecapa_source"] = {"status": "PASS", "value": HF_SOURCE}

    # 5. Risk Weights
    from app.risk.engine import _DEFAULT_WEIGHTS
    for k, v in EXPECTED_INVARIANTS["risk_weights"].items():
        if _DEFAULT_WEIGHTS.get(k) != v:
            raise InvariantViolationError(
                f"Risk weight mismatch for {k}! Expected {v}, got {_DEFAULT_WEIGHTS.get(k)}"
            )
    audit["risk_weights"] = {"status": "PASS", "values": _DEFAULT_WEIGHTS}

    # 6. Policy Thresholds
    from app.risk.engine import _DEFAULT_THRESHOLDS
    for k, v in EXPECTED_INVARIANTS["policy_thresholds"].items():
        if _DEFAULT_THRESHOLDS.get(k) != v:
            raise InvariantViolationError(
                f"Policy threshold mismatch for {k}! Expected {v}, got {_DEFAULT_THRESHOLDS.get(k)}"
            )
    audit["policy_thresholds"] = {"status": "PASS", "values": _DEFAULT_THRESHOLDS}

    # 7. Calibration Flag
    if settings.USE_CALIBRATED_SCORE_FOR_FUSION != EXPECTED_INVARIANTS["use_calibrated_score_for_fusion"]:
        raise InvariantViolationError(
            f"USE_CALIBRATED_SCORE_FOR_FUSION mismatch! Expected "
            f"{EXPECTED_INVARIANTS['use_calibrated_score_for_fusion']}, got {settings.USE_CALIBRATED_SCORE_FOR_FUSION}"
        )
    audit["use_calibrated_score_for_fusion"] = {
        "status": "PASS",
        "value": settings.USE_CALIBRATED_SCORE_FOR_FUSION,
    }

    # 8. Concurrency Settings
    if settings.ML_POOL_WORKERS != EXPECTED_INVARIANTS["ml_pool_workers"]:
        raise InvariantViolationError(
            f"ML_POOL_WORKERS mismatch! Expected {EXPECTED_INVARIANTS['ml_pool_workers']}, "
            f"got {settings.ML_POOL_WORKERS}"
        )
    if settings.MAX_PENDING_AUDIO_CHUNKS != EXPECTED_INVARIANTS["max_pending_audio_chunks"]:
        raise InvariantViolationError(
            f"MAX_PENDING_AUDIO_CHUNKS mismatch! Expected "
            f"{EXPECTED_INVARIANTS['max_pending_audio_chunks']}, got {settings.MAX_PENDING_AUDIO_CHUNKS}"
        )
    audit["concurrency"] = {
        "status": "PASS",
        "ml_pool_workers": settings.ML_POOL_WORKERS,
        "max_pending_chunks": settings.MAX_PENDING_AUDIO_CHUNKS,
    }

    return audit


if __name__ == "__main__":
    try:
        results = verify_invariants()
        print("ALL FROZEN INVARIANTS VERIFIED SUCCESSFULLY (PASS):")
        for k, v in results.items():
            print(f"  • {k}: {v}")
    except InvariantViolationError as e:
        print(f"CRITICAL INVARIANT VIOLATION: {e}", file=sys.stderr)
        sys.exit(1)
