"""
Acoustic / spectral / prosodic feature extraction.

STATUS: REAL. These are ordinary signal measurements over the audio buffer and
are computed the same way whichever inference backend is active.

They are deliberately kept separate from the *model* that turns evidence into a
spoof probability. The heuristic backend blends them into a score; the AASIST
backend reports them alongside the model's probability as independent
observations. Neither reads conversation context or speaker identity.
"""

from __future__ import annotations

import numpy as np

LOW, MEDIUM, HIGH = "LOW", "MEDIUM", "HIGH"


def band(value: float) -> str:
    """Map a 0.0–1.0 anomaly level onto the band the dashboard renders."""
    if value >= 0.66:
        return HIGH
    if value >= 0.33:
        return MEDIUM
    return LOW


def frame_energy(audio: np.ndarray, sample_rate: int, frame_s: float) -> np.ndarray:
    frame = max(1, int(sample_rate * frame_s))
    n = len(audio) // frame
    if n < 2:
        return np.array([], dtype=np.float64)
    frames = audio[: n * frame].reshape(n, frame)
    return np.sqrt(np.mean(frames**2, axis=1) + 1e-12)


def voiced(energy: np.ndarray, floor_ratio: float = 0.35) -> np.ndarray:
    """Keep only frames above a fraction of mean energy — drops inter-word pauses."""
    if energy.size == 0:
        return energy
    return energy[energy >= floor_ratio * float(np.mean(energy))]


def acoustic_anomaly(audio: np.ndarray, sample_rate: int) -> float:
    """
    Over-smooth amplitude envelopes are a classic vocoder artefact. Low
    short-term energy variance *within voiced speech* raises the anomaly.

    Pauses are excluded first: a pause contributes variance in any recording,
    natural or synthetic, and would mask the syllabic modulation being measured.
    """
    v = voiced(frame_energy(audio, sample_rate, 0.02))
    if v.size < 4:
        return 0.0
    rel_var = float(np.std(v) / (np.mean(v) + 1e-9))
    return float(np.clip(1.0 - rel_var / 0.45, 0.0, 1.0))


def spectral_anomaly(audio: np.ndarray, sample_rate: int) -> float:
    """
    Many synthesis pipelines roll off or truncate high-frequency content.
    Combines a normalised spectral centroid with spectral flatness.
    """
    n = min(len(audio), 8192)
    if n < 64:
        return 0.0
    window = audio[:n] * np.hanning(n)
    mag = np.abs(np.fft.rfft(window)) + 1e-12
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    centroid = float(np.sum(freqs * mag) / np.sum(mag))
    centroid_anom = float(np.clip(1.0 - centroid / 2000.0, 0.0, 1.0))

    geo = float(np.exp(np.mean(np.log(mag))))
    arith = float(np.mean(mag))
    flatness = geo / (arith + 1e-12)
    flat_anom = float(np.clip(abs(flatness - 0.15) / 0.35, 0.0, 1.0))

    return float(np.clip(0.6 * centroid_anom + 0.4 * flat_anom, 0.0, 1.0))


def prosody_anomaly(audio: np.ndarray, sample_rate: int) -> float:
    """
    Zero-crossing-rate variability across voiced frames, a cheap proxy for pitch
    and rhythm variation. Flat prosody raises the anomaly.
    """
    frame = max(1, int(sample_rate * 0.03))
    n = len(audio) // frame
    if n < 4:
        return 0.0
    frames = audio[: n * frame].reshape(n, frame)
    energy = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    mask = energy >= 0.35 * float(np.mean(energy))
    if int(np.count_nonzero(mask)) < 4:
        return 0.0
    zcr = np.mean(np.abs(np.diff(np.sign(frames[mask]), axis=1)) > 0, axis=1)
    variability = float(np.std(zcr) / (np.mean(zcr) + 1e-9))
    return float(np.clip(1.0 - variability / 0.22, 0.0, 1.0))


def anomaly_bands(audio: np.ndarray, sample_rate: int) -> dict:
    """All three anomaly families, as the bands the evidence object carries."""
    return {
        "acoustic_anomaly": band(acoustic_anomaly(audio, sample_rate)),
        "spectral_anomaly": band(spectral_anomaly(audio, sample_rate)),
        "prosody_anomaly": band(prosody_anomaly(audio, sample_rate)),
    }
