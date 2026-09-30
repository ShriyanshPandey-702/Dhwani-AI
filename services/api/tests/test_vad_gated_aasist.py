"""
Test Suite: VAD-Gated AASIST Verification (Demo Stabilization Phase)

Verifies:
1. Silence → AASIST not called
2. Room-noise / non-speech → AASIST not called
3. Insufficient VAD speech (< 250 ms) → AASIST not called
4. Sufficient VAD speech (>= 250 ms) → AASIST called
5. Skipped AASIST window does not increment authenticity anomaly streak
6. Existing AASIST result is preserved unchanged when speech is sufficient
7. Existing risk engine weights, caps, and thresholds remain exactly unchanged
8. No NaN or Infinity in any risk outputs or contributions
"""

import math
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from app.websocket.manager import SessionState
from app.websocket.pipeline import (
    analyze_window,
    _get_vad_speech_duration_ms,
    _speech_credible,
    authenticity_detector,
)
from app.ml.preprocessing.audio import TARGET_SR, measure_quality, AudioQuality, GOOD, POOR
from app.risk.engine import (
    compute_risk,
    EvidenceBundle,
    _DEFAULT_WEIGHTS,
    _DEFAULT_THRESHOLDS,
    _DEFAULT_UNCORROBORATED_CAP,
    _DEFAULT_PERSISTENT_AUTH_CAP,
)


def _make_pcm16(samples: np.ndarray) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


def _make_state(session_id: str = "vad-test") -> SessionState:
    return SessionState(
        session_id=session_id,
        user_id="test-user",
        policy_config={},
        pipeline_mode="real_ml",
    )


class TestVADGatedAASIST:
    """Requirement 7 Tests A through H."""

    def test_a_silence_aasist_not_called(self):
        """A. Silence → AASIST not called."""
        state = _make_state("test-silence")
        silence_pcm = np.zeros(TARGET_SR * 2, dtype=np.int16).tobytes()

        with patch.object(authenticity_detector, "analyze") as mock_analyze:
            events = analyze_window(state, silence_pcm, pipeline_mode="real_ml")
            assert mock_analyze.call_count == 0
            assert state.consecutive_authenticity_anomalies == 0

    def test_b_room_noise_nonspeech_aasist_not_called(self):
        """B. Room noise (energy > 1e-5 but 0 VAD speech) → AASIST not called."""
        state = _make_state("test-room-noise")
        # Generates low-amplitude acoustic noise (RMS ~0.005, level ~ -46 dBFS > 1e-5)
        rng = np.random.default_rng(123)
        noise = (rng.normal(0, 0.005, 64608)).astype(np.float32)
        noise_pcm = _make_pcm16(noise)

        # Mock VAD returning 0 timestamps (non-speech)
        with patch("app.websocket.pipeline.get_speech_timestamps", return_value=[]), \
             patch("app.websocket.pipeline.VadOptions", MagicMock()), \
             patch.object(authenticity_detector, "analyze") as mock_analyze:

            events = analyze_window(state, noise_pcm, pipeline_mode="real_ml")
            assert mock_analyze.call_count == 0
            assert state.consecutive_authenticity_anomalies == 0
            assert state.last_authenticity is not None
            assert state.last_authenticity["status"] == "insufficient_evidence"
            assert state.last_authenticity["spoof_probability"] is None
            assert state.last_authenticity["reason"] == "insufficient_speech"

    def test_c_insufficient_vad_speech_aasist_not_called(self):
        """C. Insufficient VAD speech (< 250 ms) → AASIST not called."""
        state = _make_state("test-short-vad")
        audio = np.random.normal(0, 0.02, 64608).astype(np.float32)
        pcm = _make_pcm16(audio)

        # 100 ms speech timestamps: [start: 0, end: 1600] = 1600 samples = 100 ms < 250 ms
        short_ts = [{"start": 0, "end": 1600}]

        with patch("app.websocket.pipeline.get_speech_timestamps", return_value=short_ts), \
             patch("app.websocket.pipeline.VadOptions", MagicMock()), \
             patch.object(authenticity_detector, "analyze") as mock_analyze:

            events = analyze_window(state, pcm, pipeline_mode="real_ml")
            assert mock_analyze.call_count == 0
            assert state.consecutive_authenticity_anomalies == 0
            assert state.last_authenticity["status"] == "insufficient_evidence"
            assert state.last_authenticity["spoof_probability"] is None
            assert state.last_authenticity["vad_speech_ms"] == 100

    def test_d_sufficient_vad_speech_aasist_called(self):
        """D. Sufficient VAD speech (>= 250 ms) → AASIST called."""
        state = _make_state("test-sufficient-vad")
        audio = np.random.normal(0, 0.05, 64608).astype(np.float32)
        pcm = _make_pcm16(audio)

        # 500 ms speech timestamps: 8000 samples at 16 kHz = 500 ms >= 250 ms
        sufficient_ts = [{"start": 0, "end": 8000}]

        mock_auth_result = MagicMock()
        mock_auth_result.spoof_probability = 0.85
        mock_auth_result.confidence = 0.90
        mock_auth_result.to_dict.return_value = {
            "spoof_probability": 0.85,
            "confidence": 0.90,
            "score": 85,
            "is_mock": False,
        }

        with patch("app.websocket.pipeline.get_speech_timestamps", return_value=sufficient_ts), \
             patch("app.websocket.pipeline.VadOptions", MagicMock()), \
             patch.object(authenticity_detector, "analyze", return_value=mock_auth_result) as mock_analyze:

            events = analyze_window(state, pcm, pipeline_mode="real_ml")
            assert mock_analyze.call_count == 1
            assert state.last_authenticity is not None
            assert state.last_authenticity["spoof_probability"] == 0.85
            assert state.consecutive_authenticity_anomalies == 1

    def test_e_skipped_aasist_window_streak_stays_zero(self):
        """E. Skipped AASIST window does not increment authenticity anomaly streak."""
        state = _make_state("test-streak-stays-zero")
        audio = np.random.normal(0, 0.01, 64608).astype(np.float32)
        pcm = _make_pcm16(audio)

        with patch("app.websocket.pipeline.get_speech_timestamps", return_value=[]), \
             patch("app.websocket.pipeline.VadOptions", MagicMock()):

            # Feed 5 consecutive non-speech windows
            for _ in range(5):
                analyze_window(state, pcm, pipeline_mode="real_ml")
                assert state.consecutive_authenticity_anomalies == 0

    def test_f_existing_aasist_result_preserved_when_speech_sufficient(self):
        """F. Existing AASIST result is preserved unchanged when speech is sufficient."""
        state = _make_state("test-real-preserved")
        audio = np.random.normal(0, 0.05, 64608).astype(np.float32)
        pcm = _make_pcm16(audio)

        sufficient_ts = [{"start": 0, "end": 16000}]  # 1000 ms

        mock_auth_result = MagicMock()
        mock_auth_result.spoof_probability = 0.9234
        mock_auth_result.confidence = 0.95
        mock_auth_result.to_dict.return_value = {
            "spoof_probability": 0.9234,
            "confidence": 0.95,
            "score": 92,
            "is_mock": False,
        }

        with patch("app.websocket.pipeline.get_speech_timestamps", return_value=sufficient_ts), \
             patch("app.websocket.pipeline.VadOptions", MagicMock()), \
             patch.object(authenticity_detector, "analyze", return_value=mock_auth_result):

            events = analyze_window(state, pcm, pipeline_mode="real_ml")
            assert state.last_authenticity["spoof_probability"] == 0.9234
            assert state.last_authenticity["confidence"] == 0.95

    def test_g_existing_risk_engine_constants_unchanged(self):
        """G. Existing risk engine weights/caps/thresholds remain unchanged."""
        assert _DEFAULT_WEIGHTS["authenticity"] == 0.50
        assert _DEFAULT_WEIGHTS["identity"] == 0.25
        assert _DEFAULT_WEIGHTS["context"] == 0.25

        assert _DEFAULT_UNCORROBORATED_CAP == 38.0
        assert _DEFAULT_PERSISTENT_AUTH_CAP == 50.0

        assert _DEFAULT_THRESHOLDS["low"] == 20
        assert _DEFAULT_THRESHOLDS["suspicious"] == 40
        assert _DEFAULT_THRESHOLDS["high"] == 65
        assert _DEFAULT_THRESHOLDS["critical"] == 85

    def test_h_no_nan_or_infinity(self):
        """H. Verify no NaN or Infinity in risk computation under partial/skipped authenticity."""
        bundle_empty = EvidenceBundle(
            authenticity=None,
            authenticity_confidence=0.0,
            identity_similarity=None,
            identity_confidence=0.0,
            context_risk=None,
            context_confidence=0.0,
        )
        res = compute_risk(bundle_empty)
        assert not math.isnan(res.score)
        assert not math.isinf(res.score)
        assert not math.isnan(res.evidence_confidence)
        for k, v in res.contributions.items():
            assert not math.isnan(v)
            assert not math.isinf(v)

        bundle_skipped_auth = EvidenceBundle(
            authenticity=None,
            authenticity_confidence=0.0,
            identity_similarity=0.9,
            identity_confidence=0.8,
            context_risk=0.1,
            context_confidence=0.7,
        )
        res2 = compute_risk(bundle_skipped_auth)
        assert not math.isnan(res2.score)
        assert not math.isinf(res2.score)
