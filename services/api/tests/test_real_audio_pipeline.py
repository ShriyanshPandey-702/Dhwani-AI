"""
Real-audio ingestion and end-to-end pipeline tests.

These cover the path a real caller's audio actually takes:

    file/PCM -> validation -> WebSocket -> windower -> AASIST/ECAPA/Whisper
             -> context -> Risk Engine -> Policy -> events

The heavy real-ML assertions are skipped when the checkpoints are absent, so
the suite still runs on a clean checkout; where they do run they assert the
production frozen checkpoint, not a Phase 1 one.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from app.ml.preprocessing.ingest import (
    AudioIngestError, MAX_DURATION_S, iter_pcm_chunks, load_audio_file,
    normalize_array, to_int16_pcm,
)
from app.ml.preprocessing.audio import decode_pcm
from app.ml.preprocessing.stream import StreamWindower

REPO = Path(__file__).resolve().parents[3]
FUNCTIONAL = REPO / "evaluation" / "functional" / "functional_test_set.json"
AASIST_L = REPO / "services" / "api" / "models" / "aasist" / "AASIST-L.pth"
PINNED_SHA = "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a"


def _functional_items():
    if not FUNCTIONAL.is_file():
        return []
    items = json.load(open(FUNCTIONAL))["items"]
    return [i for i in items if (REPO / i["file"]).is_file()]


ITEMS = _functional_items()
has_audio = bool(ITEMS)
has_ckpt = AASIST_L.is_file()


# ══ AUDIO VALIDATION ═════════════════════════════════════════════════════════

def test_empty_audio_is_rejected():
    with pytest.raises(AudioIngestError, match="empty"):
        normalize_array(np.array([], dtype=np.float32), 16000)


def test_nan_and_inf_are_rejected_before_reaching_a_model():
    for bad in (np.nan, np.inf, -np.inf):
        a = np.zeros(1600, dtype=np.float32)
        a[10] = bad
        with pytest.raises(AudioIngestError, match="NaN or Inf"):
            normalize_array(a, 16000)


def test_implausible_sample_rate_is_rejected():
    a = np.zeros(1600, dtype=np.float32)
    for sr in (0, -16000, 10_000_000):
        with pytest.raises(AudioIngestError, match="sample rate"):
            normalize_array(a, sr)


def test_stereo_is_downmixed_to_mono():
    stereo = np.stack([np.ones(1600), -np.ones(1600)], axis=1).astype(np.float32)
    out, meta = normalize_array(stereo, 16000)
    assert out.ndim == 1 and meta.downmixed is True
    assert meta.original_channels == 2
    assert np.allclose(out, 0.0)          # +1 and -1 average to silence


def test_wrong_sample_rate_is_resampled_to_16k():
    a = np.sin(2 * np.pi * 220 * np.arange(8000) / 8000).astype(np.float32)
    out, meta = normalize_array(a, 8000)
    assert meta.resampled is True
    assert meta.normalized_sample_rate == 16000
    assert abs(out.size - 16000) <= 2      # 1 s of audio at 16 kHz


def test_excessive_amplitude_is_clamped_and_counted():
    a = np.full(1600, 3.5, dtype=np.float32)
    out, meta = normalize_array(a, 16000)
    assert meta.clipped_samples == 1600
    assert float(np.max(np.abs(out))) <= 1.0


def test_absurdly_long_audio_is_refused():
    fake = np.zeros(16000, dtype=np.float32)
    with pytest.raises(AudioIngestError, match="too long"):
        # 1 sample/second makes the duration enormous without allocating it.
        normalize_array(fake, sr=1)


def test_missing_file_is_refused():
    with pytest.raises(AudioIngestError, match="not a file"):
        load_audio_file("/nonexistent/definitely-not-here.wav")


def test_truncated_or_non_audio_file_is_refused(tmp_path):
    p = tmp_path / "broken.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt not-really-audio")
    with pytest.raises(AudioIngestError, match="cannot decode"):
        load_audio_file(p)


def test_empty_file_is_refused(tmp_path):
    p = tmp_path / "empty.wav"
    p.write_bytes(b"")
    with pytest.raises(AudioIngestError, match="empty file"):
        load_audio_file(p)


def test_metadata_never_contains_audio_samples():
    a = np.sin(np.arange(1600) / 10).astype(np.float32)
    _, meta = normalize_array(a, 16000)
    blob = json.dumps(meta.to_dict())
    assert "samples" not in blob or "normalized_samples" in blob
    for key, value in meta.to_dict().items():
        assert not isinstance(value, (list, tuple)), f"{key} leaks array data"


# ══ PCM WIRE FORMAT ══════════════════════════════════════════════════════════

def test_pcm_round_trip_preserves_the_signal():
    a = (np.sin(2 * np.pi * 200 * np.arange(1600) / 16000) * 0.5).astype(np.float32)
    back = decode_pcm(to_int16_pcm(a))
    assert back is not None
    assert np.max(np.abs(back - a)) < 1e-3      # int16 quantisation only


def test_chunking_covers_every_sample_exactly_once():
    a = np.arange(16000 * 3, dtype=np.float32) / (16000 * 3)
    for chunk_ms in (20, 40, 100, 250):
        chunks = list(iter_pcm_chunks(a, chunk_ms))
        total = sum(len(c) // 2 for c in chunks)
        assert total == a.size, f"{chunk_ms} ms lost or duplicated samples"


def test_zero_chunk_size_is_refused():
    with pytest.raises(AudioIngestError):
        list(iter_pcm_chunks(np.zeros(100, dtype=np.float32), 0))


# ══ BUFFER: exact sample accounting ══════════════════════════════════════════

def test_windower_emits_on_an_exact_known_schedule():
    """N samples in -> a known number of windows out, with no drift."""
    w = StreamWindower(window_ms=4038, hop_ms=1000)
    assert w.window_samples == 64608 and w.hop_samples == 16000

    sid = "acct"
    frame = np.ones(1600, dtype=np.float32)      # 100 ms frames
    emitted_at = []
    for i in range(1, 121):                      # 12.0 s of audio
        if w.push(sid, frame) is not None:
            emitted_at.append(i)

    # 64608 samples are needed before the first window, i.e. 40.38 frames, so
    # the first lands on frame 41. After that one window per hop = 10 frames.
    # Within 120 frames that is exactly: 41, 51, 61, 71, 81, 91, 101, 111.
    assert emitted_at == [41, 51, 61, 71, 81, 91, 101, 111], emitted_at

    stats = w.stats(sid)
    assert stats.frames_received == 120
    assert stats.windows_emitted == len(emitted_at)
    assert stats.buffered_samples <= w.window_samples + w.hop_samples


def test_windower_never_exceeds_its_documented_bound():
    w = StreamWindower(window_ms=4038, hop_ms=1000)
    for _ in range(500):
        w.push("bound", np.zeros(1600, dtype=np.float32))
    assert w.stats("bound").buffered_samples <= 64608 + 16000


# ══ MODEL INTEGRITY ══════════════════════════════════════════════════════════

@pytest.mark.skipif(not has_ckpt, reason="AASIST-L checkpoint not present")
def test_production_checkpoint_matches_the_pinned_hash():
    h = hashlib.sha256()
    with open(AASIST_L, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    assert h.hexdigest() == PINNED_SHA, "production AASIST-L checkpoint changed"


@pytest.mark.skipif(not has_ckpt, reason="AASIST-L checkpoint not present")
def test_no_phase1_checkpoint_is_wired_into_production():
    from app.core.config import settings
    assert "phase1" not in str(settings.MODEL_DIR).lower()
    assert settings.AASIST_VARIANT in ("AASIST-L", "AASIST")


@pytest.mark.skipif(not has_ckpt, reason="AASIST-L checkpoint not present")
def test_real_aasist_inference_is_deterministic():
    from app.ml.authenticity.aasist import AASISTDetector
    det = AASISTDetector(model_dir=str(REPO / "services/api/models"), cascade=False)
    if det.missing_checkpoints():
        pytest.skip("checkpoints unavailable")
    rng = np.random.default_rng(0)
    audio = (rng.standard_normal(64600) * 0.05).astype(np.float32)
    a = det.score(audio).synthetic_probability
    b = det.score(audio).synthetic_probability
    assert a == b


# ══ REAL AUDIO THROUGH THE PRODUCTION PIPELINE ═══════════════════════════════

@pytest.mark.skipif(not has_audio, reason="functional test audio not present")
def test_functional_set_is_disjoint_from_the_sealed_delta_manifest():
    import csv
    man = json.load(open(FUNCTIONAL))
    delta_manifest = REPO / "evaluation/results/inthewild_delta_baseline/manifest_test.csv"
    if not delta_manifest.is_file():
        pytest.skip("delta manifest absent")
    sealed = {r["audio_path"] for r in csv.DictReader(open(delta_manifest))}
    assert man["purpose"] == "FUNCTIONAL_TEST"
    assert not [i["file"] for i in man["items"] if i["file"] in sealed]


@pytest.mark.skipif(not has_audio, reason="functional test audio not present")
def test_real_audio_flows_through_the_whole_pipeline():
    """Real speech in, a real Risk Engine verdict out — nothing injected."""
    from app.risk.policy import DEFAULT_POLICY_CONFIG
    from app.websocket.manager import SessionState
    from app.websocket.pipeline import analyze_window, stream_windower

    item = max(ITEMS, key=lambda i: i["duration_s"])
    audio, meta = load_audio_file(REPO / item["file"])
    assert meta.normalized_sample_rate == 16000

    sid = "func-e2e"
    stream_windower.reset(sid)
    state = SessionState(session_id=sid, user_id="u",
                         policy_config=dict(DEFAULT_POLICY_CONFIG))
    risk_updates, qualities = [], []
    for chunk in iter_pcm_chunks(audio, 100):
        for e in analyze_window(state, chunk, pipeline_mode="live"):
            if e["type"] == "risk_update":
                risk_updates.append(e)
            elif e["type"] == "audio_quality":
                qualities.append(e)
    stream_windower.reset(sid)

    assert qualities, "no audio_quality events"
    assert risk_updates, "real audio produced no risk update"
    last = risk_updates[-1]
    assert last["pipeline_mode"] == "live"
    assert last["risk_state"] in (
        "insufficient_evidence", "low", "suspicious", "high", "critical")
    assert isinstance(last["risk_score"], int)
    # Authoritative values come from the backend engine, never the client.
    assert "authenticity" in last and "identity" in last


@pytest.mark.skipif(not (has_audio and has_ckpt), reason="audio or checkpoint absent")
def test_real_audio_reaches_the_real_aasist_model_when_real_ml_is_enabled():
    """
    The §28-A guarantee: with real ML on, a real file is scored by AASIST-L.

    Uses the detector directly (rather than the env-dependent singleton) so the
    assertion is about the model actually running, not about import order.
    """
    from app.ml.authenticity.detector import AuthenticityDetector

    det = AuthenticityDetector(pipeline_mode="real_ml")
    if not det.is_real_ml:
        pytest.skip(f"real ML unavailable: {det.fallback_reason}")

    item = max(ITEMS, key=lambda i: i["duration_s"])
    audio, _ = load_audio_file(REPO / item["file"])
    result = det.analyze(audio[:64600])

    assert result is not None
    assert result.pipeline_mode == "real_ml"
    assert result.is_mock is False
    assert result.model_name == "AASIST"
    assert "asvspoof2019la" in result.model_version
    assert 0.0 <= result.spoof_probability <= 1.0
    assert result.inference_ms > 0, "a real forward pass takes measurable time"


@pytest.mark.skipif(not has_audio, reason="functional test audio not present")
def test_silence_never_becomes_evidence_of_a_synthetic_voice():
    from app.risk.policy import DEFAULT_POLICY_CONFIG
    from app.websocket.manager import SessionState
    from app.websocket.pipeline import analyze_window, stream_windower

    sid = "func-silence"
    stream_windower.reset(sid)
    state = SessionState(session_id=sid, user_id="u",
                         policy_config=dict(DEFAULT_POLICY_CONFIG))
    silence = to_int16_pcm(np.zeros(16000, dtype=np.float32))
    events = []
    for _ in range(10):
        events.extend(analyze_window(state, silence, pipeline_mode="live"))
    stream_windower.reset(sid)

    assert not [e for e in events if e["type"] == "risk_update"], \
        "silence produced a risk update"
    assert state.last_authenticity is None
    assert all(e["active"] is False
               for e in events if e["type"] == "audio_quality")
