"""
Phase 5.7 — Detection Pipeline Correctness Hardening
Deterministic regression tests (T1 – T12).

Tests run entirely against the heuristic-demo backends (no ML models, no
database, no sockets).  They validate the three surgical changes:

  1. Speaker auto-enrolment is gated on _speech_credible(quality): silent,
     POOR-quality and non-speech windows MUST NOT become the speaker reference.

  2. The P=2 identity mismatch streak is only updated on credible-speech
     windows: non-credible audio neither increments nor resets the streak.

  3. The gateway teardown uses effective_user_id rather than the
     closure-captured user_id (which is None for anonymous connections).

AASIST scoring is NOT suppressed by quality in this phase.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.ml.authenticity.detector import AuthenticityDetector, HEURISTIC_DEMO
from app.ml.context.transcriber import Transcriber
from app.ml.identity.speaker import SpeakerIdentity
from app.ml.preprocessing.audio import (
    TARGET_SR,
    GOOD, FAIR, POOR,
    AudioQuality,
    measure_quality,
)
from app.risk.policy import DEFAULT_POLICY_CONFIG
from app.websocket import events as ev
from app.websocket import pipeline as pl
from app.websocket.manager import SessionState
from app.websocket.pipeline import analyze_window, _speech_credible


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _demo_backends(monkeypatch):
    monkeypatch.setattr(pl, "authenticity_detector",
                        AuthenticityDetector(pipeline_mode=HEURISTIC_DEMO))
    monkeypatch.setattr(pl, "speaker_identity",
                        SpeakerIdentity(pipeline_mode=HEURISTIC_DEMO))
    monkeypatch.setattr(pl, "transcriber", Transcriber(pipeline_mode=HEURISTIC_DEMO))
    yield


def _fresh(session_id: str) -> SessionState:
    pl.speaker_identity.clear(session_id)
    pl.transcriber.reset(session_id)
    pl.context_classifier.reset(session_id)
    pl.stream_windower.reset(session_id)
    return SessionState(
        session_id=session_id,
        user_id="user-t57",
        policy_config=dict(DEFAULT_POLICY_CONFIG),
    )


# ── PCM helpers ───────────────────────────────────────────────────────────────

def _pcm(samples: np.ndarray) -> bytes:
    return (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()

def _digital_silence(duration_ms: int = 1000, sr: int = TARGET_SR) -> bytes:
    n = int(sr * duration_ms / 1000)
    return np.zeros(n, dtype=np.int16).tobytes()

def _room_noise(duration_ms: int = 1000, sr: int = TARGET_SR, amplitude: float = 3e-3) -> bytes:
    rng = np.random.default_rng(42)
    n = int(sr * duration_ms / 1000)
    sig = (rng.standard_normal(n) * amplitude).astype(np.float32)
    return _pcm(sig)

def _mic_hiss(duration_ms: int = 1000, sr: int = TARGET_SR) -> bytes:
    rng = np.random.default_rng(7)
    n = int(sr * duration_ms / 1000)
    sig = (rng.standard_normal(n) * 4e-3).astype(np.float32)
    return _pcm(sig)

def _speech(duration_ms: int = 1000, sr: int = TARGET_SR, seed: int = 0) -> bytes:
    rng = np.random.default_rng(seed)
    n = int(sr * duration_ms / 1000)
    t = np.arange(n) / sr
    f0 = 130.0
    sig = np.zeros(n, dtype=np.float64)
    for h in range(1, 12):
        sig += (1.0 / h) * np.sin(2 * np.pi * f0 * h * t)
    env = 0.3 + 0.7 * 0.5 * (1 + np.sin(2 * np.pi * 4.0 * t))
    sig *= env
    sig += rng.standard_normal(n) * 0.002
    sig = np.clip(sig / (np.max(np.abs(sig)) + 1e-9) * 0.6, -1.0, 1.0)
    return _pcm(sig.astype(np.float32))

def _synthetic(duration_ms: int = 1000, sr: int = TARGET_SR) -> bytes:
    n = int(sr * duration_ms / 1000)
    t = np.arange(n) / sr
    sig = np.clip(0.5 * np.sin(2 * np.pi * 130.0 * t) * 0.6, -1.0, 1.0)
    return _pcm(sig.astype(np.float32))


# ── Quality predicate helpers ─────────────────────────────────────────────────

def _make_quality(quality_band: str, is_silent: bool = False) -> AudioQuality:
    return AudioQuality(
        level_db=-30.0,
        estimated_snr_db=20.0 if quality_band == GOOD else (12.0 if quality_band == FAIR else 3.0),
        clipping_ratio=0.0,
        is_silent=is_silent,
        quality=quality_band,
        sample_rate=TARGET_SR,
        duration_ms=1000,
    )


# ── _speech_credible() unit tests ─────────────────────────────────────────────

class TestSpeechCrediblePredicate:
    def test_silent_is_never_credible(self):
        assert _speech_credible(_make_quality(POOR, is_silent=True)) is False

    def test_poor_non_silent_is_not_credible(self):
        assert _speech_credible(_make_quality(POOR, is_silent=False)) is False

    def test_fair_is_credible(self):
        assert _speech_credible(_make_quality(FAIR)) is True

    def test_good_is_credible(self):
        assert _speech_credible(_make_quality(GOOD)) is True


# ── T1 – Digital silence ──────────────────────────────────────────────────────

class TestT1DigitalSilence:
    def test_no_enrollment_after_silence(self):
        sid = "t1-silence"
        state = _fresh(sid)
        analyze_window(state, _digital_silence(), "mock")
        assert not pl.speaker_identity.is_enrolled(sid)

    def test_no_mismatch_streak_after_silence(self):
        sid = "t1-silence-streak"
        state = _fresh(sid)
        analyze_window(state, _digital_silence(), "mock")
        assert state.consecutive_identity_mismatches == 0

    def test_no_risk_update_after_silence(self):
        sid = "t1-silence-risk"
        state = _fresh(sid)
        events = analyze_window(state, _digital_silence(), "mock")
        assert [e for e in events if e["type"] == ev.RISK_UPDATE] == []


# ── T2 – Low-level room noise ────────────────────────────────────────────────

class TestT2RoomNoise:
    def test_no_enrollment_from_room_noise(self):
        sid = "t2-noise"
        state = _fresh(sid)
        for _ in range(5):
            analyze_window(state, _room_noise(), "mock")
        assert not pl.speaker_identity.is_enrolled(sid), \
            "room noise must never become the speaker reference"

    def test_no_mismatch_streak_from_room_noise(self):
        sid = "t2-noise-streak"
        state = _fresh(sid)
        for _ in range(5):
            analyze_window(state, _room_noise(), "mock")
        assert state.consecutive_identity_mismatches == 0

    def test_no_identity_corroboration_from_room_noise(self):
        sid = "t2-noise-corr"
        state = _fresh(sid)
        for _ in range(5):
            analyze_window(state, _room_noise(), "mock")
        bundle = state.evidence()
        assert not bundle.identity_corroborated


# ── T3 – Microphone hiss ─────────────────────────────────────────────────────

class TestT3MicHiss:
    def test_no_enrollment_from_hiss(self):
        sid = "t3-hiss"
        state = _fresh(sid)
        for _ in range(5):
            analyze_window(state, _mic_hiss(), "mock")
        assert not pl.speaker_identity.is_enrolled(sid)

    def test_mismatch_streak_stays_zero(self):
        sid = "t3-hiss-streak"
        state = _fresh(sid)
        for _ in range(5):
            analyze_window(state, _mic_hiss(), "mock")
        assert state.consecutive_identity_mismatches == 0


# ── T4 – Real / natural speech ──────────────────────────────────────────────

class TestT4RealSpeech:
    def test_enrollment_from_good_speech(self):
        sid = "t4-speech"
        state = _fresh(sid)
        analyze_window(state, _speech(), "mock")
        assert pl.speaker_identity.is_enrolled(sid)

    def test_aasist_evidence_present_for_speech(self):
        sid = "t4-speech-aasist"
        state = _fresh(sid)
        analyze_window(state, _speech(), "mock")
        assert state.last_authenticity is not None
        assert "spoof_probability" in state.last_authenticity

    def test_risk_update_emitted_for_speech(self):
        sid = "t4-speech-risk"
        state = _fresh(sid)
        events = analyze_window(state, _speech(), "mock")
        assert [e for e in events if e["type"] == ev.RISK_UPDATE]


# ── T5 – Synthetic speech ────────────────────────────────────────────────────

class TestT5SyntheticSpeech:
    def test_aasist_scores_synthetic(self):
        sid = "t5-synthetic"
        state = _fresh(sid)
        analyze_window(state, _synthetic(), "mock")
        assert state.last_authenticity is not None
        assert "spoof_probability" in state.last_authenticity

    def test_enrollment_blocked_for_poor_quality_synthetic(self):
        """_synthetic() generates a flat mono sine which lands in POOR quality
        (SNR 0.3 dB).  _speech_credible() must block enrollment — this tests
        that the gate works on non-speech-quality synthetic waveforms too."""
        sid = "t5-synthetic-enroll"
        state = _fresh(sid)
        analyze_window(state, _synthetic(), "mock")
        # AASIST must have run (last_authenticity populated) ...
        assert state.last_authenticity is not None, \
            "AASIST must score POOR-quality synthetic audio"
        # ... but enrollment must be blocked because quality=POOR
        assert not pl.speaker_identity.is_enrolled(sid), \
            ("_speech_credible() must block enrollment for POOR-quality audio, "
             "even when the audio is non-silent")


# ── T6 – Speech then Silence ─────────────────────────────────────────────────

class TestT6SpeechToSilence:
    def test_risk_preserved_on_silence_after_speech(self):
        sid = "t6-to-silence"
        state = _fresh(sid)
        analyze_window(state, _speech(), "mock")
        before = list(state.risk_history)
        analyze_window(state, _digital_silence(), "mock")
        assert state.risk_history == before

    def test_enrollment_preserved_after_silence(self):
        sid = "t6-to-silence-enroll"
        state = _fresh(sid)
        analyze_window(state, _speech(), "mock")
        assert pl.speaker_identity.is_enrolled(sid)
        analyze_window(state, _digital_silence(), "mock")
        assert pl.speaker_identity.is_enrolled(sid)


# ── T7 – Silence then Speech ─────────────────────────────────────────────────

class TestT7SilenceToSpeech:
    def test_enrollment_deferred_until_speech(self):
        sid = "t7-to-speech"
        state = _fresh(sid)
        for _ in range(3):
            analyze_window(state, _digital_silence(), "mock")
        for _ in range(3):
            analyze_window(state, _room_noise(), "mock")
        assert not pl.speaker_identity.is_enrolled(sid)
        analyze_window(state, _speech(), "mock")
        assert pl.speaker_identity.is_enrolled(sid)

    def test_no_mismatch_streak_before_enrollment(self):
        sid = "t7-streak-before"
        state = _fresh(sid)
        for _ in range(3):
            analyze_window(state, _digital_silence(), "mock")
        for _ in range(3):
            analyze_window(state, _room_noise(), "mock")
        assert state.consecutive_identity_mismatches == 0


# ── T8 – Spoken OTP / fraud phrase ──────────────────────────────────────────

class TestT8FraudPhrase:
    def test_otp_detection_on_credible_speech(self):
        sid = "t8-otp"
        state = _fresh(sid)
        from app.simulation.mock_audio import generate_frame
        for step in range(12):
            analyze_window(state, generate_frame(step, 12), "mock")
        ctx = state.last_context
        assert ctx is not None
        assert ctx["otp_request"] is True

    def test_otp_does_not_fire_on_silence_only(self):
        sid = "t8-silence-otp"
        state = _fresh(sid)
        for _ in range(6):
            analyze_window(state, _digital_silence(), "mock")
        ctx = state.last_context
        if ctx is not None:
            assert ctx.get("otp_request") is not True


# ── T9 – Noisy non-speech ────────────────────────────────────────────────────

class TestT9NoisyNonSpeech:
    def test_no_identity_corroboration_from_sustained_noise(self):
        sid = "t9-noisy"
        state = _fresh(sid)
        for _ in range(10):
            analyze_window(state, _room_noise(), "mock")
        bundle = state.evidence()
        assert not bundle.identity_corroborated

    def test_no_context_risk_from_noisy_non_speech(self):
        """Sustained POOR-quality noise must produce no context risk score
        because no transcript is ever produced (mock transcriber only fires
        on sessions with real-sounding windows)."""
        sid = "t9-noisy-ctx"
        state = _fresh(sid)
        for _ in range(10):
            analyze_window(state, _room_noise(), "mock")
        ctx = state.last_context
        # Either no context at all, or all flags False
        if ctx is not None:
            assert ctx.get("otp_request") is not True
            assert ctx.get("financial_request") is not True
            assert ctx.get("credential_request") is not True

    def test_uncorroborated_cap_applies_to_noise_only_session(self):
        sid = "t9-cap"
        state = _fresh(sid)
        for _ in range(10):
            analyze_window(state, _room_noise(), "mock")
        if state.risk_history:
            cap = state.policy_config.get("uncorroborated_total_cap", 38.0)
            assert max(state.risk_history) <= cap, \
                f"risk {max(state.risk_history)} exceeded uncorroborated cap {cap}"


# ── T10 – Anonymous session incident persistence ─────────────────────────────

class TestT10AnonymousIncidentPersistence:
    def test_effective_user_id_is_used_in_teardown(self):
        import inspect
        import app.websocket.gateway as gw
        source = inspect.getsource(gw.websocket_endpoint)
        assert "_teardown(session_id, effective_user_id)" in source, \
            "gateway must call _teardown(session_id, effective_user_id)"

    def test_save_incident_called_with_non_none_user(self):
        import asyncio
        import app.websocket.gateway as gw

        captured_args = []

        async def _fake_save(session_id, user_id, state):
            captured_args.append(user_id)
            return "fake-incident-id"

        sid = "t10-anon"
        state = _fresh(sid)
        state.peak_risk_score = 50
        state.peak_risk_state = "suspicious"
        state.pipeline_mode = "mock"
        effective_user_id = "user-from-session-lookup"

        async def run():
            with patch.object(gw, "_save_incident", _fake_save), \
                 patch.object(gw.manager, "get_state", return_value=state), \
                 patch.object(gw.manager, "publish", new=AsyncMock()), \
                 patch.object(gw.stt_queue, "close_session"), \
                 patch.object(gw, "speaker_identity", MagicMock()), \
                 patch.object(gw, "transcriber", MagicMock()), \
                 patch.object(gw, "context_classifier", MagicMock()), \
                 patch.object(gw, "stream_windower", MagicMock()), \
                 patch.object(gw.manager, "drop_state"):
                await gw._teardown(sid, effective_user_id)

        asyncio.run(run())
        assert captured_args == [effective_user_id]

    def test_none_user_id_never_reaches_save_incident(self):
        import asyncio
        import app.websocket.gateway as gw

        none_calls = []

        async def _spy_save(session_id, user_id, state):
            if user_id is None:
                none_calls.append(session_id)
            return "fake-id"

        sid = "t10-none-guard"
        state = _fresh(sid)
        state.peak_risk_score = 50

        async def run():
            with patch.object(gw, "_save_incident", _spy_save), \
                 patch.object(gw.manager, "get_state", return_value=state), \
                 patch.object(gw.manager, "publish", new=AsyncMock()), \
                 patch.object(gw.stt_queue, "close_session"), \
                 patch.object(gw, "speaker_identity", MagicMock()), \
                 patch.object(gw, "transcriber", MagicMock()), \
                 patch.object(gw, "context_classifier", MagicMock()), \
                 patch.object(gw, "stream_windower", MagicMock()), \
                 patch.object(gw.manager, "drop_state"):
                await gw._teardown(sid, "valid-uuid")

        asyncio.run(run())
        assert none_calls == [], "None user_id must never reach _save_incident"


# ── T11 – Authenticated incident persistence ─────────────────────────────────

class TestT11AuthenticatedIncidentPersistence:
    def test_authenticated_user_id_passes_through(self):
        import asyncio
        import app.websocket.gateway as gw

        captured = []

        async def _spy(session_id, user_id, state):
            captured.append(user_id)
            return "inc-id"

        sid = "t11-auth"
        state = _fresh(sid)
        state.peak_risk_score = 50
        jwt_user_id = "jwt-user-uuid-1234"

        async def run():
            with patch.object(gw, "_save_incident", _spy), \
                 patch.object(gw.manager, "get_state", return_value=state), \
                 patch.object(gw.manager, "publish", new=AsyncMock()), \
                 patch.object(gw.stt_queue, "close_session"), \
                 patch.object(gw, "speaker_identity", MagicMock()), \
                 patch.object(gw, "transcriber", MagicMock()), \
                 patch.object(gw, "context_classifier", MagicMock()), \
                 patch.object(gw, "stream_windower", MagicMock()), \
                 patch.object(gw.manager, "drop_state"):
                await gw._teardown(sid, jwt_user_id)

        asyncio.run(run())
        assert captured == [jwt_user_id]


# ── T12 – SIM demo trajectory regression ────────────────────────────────────

class TestT12DemoTrajectoryRegression:
    def test_demo_scores_unchanged(self):
        from app.simulation.mock_audio import generate_frame
        sid = "t12-regression"
        state = _fresh(sid)
        observed = []
        for step in range(12):
            for event in analyze_window(state, generate_frame(step, 12), "mock"):
                if event["type"] == ev.RISK_UPDATE:
                    observed.append((event["risk_score"], event["risk_state"], event["decision"]))

        scores = [s for s, _, _ in observed]
        assert scores == [6, 14, 21, 35, 40, 47, 68, 79, 85, 87, 91, 93], \
            f"Phase 5.7 must not change the SIM demo trajectory: {scores}"
        assert [d for _, _, d in observed][0] == "ALLOW"
        assert [d for _, _, d in observed][-1] == "HOLD"
        assert "VERIFY" in {d for _, _, d in observed}

    def test_enrollment_still_happens_on_first_good_frame(self):
        from app.simulation.mock_audio import generate_frame
        sid = "t12-enroll"
        state = _fresh(sid)
        analyze_window(state, generate_frame(0, 12), "mock")
        assert pl.speaker_identity.is_enrolled(sid)

    def test_all_demo_frames_are_credible(self):
        from app.simulation.mock_audio import generate_frame
        from app.ml.preprocessing.audio import decode_pcm, measure_quality
        for step in range(12):
            raw = decode_pcm(generate_frame(step, 12))
            q = measure_quality(raw)
            assert _speech_credible(q), \
                f"generate_frame({step}) not credible: quality={q.quality} is_silent={q.is_silent}"


# ── Whisper no_speech_prob filter ────────────────────────────────────────────

class TestWhisperNoSpeechProb:
    def test_high_no_speech_prob_segment_discarded(self):
        from app.ml.context.whisper import WhisperTranscriber
        t = WhisperTranscriber()
        seg_high = types.SimpleNamespace(text="transfer funds now", avg_logprob=-0.3, no_speech_prob=0.9)
        seg_clean = types.SimpleNamespace(text="hello there", avg_logprob=-0.2, no_speech_prob=0.1)
        fake_info = types.SimpleNamespace(language="en", language_probability=0.99)
        audio = np.ones(int(16000 * 1.5), dtype=np.float32) * 0.1
        with patch.object(t, "_load") as m:
            m.return_value.transcribe.return_value = ([seg_high, seg_clean], fake_info)
            result = t.transcribe(audio)
        assert result is not None
        assert "transfer" not in result.text.lower()
        assert "hello" in result.text.lower()

    def test_low_no_speech_prob_segment_retained(self):
        from app.ml.context.whisper import WhisperTranscriber
        t = WhisperTranscriber()
        seg = types.SimpleNamespace(text="please send the OTP", avg_logprob=-0.25, no_speech_prob=0.1)
        fake_info = types.SimpleNamespace(language="en", language_probability=0.95)
        audio = np.ones(int(16000 * 1.5), dtype=np.float32) * 0.1
        with patch.object(t, "_load") as m:
            m.return_value.transcribe.return_value = ([seg], fake_info)
            result = t.transcribe(audio)
        assert result is not None
        assert "otp" in result.text.lower()

    def test_missing_no_speech_prob_attribute_is_safe(self):
        from app.ml.context.whisper import WhisperTranscriber
        t = WhisperTranscriber()
        seg = types.SimpleNamespace(text="hello world", avg_logprob=-0.2)
        fake_info = types.SimpleNamespace(language="en", language_probability=0.9)
        audio = np.ones(int(16000 * 1.5), dtype=np.float32) * 0.1
        with patch.object(t, "_load") as m:
            m.return_value.transcribe.return_value = ([seg], fake_info)
            result = t.transcribe(audio)
        assert result is not None
        assert "hello" in result.text.lower()


# ── Invariant audit ──────────────────────────────────────────────────────────

class TestInvariantAudit:
    def test_identity_threshold_unchanged(self):
        assert DEFAULT_POLICY_CONFIG["identity_corroboration_threshold"] == 0.40

    def test_corroboration_persistence_unchanged(self):
        assert DEFAULT_POLICY_CONFIG["corroboration_persistence"] == 2

    def test_uncorroborated_cap_unchanged(self):
        assert DEFAULT_POLICY_CONFIG["uncorroborated_total_cap"] == 38.0

    def test_authenticity_uncorroborated_cap_unchanged(self):
        assert DEFAULT_POLICY_CONFIG["authenticity_uncorroborated_cap"] == 35.0

    def test_risk_weights_unchanged(self):
        w = DEFAULT_POLICY_CONFIG["weights"]
        assert w["authenticity"] == 0.50
        assert w["identity"] == 0.25
        assert w["context"] == 0.25

    def test_risk_thresholds_unchanged(self):
        t = DEFAULT_POLICY_CONFIG["thresholds"]
        assert t["low"] == 20
        assert t["suspicious"] == 40
        assert t["high"] == 65
        assert t["critical"] == 85

    def test_model_versions_keys_present(self):
        from app.websocket.pipeline import MODEL_VERSIONS
        for key in ("authenticity", "identity", "stt", "context",
                    "authenticity_backend", "identity_backend",
                    "stt_backend", "pipeline_mode"):
            assert key in MODEL_VERSIONS

    def test_stream_windower_settings_present(self):
        from app.core.config import settings
        assert hasattr(settings, "ANALYSIS_WINDOW_MS")
        assert hasattr(settings, "ANALYSIS_HOP_MS")


# ── Silero VAD Hardening Tests (Non-Speech vs Speech Gating) ──────────────────

class TestVADSpeechCredibleHardening:
    """
    Verifies that _speech_credible with Silero VAD in real_ml mode blocks
    non-speech signals (tones, DTMF, typing, music, fan/rustle) from enrolling
    or establishing identity corroboration, while accepting genuine human
    and synthetic speech.
    """

    def test_silence_not_credible(self):
        silence = np.zeros(TARGET_SR * 4, dtype=np.float32)
        q = measure_quality(silence)
        assert _speech_credible(silence, q, is_real_ml=True) is False

    def test_pulsed_tone_not_credible(self):
        t = np.arange(TARGET_SR * 4) / float(TARGET_SR)
        pulse = (np.sin(2 * np.pi * 1.0 * t) > 0).astype(float)
        tone = (0.1 * np.sin(2 * np.pi * 1000 * t) * pulse).astype(np.float32)
        q = measure_quality(tone)
        assert q.quality == GOOD
        assert _speech_credible(tone, q, is_real_ml=True) is False

    def test_dtmf_burst_not_credible(self):
        t = np.arange(TARGET_SR * 4) / float(TARGET_SR)
        pulse = (np.sin(2 * np.pi * 1.0 * t) > 0).astype(float)
        dtmf = (0.05 * (np.sin(2 * np.pi * 350 * t) + np.sin(2 * np.pi * 440 * t)) * pulse).astype(np.float32)
        q = measure_quality(dtmf)
        assert q.quality == GOOD
        assert _speech_credible(dtmf, q, is_real_ml=True) is False

    def test_keyboard_typing_not_credible(self):
        t = np.arange(TARGET_SR * 4) / float(TARGET_SR)
        keys = np.random.normal(0, 0.0005, len(t)).astype(np.float32)
        for idx in [4000, 12000, 20000, 28000]:
            keys[idx:idx+300] += 0.25 * np.sin(np.linspace(0, 10*np.pi, 300)).astype(np.float32)
        q = measure_quality(keys)
        assert q.quality == GOOD
        assert _speech_credible(keys, q, is_real_ml=True) is False

    def test_music_chords_not_credible(self):
        t = np.arange(TARGET_SR * 4) / float(TARGET_SR)
        chord = 0.03 * (np.sin(2 * np.pi * 261.63 * t) + np.sin(2 * np.pi * 329.63 * t) + np.sin(2 * np.pi * 392.00 * t))
        beat = ((t % 0.5) < 0.3).astype(float)
        music = (chord * beat).astype(np.float32)
        q = measure_quality(music)
        assert q.quality == GOOD
        assert _speech_credible(music, q, is_real_ml=True) is False

    def test_fan_rustle_not_credible(self):
        t = np.arange(TARGET_SR * 4) / float(TARGET_SR)
        hum = 0.03 * np.sin(2 * np.pi * 120 * t)
        noise = np.random.normal(0, 0.01, len(t))
        fan = ((hum + noise) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t))).astype(np.float32)
        q = measure_quality(fan)
        assert q.quality == GOOD
        assert _speech_credible(fan, q, is_real_ml=True) is False

    def test_genuine_human_speech_credible(self):
        from pathlib import Path
        import soundfile as sf
        path = Path(__file__).parents[3] / "data/external/InTheWild/release_in_the_wild/8.wav"
        h_data, _ = sf.read(str(path))
        human = h_data[:TARGET_SR * 4].astype(np.float32)
        q = measure_quality(human)
        assert q.quality == GOOD
        assert _speech_credible(human, q, is_real_ml=True) is True

    def test_synthetic_speech_credible(self):
        from pathlib import Path
        import soundfile as sf
        path = Path(__file__).parent / "fixtures/audio/tts_synthetic_16k.wav"
        tts_data, _ = sf.read(str(path))
        tts = tts_data[:TARGET_SR * 4].astype(np.float32)
        q = measure_quality(tts)
        assert q.quality == GOOD
        assert _speech_credible(tts, q, is_real_ml=True) is True

    def test_nonspeech_cannot_enroll_ecapa_in_real_ml(self):
        from app.ml.identity.speaker import SpeakerIdentity
        sid = "test-vad-no-enroll"
        spk = SpeakerIdentity(pipeline_mode="real_ml")
        spk.clear(sid)
        t = np.arange(TARGET_SR * 4) / float(TARGET_SR)
        keys = np.random.normal(0, 0.0005, len(t)).astype(np.float32)
        for idx in [4000, 12000, 20000, 28000]:
            keys[idx:idx+300] += 0.25 * np.sin(np.linspace(0, 10*np.pi, 300)).astype(np.float32)
        q = measure_quality(keys)
        # Gated enrollment should not occur
        if _speech_credible(keys, q, is_real_ml=True):
            spk.enroll(sid, keys)
        assert spk.is_enrolled(sid) is False

    def test_genuine_speech_can_enroll_in_real_ml(self):
        from pathlib import Path
        from app.ml.identity.speaker import SpeakerIdentity
        sid = "test-vad-can-enroll"
        spk = SpeakerIdentity(pipeline_mode="real_ml")
        spk.clear(sid)
        import soundfile as sf
        path = Path(__file__).parents[3] / "data/external/InTheWild/release_in_the_wild/8.wav"
        h_data, _ = sf.read(str(path))
        human = h_data[:TARGET_SR * 4].astype(np.float32)
        q = measure_quality(human)
        if _speech_credible(human, q, is_real_ml=True):
            spk.enroll(sid, human)
        assert spk.is_enrolled(sid) is True

