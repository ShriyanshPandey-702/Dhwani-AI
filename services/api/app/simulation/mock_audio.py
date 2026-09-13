"""
DEVELOPMENT MOCK AUDIO — synthetic PCM for demos and tests.

╔══════════════════════════════════════════════════════════════════════════╗
║  This is NOT real call audio and NOT Android audio capture.              ║
║                                                                          ║
║  It exists so the full WebSocket → Risk Engine → Policy Engine →         ║
║  dashboard path can be exercised end to end before real capture lands.   ║
║  Every event derived from this source is tagged pipeline_mode="mock" on  ║
║  the wire, and the mobile dashboard renders a MOCK DATA banner.          ║
║                                                                          ║
║  REAL ANDROID AUDIO CAPTURE (Phase 7) will feed the identical pipeline   ║
║  with pipeline_mode="live". Nothing downstream changes.                  ║
╚══════════════════════════════════════════════════════════════════════════╝

The generated waveforms are genuine signals: as the scripted scenario
progresses they acquire the artefacts the heuristic detector actually looks
for — a flatter amplitude envelope, a lower spectral centroid and reduced
prosodic variation. The detector is therefore doing real work on real audio;
only the audio's provenance is synthetic.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 1000


def generate_frame(step: int, total_steps: int = 12, sr: int = SAMPLE_RATE,
                   duration_ms: int = FRAME_MS, seed: int | None = None) -> bytes:
    """
    Produce one int16 PCM frame for `step` of a scripted call.

    `progression` moves 0 → 1 across the call. At 0 the frame carries natural
    speech (broadband, variable envelope, varied pitch); at 1 it carries the
    over-smoothed, band-limited characteristics of vocoded output.
    """
    rng = np.random.default_rng(seed if seed is not None else step)
    n = int(sr * duration_ms / 1000)
    t = np.arange(n) / sr
    progression = float(np.clip(step / max(1, total_steps - 1), 0.0, 1.0))

    # ── Pitch: natural speech wanders; synthetic output is flatter ───────────
    f0_base = 130.0
    vibrato_depth = 14.0 * (1.0 - 0.85 * progression)
    f0 = f0_base + vibrato_depth * np.sin(2 * np.pi * 1.7 * t) \
        + (1.0 - progression) * 6.0 * rng.standard_normal(n).cumsum() / max(1, n) * 10
    phase = 2 * np.pi * np.cumsum(f0) / sr

    # ── Harmonics: high partials roll off as progression rises ──────────────
    signal = np.zeros(n, dtype=np.float64)
    n_harmonics = 18
    for h in range(1, n_harmonics + 1):
        rolloff = 1.0 / h
        # Aggressive high-frequency attenuation at high progression
        hf_penalty = 1.0 - progression * min(1.0, (h - 1) / 6.0)
        signal += rolloff * max(0.0, hf_penalty) * np.sin(h * phase)
    signal /= np.max(np.abs(signal)) + 1e-9

    # ── Amplitude envelope: syllabic modulation flattens out ────────────────
    syllable_rate = 4.0
    mod_depth = 0.75 * (1.0 - 0.85 * progression)
    envelope = (1.0 - mod_depth) + mod_depth * (
        0.5 * (1.0 + np.sin(2 * np.pi * syllable_rate * t))
    )
    signal *= envelope

    # ── Inter-word pauses: present in any real call, synthetic or not. They
    #    give the quality meter a measurable noise floor. ────────────────────
    gate = np.ones(n)
    pause_len = int(sr * 0.18)
    for start in (int(sr * 0.30), int(sr * 0.72)):
        gate[start:start + pause_len] = 0.05
    signal *= gate

    # ── Noise floor: natural recordings carry breath and room noise ─────────
    noise_level = 0.004 * (1.0 - 0.5 * progression)
    signal += noise_level * rng.standard_normal(n)

    signal = np.clip(signal * 0.45, -1.0, 1.0)
    return (signal * 32767).astype(np.int16).tobytes()


def generate_silence(sr: int = SAMPLE_RATE, duration_ms: int = FRAME_MS) -> bytes:
    """A silent frame — used to test the insufficient-evidence path."""
    return np.zeros(int(sr * duration_ms / 1000), dtype=np.int16).tobytes()
