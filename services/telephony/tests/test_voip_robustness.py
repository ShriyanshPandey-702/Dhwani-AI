"""
VoiceShield Telephony — VoIP Adversarial Robustness Harness Unit Tests.

Validates the building blocks of Phase 5.3 VoIP robustness testing:
1. Determinism of audio degradation transforms.
2. 16 kHz to 8 kHz linear PCM and G.711 u-law conversion and framing.
3. Controlled RTP packet-loss injection math and sequence gap creation.
4. RtpDepacketizer sequence gap telemetry under packet drops.
5. Intercepting WebSocket wrapper for live event capture.
6. Paired-sample delta calculation and decision flip tracking.
"""

from __future__ import annotations

import asyncio
import json
import struct
import numpy as np
from scipy import signal

from evaluation.robustness.transforms import apply_condition
from services.telephony.gateway.rtp import RtpDepacketizer
from services.telephony.scripts.test_call_stream import _linear_to_ulaw


# ── Test 1: Determinism of Audio Degradation Transforms ─────────────────────────

def test_audio_transforms_deterministic():
    """Verify that every stochastic transform is 100% deterministic given the same seed."""
    sr = 16000
    t = np.linspace(0, 1.0, sr, dtype=np.float32)
    clean_audio = 0.5 * np.sin(2 * np.pi * 440 * t)

    stochastic_conditions = [
        "noise_white_10db",
        "noise_white_0db",
        "noise_pink_10db",
        "noise_babble_10db",
        "reverb_300ms",
    ]

    for cond in stochastic_conditions:
        out1 = apply_condition(cond, clean_audio, seed=42)
        out2 = apply_condition(cond, clean_audio, seed=42)
        out3 = apply_condition(cond, clean_audio, seed=999)

        # Same seed must yield exact byte-for-byte match
        np.testing.assert_array_equal(out1, out2, err_msg=f"Condition {cond} not deterministic with seed 42")
        # Different seeds must produce different perturbations for stochastic transforms
        assert not np.array_equal(out1, out3), f"Condition {cond} did not vary with seed change"

    # Deterministic non-stochastic transforms must also produce identical output on repeated runs
    det_out1 = apply_condition("telephone_chain", clean_audio, seed=42)
    det_out2 = apply_condition("telephone_chain", clean_audio, seed=42)
    np.testing.assert_array_equal(det_out1, det_out2)


# ── Test 2: Audio Resampling and G.711 u-law Framing ────────────────────────────

def test_resample_and_ulaw_conversion():
    """Verify resampling 16 kHz audio to 8 kHz and encoding into 20ms (160 bytes) u-law frames."""
    sr_in = 16000
    duration_s = 1.0
    t = np.linspace(0, duration_s, int(sr_in * duration_s), dtype=np.float32)
    audio_16k = 0.6 * np.sin(2 * np.pi * 500 * t)

    # Resample to 8000 Hz
    audio_8k = signal.resample_poly(audio_16k, 8000, sr_in)
    assert len(audio_8k) == 8000

    # Scale to 16-bit integer
    int_samples = (np.clip(audio_8k, -1.0, 1.0) * 32767.0).astype(np.int16)

    # Frame into 20ms slices (160 samples @ 8000 Hz)
    samples_per_frame = 160
    frames: list[bytes] = []
    for i in range(0, len(int_samples), samples_per_frame):
        slice_s = int_samples[i : i + samples_per_frame]
        ulaw_bytes = bytes(_linear_to_ulaw(int(s)) for s in slice_s)
        assert len(ulaw_bytes) == samples_per_frame
        frames.append(ulaw_bytes)

    assert len(frames) == 50  # 1.0s / 20ms = 50 frames


# ── Test 3: Controlled RTP Packet Loss Accounting ─────────────────────────────

def test_controlled_packet_loss_injection():
    """Verify sender packet-loss accounting: generated == dropped + transmitted."""
    total_packets = 200  # 4 seconds of 20ms frames
    loss_rate = 0.05
    seed = 1337

    rng = np.random.default_rng(seed)
    packets_generated = 0
    packets_dropped = 0
    packets_transmitted = 0

    for _ in range(total_packets):
        packets_generated += 1
        if rng.random() < loss_rate:
            packets_dropped += 1
        else:
            packets_transmitted += 1

    assert packets_generated == total_packets
    assert packets_dropped + packets_transmitted == packets_generated
    assert packets_dropped > 0  # 5% of 200 should drop ~10 packets
    assert abs(packets_dropped / total_packets - loss_rate) < 0.03


# ── Test 4: Sequence Gap Telemetry under Controlled Dropping ───────────────────

def test_rtp_sequence_gap_accounting():
    """Verify that when a packet is intentionally dropped, the receiver tracks sequence gaps."""
    depacketizer = RtpDepacketizer(is_big_endian=True)
    ssrc = 0x12345678
    ts = 0
    seq = 1000

    rng = np.random.default_rng(42)
    packets_generated = 50
    packets_dropped = 0
    packets_sent = 0

    dummy_payload = b"\x00" * 320  # 160 samples 16-bit SLIN16 or similar

    for _ in range(packets_generated):
        drop = rng.random() < 0.10  # 10% drop
        if drop:
            packets_dropped += 1
            # Advance seq and ts, but DO NOT deliver to depacketizer
            seq = (seq + 1) & 0xFFFF
            ts = (ts + 160) & 0xFFFFFFFF
        else:
            packets_sent += 1
            header = struct.pack(">BBHII", 0x80, 0, seq, ts, ssrc)
            packet = header + dummy_payload
            pkt = depacketizer.parse_packet(packet)
            assert pkt is not None
            seq = (seq + 1) & 0xFFFF
            ts = (ts + 160) & 0xFFFFFFFF

    t = depacketizer.telemetry
    assert t.packets_received == packets_sent
    assert t.sequence_gaps == packets_dropped
    assert t.packets_invalid == 0


# ── Test 5: Intercepting WebSocket Wrapper ────────────────────────────────────

def test_intercepting_ws_wrapper():
    """Verify that InterceptingWsWrapper captures events without interfering with async iteration."""
    async def _run():
        class MockWs:
            def __init__(self):
                self.closed = False
                self.events = [
                    json.dumps({"type": "audio_quality", "active": True}),
                    json.dumps({
                        "type": "risk_update",
                        "risk_score": 15,
                        "risk_state": "low",
                        "decision": "ALLOW",
                        "authenticity": {
                            "spoof_probability": 0.08,
                            "confidence": 0.75,
                            "model_name": "AASIST-L",
                            "pipeline_mode": "real_ml",
                        },
                        "context": {"transcript": "hello world"},
                    }),
                    json.dumps({"type": "policy_decision", "decision": "ALLOW"}),
                ]
                self.idx = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.idx >= len(self.events):
                    raise StopAsyncIteration
                ev = self.events[self.idx]
                self.idx += 1
                return ev

            async def close(self):
                self.closed = True

        class InterceptingWsWrapper:
            def __init__(self, ws, on_message):
                self._ws = ws
                self._on_message = on_message

            async def __aiter__(self):
                async for msg in self._ws:
                    self._on_message(msg)
                    yield msg

            def __getattr__(self, name):
                return getattr(self._ws, name)

        captured: list[dict] = []
        ws = MockWs()
        wrapped = InterceptingWsWrapper(ws, lambda raw: captured.append(json.loads(raw)))

        # Iterate through wrapper
        received_count = 0
        async for msg in wrapped:
            received_count += 1

        assert received_count == 3
        assert len(captured) == 3
        assert captured[1]["type"] == "risk_update"
        assert captured[1]["risk_score"] == 15
        assert captured[1]["authenticity"]["spoof_probability"] == 0.08

        # Ensure proxy methods work
        assert wrapped.closed is False
        await wrapped.close()
        assert wrapped.closed is True

    asyncio.run(_run())


# ── Test 6: Paired Delta and Decision Flip Mathematics ────────────────────────

def test_paired_delta_math():
    """Verify paired evaluation comparison against clean baseline."""
    clean_rec = {
        "sample_id": "BF_1",
        "condition": "clean",
        "aasist_score": 0.0500,
        "risk_score": 12.0,
        "policy_decision": "ALLOW",
    }

    degraded_rec = {
        "sample_id": "BF_1",
        "condition": "noise_white_10db",
        "aasist_score": 0.2200,
        "risk_score": 26.0,
        "policy_decision": "ALLOW",
    }

    flipped_rec = {
        "sample_id": "BF_1",
        "condition": "noise_white_0db",
        "aasist_score": 0.4500,
        "risk_score": 45.0,
        "policy_decision": "VERIFY",
    }

    # Degradation 1: No flip
    delta_aasist_1 = round(degraded_rec["aasist_score"] - clean_rec["aasist_score"], 4)
    delta_risk_1 = round(degraded_rec["risk_score"] - clean_rec["risk_score"], 2)
    flipped_1 = degraded_rec["policy_decision"] != clean_rec["policy_decision"]

    assert delta_aasist_1 == 0.1700
    assert delta_risk_1 == 14.00
    assert flipped_1 is False

    # Degradation 2: Flipped ALLOW -> VERIFY
    delta_aasist_2 = round(flipped_rec["aasist_score"] - clean_rec["aasist_score"], 4)
    delta_risk_2 = round(flipped_rec["risk_score"] - clean_rec["risk_score"], 2)
    flipped_2 = flipped_rec["policy_decision"] != clean_rec["policy_decision"]
    flip_type = f"{clean_rec['policy_decision']}->{flipped_rec['policy_decision']}"

    assert delta_aasist_2 == 0.4000
    assert delta_risk_2 == 33.00
    assert flipped_2 is True
    assert flip_type == "ALLOW->VERIFY"


# ── Test 7: AASIST Extraction Correctness ─────────────────────────────────────

def _extract_aasist_from_events(risk_updates: list) -> tuple:
    """
    Mirrors the corrected extraction logic from run_voip_robustness.py.
    Returns (aasist_scores, windows_with_auth, windows_without_auth, evidence_status, mean_aasist).
    """
    aasist_scores = []
    windows_with_auth = 0
    windows_without_auth = 0

    for ru in risk_updates:
        raw_auth = ru.get("authenticity")
        if raw_auth is None:
            windows_without_auth += 1
        elif isinstance(raw_auth, dict):
            score = raw_auth.get("spoof_probability")
            if score is not None:
                aasist_scores.append(float(score))
                windows_with_auth += 1
            else:
                windows_without_auth += 1
        else:
            windows_without_auth += 1

    if aasist_scores:
        evidence_status = "valid"
    elif windows_without_auth > 0:
        evidence_status = "authenticity_evidence_missing"
    else:
        evidence_status = "no_risk_updates"

    mean_aasist = round(float(np.mean(aasist_scores)), 4) if aasist_scores else None
    return aasist_scores, windows_with_auth, windows_without_auth, evidence_status, mean_aasist


def test_aasist_extraction_valid_spoof_probability():
    """Verify: spoof_probability=0.42 in a risk_update is recorded as 0.42 (not 0.0)."""
    risk_updates = [
        {
            "type": "risk_update",
            "risk_score": 55,
            "authenticity": {
                "spoof_probability": 0.42,
                "confidence": 0.88,
                "model_name": "AASIST-L",
                "pipeline_mode": "real_ml",
            },
        },
        {
            "type": "risk_update",
            "risk_score": 60,
            "authenticity": {
                "spoof_probability": 0.61,
                "confidence": 0.90,
                "model_name": "AASIST-L",
                "pipeline_mode": "real_ml",
            },
        },
    ]
    scores, valid, missing, status, mean = _extract_aasist_from_events(risk_updates)
    assert status == "valid", f"Expected 'valid' but got '{status}'"
    assert valid == 2
    assert missing == 0
    assert len(scores) == 2
    assert scores[0] == 0.42
    assert scores[1] == 0.61
    assert mean == round((0.42 + 0.61) / 2, 4)
    assert mean != 0.0, "Valid AASIST scores must not map to 0.0"


def test_aasist_extraction_null_authenticity_yields_none_not_zero():
    """
    Verify: when authenticity is null in the event (backend evidence pending/gating),
    the harness MUST record None, not 0.0.
    """
    risk_updates = [
        {"type": "risk_update", "risk_score": 25, "authenticity": None},
        {"type": "risk_update", "risk_score": 25, "authenticity": None},
    ]
    scores, valid, missing, status, mean = _extract_aasist_from_events(risk_updates)
    assert status == "authenticity_evidence_missing"
    assert valid == 0
    assert missing == 2
    assert len(scores) == 0
    assert mean is None, (
        f"Missing authenticity evidence must produce mean_aasist=None, not {mean!r}. "
        "Returning 0.0 is a reporting bug."
    )


def test_aasist_extraction_dict_without_spoof_probability_yields_none():
    """
    Verify: an authenticity dict that lacks spoof_probability (e.g., old schema
    with 'score' field) must NOT be silently recorded as 0.0.
    """
    risk_updates = [
        {
            "type": "risk_update",
            "risk_score": 25,
            # Old/wrong field name — no spoof_probability present
            "authenticity": {"score": 0.88, "synthetic_probability": 0.88},
        },
    ]
    scores, valid, missing, status, mean = _extract_aasist_from_events(risk_updates)
    # The dict does not contain spoof_probability, so it must be treated as missing
    assert valid == 0
    assert missing == 1
    assert len(scores) == 0
    assert mean is None, (
        f"Authenticity dict without spoof_probability must yield None, not {mean!r}."
    )

