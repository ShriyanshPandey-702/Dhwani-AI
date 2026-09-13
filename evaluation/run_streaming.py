#!/usr/bin/env python3
"""
Streaming score stability on the REAL model, through the production windower.

Builds streams from real ASVspoof audio — including bona-fide↔spoof splices —
pushes them frame by frame through the deployed `StreamWindower`, scores every
emitted window, and measures stability, delay and spurious alerts.

    python evaluation/run_streaming.py --asvspoof-root data/external/LA --threshold 0.5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.datasets import asvspoof  # noqa: E402
from evaluation.datasets.base import BONAFIDE, SPOOF  # noqa: E402
from evaluation.runners.score import build_detector, load_audio, run_metadata  # noqa: E402
from evaluation.runners.streaming import (  # noqa: E402
    compare_aggregators, concat_with_transition, count_isolated_flips,
    decisions_confirm, detection_delay, run_stream,
)

SEED = 1337
SR = 16000


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def pad_to(audio: np.ndarray, seconds: float) -> np.ndarray:
    """Loop a clip up to `seconds` so a stream has enough windows to analyse."""
    need = int(SR * seconds)
    if audio.size >= need:
        return audio[:need]
    reps = int(need / max(1, audio.size)) + 1
    return np.tile(audio, reps)[:need]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--asvspoof-root", required=True)
    ap.add_argument("--variant", default="AASIST-L")
    ap.add_argument("--threshold", type=float, required=True,
                    help="operating threshold chosen on the calibration split")
    ap.add_argument("--n-streams", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--out", default="evaluation/results")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()

    tag = args.tag or time.strftime("streaming_%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    import random

    rng = random.Random(SEED)
    samples = asvspoof.load_split(args.asvspoof_root, "eval")
    bona = [s for s in samples if s.label == BONAFIDE]
    spoof = [s for s in samples if s.label == SPOOF]
    log(f"eval pool: {len(bona)} bona fide, {len(spoof)} spoof")

    detector = build_detector(variant=args.variant, cascade=False)
    from app.ml.preprocessing.stream import StreamWindower
    from app.core.config import settings

    windower = StreamWindower(window_ms=settings.ANALYSIS_WINDOW_MS,
                              hop_ms=settings.ANALYSIS_HOP_MS)
    log(f"windower: {windower.window_samples} samples / hop {windower.hop_samples}")

    results = {"threshold": args.threshold, "streams": [], "transitions": [],
               "edge_cases": {}}

    # ── Steady streams: pure bona fide, pure spoof ───────────────────────────
    for kind, pool in (("bonafide", bona), ("spoof", spoof)):
        for i in range(args.n_streams // 2):
            pick = rng.choice(pool)
            audio = load_audio(pick.audio_path)
            if audio is None:
                continue
            stream = run_stream(pad_to(audio, args.seconds), detector, windower,
                                session=f"{kind}-{i}", name=f"{kind}-{i}")
            stats = stream.stats()
            stats["kind"] = kind
            stats["aggregators"] = compare_aggregators(stream.scores, args.threshold)
            decisions = [int(s >= args.threshold) for s in stream.scores]
            stats["isolated_flips_raw"] = count_isolated_flips(decisions)
            stats["decision_rate"] = float(np.mean(decisions)) if decisions else None
            results["streams"].append(stats)
            log(f"  {kind}-{i}: n={stats['n']} mean={stats.get('mean', 0):.3f} "
                f"std={stats.get('std', 0):.3f} jitter={stats.get('jitter_mean_abs_delta', 0):.3f} "
                f"flips={stats['isolated_flips_raw']}")

    # ── Transitions: bona fide → spoof and back ──────────────────────────────
    for name, first_pool, second_pool in (("bonafide_to_spoof", bona, spoof),
                                          ("spoof_to_bonafide", spoof, bona)):
        a = load_audio(rng.choice(first_pool).audio_path)
        b = load_audio(rng.choice(second_pool).audio_path)
        if a is None or b is None:
            continue
        half = args.seconds / 2
        stream_audio = concat_with_transition(pad_to(a, half), pad_to(b, half))
        stream = run_stream(stream_audio, detector, windower, session=name, name=name)
        transition_frame = int(half)          # frames are 1 s
        decisions_raw = [int(s >= args.threshold) for s in stream.scores]
        decisions_c2 = decisions_confirm(stream.scores, args.threshold, 2)

        entry = {
            "name": name,
            "scores": [round(s, 4) for s in stream.scores],
            "transition_at_frame": transition_frame,
            "windows_scored": stream.windows_scored,
            "delay_raw_s": detection_delay(stream.scores, decisions_raw,
                                           transition_frame, settings.ANALYSIS_HOP_MS),
            "delay_confirm2_s": detection_delay(stream.scores, decisions_c2,
                                                transition_frame, settings.ANALYSIS_HOP_MS),
            "isolated_flips_raw": count_isolated_flips(decisions_raw),
            "isolated_flips_confirm2": count_isolated_flips(decisions_c2),
        }
        results["transitions"].append(entry)
        log(f"  {name}: delay_raw={entry['delay_raw_s']} "
            f"delay_confirm2={entry['delay_confirm2_s']} "
            f"flips {entry['isolated_flips_raw']}→{entry['isolated_flips_confirm2']}")

    # ── Edge cases: silence, short speech, noisy speech ──────────────────────
    from evaluation.robustness.transforms import add_noise

    clean = pad_to(load_audio(rng.choice(bona).audio_path), args.seconds)
    edge = {
        "silence": np.zeros(int(SR * args.seconds), dtype=np.float32),
        "short_speech_2s": pad_to(clean, 2.0),
        "noisy_5db": add_noise(clean, 5, seed=SEED),
        "speech_then_silence": np.concatenate(
            [pad_to(clean, args.seconds / 2), np.zeros(int(SR * args.seconds / 2), np.float32)]),
    }
    for name, audio in edge.items():
        stream = run_stream(audio, detector, windower, session=f"edge-{name}", name=name)
        results["edge_cases"][name] = stream.stats()
        log(f"  edge {name}: windows_scored={stream.windows_scored} "
            f"no_window={stream.skipped_no_window} no_evidence={stream.skipped_no_evidence}")

    (out_dir / "streaming.json").write_text(json.dumps(results, indent=2, default=float))
    (out_dir / "run_metadata.json").write_text(json.dumps(
        run_metadata(detector, extra={"run_tag": tag, "seed": SEED,
                                      "threshold": args.threshold,
                                      "stream_seconds": args.seconds}),
        indent=2, default=str))
    log(f"done → {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
