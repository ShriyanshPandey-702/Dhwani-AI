"""
Audio preprocessing — PCM decode, normalisation, silence gating and
channel-quality measurement.

STATUS: REAL. These are ordinary signal-processing operations over the PCM the
client sends; nothing here is stubbed. What is *not* yet real is the source of
that PCM — see the audio-capture note in docs/tech.md.

PLANNED (Phase 3): torchaudio resampling and feature extraction feeding the
AASIST / ECAPA / Whisper front-ends directly.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional

import numpy as np

TARGET_SR = 16000
WINDOW_MS = 2000
HOP_MS = 1000
MIN_SPEECH_ENERGY = 1e-5   # below this a window is treated as silence
MIN_BYTES = 320            # < 10 ms at 16 kHz mono int16

GOOD, FAIR, POOR = "GOOD", "FAIR", "POOR"


@dataclass
class AudioQuality:
    """Channel-quality evidence shown on the dashboard."""

    level_db: float          # RMS level in dBFS
    estimated_snr_db: float
    clipping_ratio: float    # fraction of samples at full scale
    is_silent: bool
    quality: str             # GOOD | FAIR | POOR
    sample_rate: int
    duration_ms: int
    rms: float = 0.0
    energy_variance: float = 0.0
    zcr: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def decode_pcm(pcm_bytes: bytes) -> Optional[np.ndarray]:
    """
    Convert raw little-endian int16 PCM to normalised float32 in [-1, 1].
    Returns None if the buffer is too short or cannot be decoded.
    """
    if not pcm_bytes or len(pcm_bytes) < MIN_BYTES:
        return None
    try:
        # Trim a trailing odd byte rather than failing the whole frame.
        usable = len(pcm_bytes) - (len(pcm_bytes) % 2)
        audio = np.frombuffer(pcm_bytes[:usable], dtype=np.int16).astype(np.float32)
    except Exception:
        return None
    if audio.size == 0:
        return None
    return audio / 32768.0


def measure_quality(audio: Optional[np.ndarray], sr: int = TARGET_SR) -> AudioQuality:
    """Compute channel-quality metrics for one window."""
    if audio is None or audio.size == 0:
        return AudioQuality(
            level_db=-120.0, estimated_snr_db=0.0, clipping_ratio=0.0,
            is_silent=True, quality=POOR, sample_rate=sr, duration_ms=0,
        )

    rms = float(np.sqrt(np.mean(audio**2) + 1e-12))
    level_db = float(20.0 * np.log10(rms + 1e-12))
    clipping_ratio = float(np.mean(np.abs(audio) >= 0.999))
    is_silent = bool(np.mean(audio**2) < MIN_SPEECH_ENERGY)

    # SNR proxy: loudest decile (speech) against quietest decile (noise floor).
    frame = max(1, int(sr * 0.02))
    n = len(audio) // frame
    if n >= 10:
        frames = audio[: n * frame].reshape(n, frame)
        frame_energies = np.mean(frames**2, axis=1)
        energies = np.sort(frame_energies)
        noise = float(np.mean(energies[: max(1, n // 10)]) + 1e-12)
        speech = float(np.mean(energies[-max(1, n // 10):]) + 1e-12)
        snr_db = float(10.0 * np.log10(speech / noise))
        energy_variance = float(np.var(frame_energies))
    else:
        snr_db = 0.0
        energy_variance = 0.0
    snr_db = float(np.clip(snr_db, 0.0, 60.0))

    zcr = float(np.mean(np.abs(np.diff(np.sign(audio))) > 0)) if len(audio) > 1 else 0.0

    if is_silent or snr_db < 8.0 or clipping_ratio > 0.02:
        quality = POOR
    elif snr_db < 18.0 or level_db < -40.0:
        quality = FAIR
    else:
        quality = GOOD

    return AudioQuality(
        level_db=round(level_db, 2),
        estimated_snr_db=round(snr_db, 2),
        clipping_ratio=round(clipping_ratio, 5),
        is_silent=is_silent,
        quality=quality,
        sample_rate=sr,
        duration_ms=int(1000 * len(audio) / sr),
        rms=round(rms, 4),
        energy_variance=round(energy_variance, 6),
        zcr=round(zcr, 4),
    )


def preprocess_audio_chunk(pcm_bytes: bytes, sr: int = TARGET_SR) -> Optional[np.ndarray]:
    """
    Decode PCM and gate out silence.

    Returns None for silence so the Risk Engine stays at INSUFFICIENT_EVIDENCE
    instead of scoring an empty window.
    """
    audio = decode_pcm(pcm_bytes)
    if audio is None:
        return None
    if float(np.mean(audio**2)) < MIN_SPEECH_ENERGY:
        return None
    return audio


def extract_windows(
    audio: np.ndarray,
    sr: int = TARGET_SR,
    window_ms: int = WINDOW_MS,
    hop_ms: int = HOP_MS,
) -> List[np.ndarray]:
    """Split audio into overlapping analysis windows."""
    window_samples = int(sr * window_ms / 1000)
    hop_samples = max(1, int(sr * hop_ms / 1000))
    if len(audio) < window_samples:
        return [audio] if len(audio) else []
    return [
        audio[start:start + window_samples]
        for start in range(0, len(audio) - window_samples + 1, hop_samples)
    ]
