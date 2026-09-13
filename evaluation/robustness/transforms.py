"""
Controlled audio degradations for robustness testing.

Every transform is deterministic given a seed, operates on float32 mono at a
stated sample rate, and is a *synthetic* approximation of a real-world effect.

READ THIS BEFORE QUOTING ANY RESULT: passing these tests is not field
validation. A synthetic band-limit plus companding is not a real GSM/AMR codec
over a real network, and a synthetic impulse response is not a real room. These
measure sensitivity to a known perturbation, nothing more.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import numpy as np
from scipy import signal

SAMPLE_RATE = 16000


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def _as_float32(audio: np.ndarray) -> np.ndarray:
    return np.asarray(audio, dtype=np.float32).ravel()


def _rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2) + 1e-20))


# ── Additive noise ───────────────────────────────────────────────────────────

def add_noise(audio, snr_db: float, seed: int = 0, sr: int = SAMPLE_RATE,
              kind: str = "white") -> np.ndarray:
    """
    Mix noise at a target SNR, measured over the whole signal.

    `kind`: "white" (flat), "pink" (1/f, closer to ambient), or "babble"
    (several band-limited streams, a crude speech-babble stand-in).
    """
    x = _as_float32(audio)
    rng = _rng(seed)

    if kind == "white":
        noise = rng.standard_normal(x.size)
    elif kind == "pink":
        white = rng.standard_normal(x.size)
        spectrum = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(x.size, 1.0 / sr)
        scale = np.ones_like(freqs)
        scale[1:] = 1.0 / np.sqrt(freqs[1:])
        noise = np.fft.irfft(spectrum * scale, n=x.size)
    elif kind == "babble":
        noise = np.zeros(x.size)
        for _ in range(6):
            stream = rng.standard_normal(x.size)
            b, a = signal.butter(2, [300 / (sr / 2), 3000 / (sr / 2)], btype="band")
            noise += signal.lfilter(b, a, stream)
    else:
        raise ValueError(f"unknown noise kind {kind!r}")

    noise = noise / (np.sqrt(np.mean(noise ** 2)) + 1e-20)
    target_noise_rms = _rms(x) / (10 ** (snr_db / 20.0))
    return np.clip(x + (noise * target_noise_rms).astype(np.float32), -1.0, 1.0).astype(np.float32)


# ── Channel and codec approximations ─────────────────────────────────────────

def resample_roundtrip(audio, sr: int = SAMPLE_RATE, intermediate: int = 8000) -> np.ndarray:
    """Downsample then restore — models loss of high-frequency detail."""
    x = _as_float32(audio)
    down = signal.resample_poly(x, intermediate, sr)
    return _as_float32(signal.resample_poly(down, sr, intermediate))[: x.size]


def lowpass(audio, cutoff_hz: float = 4000.0, sr: int = SAMPLE_RATE) -> np.ndarray:
    b, a = signal.butter(6, cutoff_hz / (sr / 2), btype="low")
    return _as_float32(signal.lfilter(b, a, _as_float32(audio)))


def telephone_band(audio, sr: int = SAMPLE_RATE) -> np.ndarray:
    """300–3400 Hz band-limit — the classic narrowband telephony passband."""
    x = _as_float32(audio)
    b, a = signal.butter(6, [300 / (sr / 2), 3400 / (sr / 2)], btype="band")
    return _as_float32(signal.lfilter(b, a, x))


def mu_law_companding(audio, mu: float = 255.0) -> np.ndarray:
    """
    G.711 µ-law quantisation round trip — 8-bit companding.

    This is a real companding curve, but it is NOT a full codec: no framing,
    no packetisation, no bitrate adaptation. Do not describe it as "G.711".
    """
    x = np.clip(_as_float32(audio), -1.0, 1.0)
    compressed = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    quantised = np.round(compressed * 127.0) / 127.0
    expanded = np.sign(quantised) * ((1 + mu) ** np.abs(quantised) - 1) / mu
    return _as_float32(expanded)


def telephone_chain(audio, sr: int = SAMPLE_RATE, seed: int = 0) -> np.ndarray:
    """Band-limit → 8 kHz round trip → companding. A telephony *approximation*."""
    return mu_law_companding(resample_roundtrip(telephone_band(audio, sr), sr))


# ── Level, clipping, room ────────────────────────────────────────────────────

def gain(audio, gain_db: float) -> np.ndarray:
    return np.clip(_as_float32(audio) * (10 ** (gain_db / 20.0)), -1.0, 1.0).astype(np.float32)


def clip_signal(audio, threshold: float = 0.3) -> np.ndarray:
    """
    Hard clipping — models an overdriven input stage.

    The waveform is clipped and left at that level; no renormalisation, because
    restoring the original RMS would undo the very distortion being tested.
    """
    return np.clip(_as_float32(audio), -threshold, threshold).astype(np.float32)


def reverb(audio, sr: int = SAMPLE_RATE, rt60_s: float = 0.3, seed: int = 0) -> np.ndarray:
    """
    Convolve with a synthetic exponentially-decaying noise impulse response.
    A crude room simulation, not a measured RIR.
    """
    rng = _rng(seed)
    length = int(sr * rt60_s)
    envelope = np.exp(-6.9 * np.arange(length) / max(1, length))
    ir = rng.standard_normal(length) * envelope
    ir[0] += 1.0
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-20
    x = _as_float32(audio)
    wet = signal.fftconvolve(x, ir, mode="full")[: x.size]
    return np.clip(wet, -1.0, 1.0).astype(np.float32)


def packet_loss(audio, loss_rate: float = 0.02, packet_ms: float = 20.0,
                sr: int = SAMPLE_RATE, seed: int = 0) -> np.ndarray:
    """Zero out random fixed-length packets — crude VoIP loss without concealment."""
    x = _as_float32(audio).copy()
    rng = _rng(seed)
    n = max(1, int(sr * packet_ms / 1000))
    for start in range(0, x.size, n):
        if rng.random() < loss_rate:
            x[start:start + n] = 0.0
    return x


# ── Registry ─────────────────────────────────────────────────────────────────

CONDITIONS: Dict[str, Callable[[np.ndarray, int], np.ndarray]] = {
    "clean":            lambda a, s: _as_float32(a),
    "noise_white_20db": lambda a, s: add_noise(a, 20, seed=s, kind="white"),
    "noise_white_10db": lambda a, s: add_noise(a, 10, seed=s, kind="white"),
    "noise_white_5db":  lambda a, s: add_noise(a, 5, seed=s, kind="white"),
    "noise_white_0db":  lambda a, s: add_noise(a, 0, seed=s, kind="white"),
    "noise_babble_10db": lambda a, s: add_noise(a, 10, seed=s, kind="babble"),
    "noise_pink_10db":  lambda a, s: add_noise(a, 10, seed=s, kind="pink"),
    "resample_8k":      lambda a, s: resample_roundtrip(a),
    "lowpass_4k":       lambda a, s: lowpass(a, 4000),
    "lowpass_3k4":      lambda a, s: lowpass(a, 3400),
    "telephone_band":   lambda a, s: telephone_band(a),
    "mu_law":           lambda a, s: mu_law_companding(a),
    "telephone_chain":  lambda a, s: telephone_chain(a, seed=s),
    "gain_minus_20db":  lambda a, s: gain(a, -20),
    "gain_plus_6db":    lambda a, s: gain(a, 6),
    "clipping":         lambda a, s: clip_signal(a, 0.3),
    "reverb_300ms":     lambda a, s: reverb(a, rt60_s=0.3, seed=s),
    "packet_loss_2pct": lambda a, s: packet_loss(a, 0.02, seed=s),
    "packet_loss_5pct": lambda a, s: packet_loss(a, 0.05, seed=s),
}


def apply_condition(name: str, audio: np.ndarray, seed: int = 0) -> np.ndarray:
    if name not in CONDITIONS:
        raise KeyError(f"unknown condition {name!r}; have {sorted(CONDITIONS)}")
    out = CONDITIONS[name](audio, seed)
    if not np.all(np.isfinite(out)):
        raise ValueError(f"condition {name!r} produced non-finite audio")
    return _as_float32(out)
