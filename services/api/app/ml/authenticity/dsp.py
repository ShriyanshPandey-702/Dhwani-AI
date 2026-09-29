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


def safe_float(v: object, digits: int = 2) -> Optional[float]:
    """Ensure numerical safety: return a finite rounded float or None (never NaN/Inf)."""
    if v is None:
        return None
    try:
        f = float(v)  # type: ignore
        if not np.isfinite(f):
            return None
        return round(f, digits)
    except (ValueError, TypeError):
        return None


def estimate_pitch_f0(
    audio: Optional[np.ndarray],
    sample_rate: int = 16000,
    frame_len_s: float = 0.03,
    hop_len_s: float = 0.015,
    fmin: float = 65.0,
    fmax: float = 500.0,
) -> Optional[dict]:
    """
    Lightweight, genuine fundamental-frequency (F0) analysis using normalized
    autocorrelation across short sliding frames.

    Requirements enforced:
      * Evaluates F0 only when there is sufficient voiced speech.
      * Pure numpy computation without new external dependencies.
      * Does NOT alter risk scores (evidence/diagnostic only).
      * Returns None (unavailable) when speech is insufficient or unvoiced.
      * Guaranteed numerical safety (no NaN/Inf).
    """
    if audio is None or len(audio) < int(sample_rate * 0.1):
        return None

    frame_samples = int(sample_rate * frame_len_s)
    hop_samples = int(sample_rate * hop_len_s)
    min_lag = int(sample_rate / fmax)
    max_lag = int(sample_rate / fmin)

    n_frames = (len(audio) - frame_samples) // hop_samples + 1
    if n_frames < 4 or max_lag <= min_lag:
        return None

    rms_total = float(np.sqrt(np.mean(audio**2) + 1e-12))
    if rms_total < 1e-4:
        return None
    silence_thresh = max(1e-4, 0.08 * rms_total)

    f0_list = []
    voiced_flags = []

    for i in range(n_frames):
        start = i * hop_samples
        frame = audio[start : start + frame_samples]
        rms_frame = float(np.sqrt(np.mean(frame**2) + 1e-12))
        if rms_frame < silence_thresh:
            voiced_flags.append(False)
            continue

        corr = np.correlate(frame, frame, mode="full")
        corr = corr[len(frame) - 1 :]
        if corr[0] <= 1e-12:
            voiced_flags.append(False)
            continue

        norm_corr = corr / corr[0]
        search_region = norm_corr[min_lag:max_lag]
        if len(search_region) == 0:
            voiced_flags.append(False)
            continue

        peak_idx = int(np.argmax(search_region))
        peak_val = float(search_region[peak_idx])
        lag = min_lag + peak_idx

        # Normalized autocorrelation peak > 0.35 indicates periodic/voiced speech
        if peak_val > 0.35 and lag > 0:
            pitch = float(sample_rate / lag)
            f0_list.append(pitch)
            voiced_flags.append(True)
        else:
            voiced_flags.append(False)

    if len(f0_list) < 3 or len(voiced_flags) == 0:
        return None

    f0_arr = np.array(f0_list, dtype=np.float64)
    voiced_ratio = float(np.mean(voiced_flags))
    if voiced_ratio < 0.05:
        return None

    mean_f0 = float(np.mean(f0_arr))
    std_f0 = float(np.std(f0_arr))
    var_f0 = float(np.var(f0_arr))
    min_f0 = float(np.min(f0_arr))
    max_f0 = float(np.max(f0_arr))

    return {
        "mean_f0_hz": safe_float(mean_f0, 1),
        "f0_std_hz": safe_float(std_f0, 1),
        "f0_variance": safe_float(var_f0, 1),
        "f0_min_hz": safe_float(min_f0, 1),
        "f0_max_hz": safe_float(max_f0, 1),
        "voiced_frame_ratio": safe_float(voiced_ratio, 3),
    }


def analyze_rhythm_and_pauses(
    audio: Optional[np.ndarray],
    sample_rate: int = 16000,
    frame_len_s: float = 0.02,
    hop_len_s: float = 0.01,
) -> Optional[dict]:
    """
    Rhythm and pause analysis computed from short-term frame energy dynamics.
    Quantifies pause duration, pause frequency, and speech-to-pause ratios.
    """
    if audio is None or len(audio) < int(sample_rate * 0.2):
        return None

    frame_samples = int(sample_rate * frame_len_s)
    hop_samples = int(sample_rate * hop_len_s)
    n_frames = (len(audio) - frame_samples) // hop_samples + 1
    if n_frames < 10:
        return None

    frames = np.lib.stride_tricks.sliding_window_view(audio, frame_samples)[::hop_samples]
    energies = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)

    rms_total = float(np.sqrt(np.mean(audio**2) + 1e-12))
    if rms_total < 1e-4:
        return None

    # Adaptive speech threshold relative to RMS energy
    speech_thresh = max(1e-4, 0.15 * rms_total)
    is_speech = energies >= speech_thresh

    speech_segments = []
    pause_segments = []
    current_state = bool(is_speech[0])
    current_len = 1

    for val in is_speech[1:]:
        val_bool = bool(val)
        if val_bool == current_state:
            current_len += 1
        else:
            duration_ms = current_len * (hop_len_s * 1000.0)
            if current_state:
                speech_segments.append(duration_ms)
            else:
                pause_segments.append(duration_ms)
            current_state = val_bool
            current_len = 1

    final_ms = current_len * (hop_len_s * 1000.0)
    if current_state:
        speech_segments.append(final_ms)
    else:
        pause_segments.append(final_ms)

    sig_pauses = [p for p in pause_segments if p >= 60.0]
    sig_speech = [s for s in speech_segments if s >= 80.0]

    total_speech_ms = sum(speech_segments)
    total_pause_ms = sum(pause_segments)

    if total_speech_ms < 100.0:
        return None

    avg_speech = float(np.mean(sig_speech)) if sig_speech else float(np.mean(speech_segments))
    avg_pause = float(np.mean(sig_pauses)) if sig_pauses else (float(np.mean(pause_segments)) if pause_segments else 0.0)
    longest_pause = float(max(pause_segments)) if pause_segments else 0.0
    pause_ratio = total_pause_ms / (total_speech_ms + total_pause_ms + 1e-9)
    speech_to_pause = total_speech_ms / (total_pause_ms + 1e-9)

    return {
        "speech_segment_count": len(sig_speech) if sig_speech else len(speech_segments),
        "total_speech_duration_ms": int(round(total_speech_ms)),
        "total_pause_duration_ms": int(round(total_pause_ms)),
        "pause_count": len(sig_pauses),
        "average_speech_duration_ms": safe_float(avg_speech, 1),
        "average_pause_duration_ms": safe_float(avg_pause, 1),
        "longest_pause_duration_ms": safe_float(longest_pause, 1),
        "pause_to_speech_ratio": safe_float(pause_ratio, 3),
        "speech_to_pause_ratio": safe_float(speech_to_pause, 2),
    }


def analyze_microvariation(
    audio: Optional[np.ndarray],
    sample_rate: int = 16000,
    f0_stats: Optional[dict] = None,
) -> Optional[dict]:
    """
    Microvariation analysis using frame-level audio statistics:
    - short-term energy variability across voiced frames
    - zero-crossing rate variability
    - spectral centroid variability across frames
    - fundamental-frequency (F0) variability if F0 is available
    """
    if audio is None or len(audio) < int(sample_rate * 0.1):
        return None

    frame_samples = max(1, int(sample_rate * 0.02))
    n = len(audio) // frame_samples
    if n < 4:
        return None

    frames = audio[: n * frame_samples].reshape(n, frame_samples)
    energy = np.sqrt(np.mean(frames**2, axis=1) + 1e-12)
    mean_energy = float(np.mean(energy))
    if mean_energy < 1e-5:
        return None

    mask = energy >= 0.35 * mean_energy
    if int(np.count_nonzero(mask)) < 4:
        return None

    voiced_energy = energy[mask]
    energy_var = float(np.std(voiced_energy) / (np.mean(voiced_energy) + 1e-9))

    voiced_frames = frames[mask]
    zcr = np.mean(np.abs(np.diff(np.sign(voiced_frames), axis=1)) > 0, axis=1)
    zcr_var = float(np.std(zcr) / (np.mean(zcr) + 1e-9))

    window = np.hanning(frame_samples)
    mags = np.abs(np.fft.rfft(voiced_frames * window, axis=1)) + 1e-12
    freqs = np.fft.rfftfreq(frame_samples, d=1.0 / sample_rate)
    centroids = np.sum(freqs * mags, axis=1) / np.sum(mags, axis=1)
    spectral_var = float(np.std(centroids) / (np.mean(centroids) + 1e-9))

    f0_var = None
    if f0_stats and f0_stats.get("mean_f0_hz") and f0_stats.get("f0_std_hz"):
        mean_val = f0_stats["mean_f0_hz"]
        std_val = f0_stats["f0_std_hz"]
        if mean_val and mean_val > 0 and std_val is not None:
            f0_var = safe_float(std_val / mean_val, 3)

    return {
        "status": "available",
        "energy_variability": safe_float(energy_var, 3),
        "energy_variation": safe_float(energy_var, 3),
        "zcr_variability": safe_float(zcr_var, 3),
        "zcr_variation": safe_float(zcr_var, 3),
        "spectral_variability": safe_float(spectral_var, 3),
        "spectral_variation": safe_float(spectral_var, 3),
        "f0_variability": f0_var,
        "f0_variation": f0_var,
        "jitter_shimmer_status": "not_implemented (frame-level microvariation computed)",
    }


def analyze_prosody(
    audio: Optional[np.ndarray],
    sample_rate: int = 16000,
    f0_data: Optional[dict] = None,
    rhythm_data: Optional[dict] = None,
    micro_data: Optional[dict] = None,
) -> Optional[dict]:
    """
    Prosody evidence combining pitch contours, energy envelope, rhythm, and pauses.
    Supporting evidence only; does not independently prove or disprove synthetic speech.
    """
    if audio is None or len(audio) < int(sample_rate * 0.1):
        return None

    if f0_data is None:
        f0_data = estimate_pitch_f0(audio, sample_rate)
    if rhythm_data is None:
        rhythm_data = analyze_rhythm_and_pauses(audio, sample_rate)
    if micro_data is None:
        micro_data = analyze_microvariation(audio, sample_rate, f0_stats=f0_data)

    if not f0_data and not rhythm_data and not micro_data:
        return None

    pitch_var = None
    if f0_data and f0_data.get("mean_f0_hz") and f0_data.get("f0_std_hz"):
        mean_val = f0_data["mean_f0_hz"]
        std_val = f0_data["f0_std_hz"]
        if mean_val and mean_val > 0 and std_val is not None:
            pitch_var = safe_float(std_val / mean_val, 3)

    return {
        "mean_f0_hz": f0_data.get("mean_f0_hz") if f0_data else None,
        "f0_std_hz": f0_data.get("f0_std_hz") if f0_data else None,
        "f0_min_hz": f0_data.get("f0_min_hz") if f0_data else None,
        "f0_max_hz": f0_data.get("f0_max_hz") if f0_data else None,
        "pitch_variability": pitch_var,
        "energy_variability": micro_data.get("energy_variability") if micro_data else None,
        "voiced_ratio": f0_data.get("voiced_frame_ratio") if f0_data else None,
        "speech_segment_count": rhythm_data.get("speech_segment_count") if rhythm_data else None,
        "average_speech_duration_ms": rhythm_data.get("average_speech_duration_ms") if rhythm_data else None,
        "average_pause_duration_ms": rhythm_data.get("average_pause_duration_ms") if rhythm_data else None,
        "longest_pause_duration_ms": rhythm_data.get("longest_pause_duration_ms") if rhythm_data else None,
        "pause_ratio": rhythm_data.get("pause_to_speech_ratio") if rhythm_data else None,
        "note": "Supporting evidence only; does not independently prove or disprove synthetic speech.",
    }


def extract_spectral_details(
    audio: Optional[np.ndarray],
    sample_rate: int = 16000,
) -> Optional[dict]:
    """Extract fine-grained spectral features: centroid (Hz) and flatness."""
    if audio is None or len(audio) < 64:
        return None
    n = min(len(audio), 8192)
    window = audio[:n] * np.hanning(n)
    mag = np.abs(np.fft.rfft(window)) + 1e-12
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)

    centroid = float(np.sum(freqs * mag) / np.sum(mag))
    geo = float(np.exp(np.mean(np.log(mag))))
    arith = float(np.mean(mag))
    flatness = float(geo / (arith + 1e-12))

    return {
        "centroid_hz": safe_float(centroid, 1),
        "flatness": safe_float(flatness, 4),
        "spectral_anomaly": band(spectral_anomaly(audio, sample_rate)),
    }


def extract_dsp_evidence(
    audio: Optional[np.ndarray],
    sample_rate: int = 16000,
) -> dict:
    """
    Extract all measurable DSP evidence features in a unified pass.
    Preserves all existing anomaly bands and adds genuine pitch, rhythm, pause,
    prosody, and microvariation metrics.
    """
    if audio is None or len(audio) == 0:
        return {
            "bands": {"acoustic_anomaly": LOW, "spectral_anomaly": LOW, "prosody_anomaly": LOW},
            "pitch": None,
            "prosody": None,
            "rhythm": None,
            "pause_analysis": None,
            "microvariation": None,
            "spectral": None,
        }

    bands = anomaly_bands(audio, sample_rate)
    f0_stats = estimate_pitch_f0(audio, sample_rate)
    rhythm_pauses = analyze_rhythm_and_pauses(audio, sample_rate)
    micro = analyze_microvariation(audio, sample_rate, f0_stats=f0_stats)
    prosody = analyze_prosody(audio, sample_rate, f0_data=f0_stats, rhythm_data=rhythm_pauses, micro_data=micro)
    spectral = extract_spectral_details(audio, sample_rate)
    zcr_val = safe_float(np.mean(np.abs(np.diff(np.sign(audio))) > 0), 4) if len(audio) > 1 else None
    spectral_var = micro.get("spectral_variability") if micro else None

    # Enhanced spectral details with explicit metric names
    spectral_details = {
        "centroid_hz": spectral.get("centroid_hz") if spectral else None,
        "flatness": spectral.get("flatness") if spectral else None,
        "spectral_centroid": spectral.get("centroid_hz") if spectral else None,
        "spectral_flatness": spectral.get("flatness") if spectral else None,
        "zcr": zcr_val,
        "spectral_variation": spectral_var,
        "spectral_anomaly": spectral.get("spectral_anomaly") if spectral else LOW,
    }

    # Structured prosody sub-blocks with explicit status
    f0_block = {
        "mean": f0_stats.get("mean_f0_hz") if f0_stats else None,
        "min": f0_stats.get("f0_min_hz") if f0_stats else None,
        "max": f0_stats.get("f0_max_hz") if f0_stats else None,
        "std": f0_stats.get("f0_std_hz") if f0_stats else None,
        "voiced_ratio": f0_stats.get("voiced_frame_ratio") if f0_stats else None,
        "status": "available" if f0_stats else "unavailable",
    }
    if f0_stats:
        f0_block.update(f0_stats)

    speech_ms = rhythm_pauses.get("total_speech_duration_ms", 0) if rhythm_pauses else 0
    seg_count = rhythm_pauses.get("speech_segment_count", 0) if rhythm_pauses else 0
    speech_rate_proxy = safe_float(seg_count / (speech_ms / 1000.0 + 1e-6), 2) if speech_ms > 200 else None

    rhythm_block = {
        "segment_count": seg_count if rhythm_pauses else None,
        "average_segment_duration_ms": rhythm_pauses.get("average_speech_duration_ms") if rhythm_pauses else None,
        "average_pause_ms": rhythm_pauses.get("average_pause_duration_ms") if rhythm_pauses else None,
        "speech_to_pause_ratio": rhythm_pauses.get("speech_to_pause_ratio") if rhythm_pauses else None,
        "speech_rate_proxy": speech_rate_proxy,
        "status": "available" if rhythm_pauses else "unavailable",
    }
    if rhythm_pauses:
        rhythm_block.update({
            "speech_segment_count": rhythm_pauses.get("speech_segment_count"),
            "total_speech_duration_ms": rhythm_pauses.get("total_speech_duration_ms"),
            "average_speech_duration_ms": rhythm_pauses.get("average_speech_duration_ms"),
        })

    behavioral_block = {
        "energy_variability": micro.get("energy_variability") if micro else None,
        "zcr_variability": micro.get("zcr_variability") if micro else None,
        "status": "available" if micro else "unavailable",
    }

    if micro:
        micro["status"] = "available"
        micro["energy_variation"] = micro.get("energy_variability")
        micro["zcr_variation"] = micro.get("zcr_variability")
        micro["spectral_variation"] = micro.get("spectral_variability")
        micro["f0_variation"] = micro.get("f0_variability")

    return {
        "bands": bands,
        "pitch": f0_block if f0_stats else None,
        "prosody": prosody,
        "f0": f0_block,
        "speech_rhythm": rhythm_block,
        "behavioral": behavioral_block,
        "rhythm": rhythm_block if rhythm_pauses else None,
        "pause_analysis": {
            "pause_count": rhythm_pauses.get("pause_count") if rhythm_pauses else None,
            "total_pause_duration_ms": rhythm_pauses.get("total_pause_duration_ms") if rhythm_pauses else None,
            "average_pause_duration_ms": rhythm_pauses.get("average_pause_duration_ms") if rhythm_pauses else None,
            "longest_pause_duration_ms": rhythm_pauses.get("longest_pause_duration_ms") if rhythm_pauses else None,
            "pause_to_speech_ratio": rhythm_pauses.get("pause_to_speech_ratio") if rhythm_pauses else None,
        } if rhythm_pauses else None,
        "microvariation": micro,
        "spectral": spectral_details,
    }
