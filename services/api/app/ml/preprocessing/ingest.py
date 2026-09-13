"""
Canonical audio ingestion — the ONE place a file or foreign buffer becomes
VoiceShield's internal representation.

Internal contract (unchanged from the validated pipeline; see docs/models.md):

    mono · float32 in [-1, 1] · 16 kHz · no implicit gain change

`decode_pcm` in `audio.py` remains the wire path for streamed int16 PCM. This
module is the *file / foreign format* path: it validates, converts once, and
hands back the same representation, so AASIST, ECAPA and Whisper are never fed
audio that took a different route.

It deliberately does NOT resample or re-window inside the model wrappers —
model-side length policy (tile/centre-crop to 64,600) stays where it was.

Nothing here logs audio content. Only metadata is returned.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

TARGET_SR = 16000
MAX_FILE_BYTES = 200 * 1024 * 1024      # refuse absurd uploads outright
MAX_DURATION_S = 60 * 30                # 30 minutes


class AudioIngestError(ValueError):
    """Raised for audio that cannot be safely turned into the internal form."""


@dataclass(frozen=True)
class AudioMeta:
    """Everything we are willing to record about a piece of audio."""
    source: str
    original_sample_rate: int
    original_channels: int
    original_frames: int
    duration_s: float
    normalized_samples: int
    normalized_sample_rate: int
    resampled: bool
    downmixed: bool
    peak_abs: float
    clipped_samples: int

    def to_dict(self) -> dict:
        return asdict(self)


def _to_mono(audio: np.ndarray) -> Tuple[np.ndarray, bool]:
    if audio.ndim == 1:
        return audio, False
    return audio.mean(axis=1), True


def _resample(audio: np.ndarray, sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    if sr == target_sr:
        return audio
    from scipy import signal as sps
    g = np.gcd(int(sr), int(target_sr))
    return sps.resample_poly(audio, target_sr // g, sr // g)


def normalize_array(audio: np.ndarray, sr: int, source: str = "array") -> Tuple[np.ndarray, AudioMeta]:
    """
    Validate and convert an already-decoded array into the internal form.

    Raises AudioIngestError for anything that must not reach a model:
    empty audio, non-finite values, or an implausible sample rate.
    """
    if audio is None or getattr(audio, "size", 0) == 0:
        raise AudioIngestError("empty audio")
    if sr <= 0 or sr > 384_000:
        raise AudioIngestError(f"implausible sample rate: {sr}")

    a = np.asarray(audio, dtype=np.float32)
    if not np.all(np.isfinite(a)):
        # NaN/Inf would propagate silently through every downstream model.
        raise AudioIngestError("audio contains NaN or Inf")

    orig_channels = 1 if a.ndim == 1 else a.shape[1]
    orig_frames = a.shape[0]
    a, downmixed = _to_mono(a)

    duration_s = orig_frames / float(sr)
    if duration_s > MAX_DURATION_S:
        raise AudioIngestError(f"audio too long: {duration_s:.0f}s > {MAX_DURATION_S}s")

    resampled = sr != TARGET_SR
    a = _resample(a, sr, TARGET_SR).astype(np.float32, copy=False)

    peak = float(np.max(np.abs(a))) if a.size else 0.0
    clipped = int(np.count_nonzero(np.abs(a) > 1.0))
    if clipped:
        # Out-of-range input is clamped, not rejected: real captures do this,
        # and silently letting >1.0 through would corrupt int16 conversion.
        a = np.clip(a, -1.0, 1.0)

    meta = AudioMeta(
        source=source, original_sample_rate=int(sr), original_channels=int(orig_channels),
        original_frames=int(orig_frames), duration_s=round(duration_s, 4),
        normalized_samples=int(a.size), normalized_sample_rate=TARGET_SR,
        resampled=bool(resampled), downmixed=bool(downmixed),
        peak_abs=round(peak, 6), clipped_samples=clipped,
    )
    return np.ascontiguousarray(a, dtype=np.float32), meta


def load_audio_file(path: str | Path) -> Tuple[np.ndarray, AudioMeta]:
    """Read a WAV/FLAC/etc. file into the internal representation."""
    import soundfile as sf

    p = Path(path)
    if not p.is_file():
        raise AudioIngestError(f"not a file: {p}")
    size = p.stat().st_size
    if size == 0:
        raise AudioIngestError("empty file")
    if size > MAX_FILE_BYTES:
        raise AudioIngestError(f"file too large: {size} bytes")
    try:
        audio, sr = sf.read(str(p), dtype="float32", always_2d=False)
    except Exception as e:
        # Covers truncated or malformed containers and unsupported codecs.
        raise AudioIngestError(f"cannot decode audio: {e}") from e
    return normalize_array(audio, sr, source=p.name)


def to_int16_pcm(audio: np.ndarray) -> bytes:
    """Internal float32 [-1,1] → little-endian int16 PCM, the wire format."""
    a = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    return (a * 32767.0).astype("<i2").tobytes()


def iter_pcm_chunks(audio: np.ndarray, chunk_ms: int,
                    sample_rate: int = TARGET_SR) -> Iterator[bytes]:
    """
    Split internal audio into fixed-duration int16 PCM chunks.

    The final chunk is emitted even when short — a real stream ends mid-chunk,
    and the windower is responsible for deciding whether enough audio exists.
    """
    if chunk_ms <= 0:
        raise AudioIngestError("chunk_ms must be positive")
    n = max(1, int(sample_rate * chunk_ms / 1000))
    for start in range(0, len(audio), n):
        piece = audio[start:start + n]
        if piece.size:
            yield to_int16_pcm(piece)
