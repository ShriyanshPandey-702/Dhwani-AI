#!/usr/bin/env python3
"""
Phase 1.8 — Paired Pipeline Robustness Evaluation Runner.
=========================================================
Evaluates the frozen VoiceShield streaming pipeline across 19 canonical
acoustic and transmission degradation conditions using STRICT PAIRED EVALUATION:

Conditions (19 total):
  BASELINE:         clean
  NOISE:            noise_white_20db, noise_white_10db, noise_white_5db, noise_white_0db,
                    noise_pink_10db, noise_babble_10db
  TELEPHONY:        resample_8k, lowpass_4k, lowpass_3k4, telephone_band, mu_law, telephone_chain
  GAIN/DISTORTION:  gain_minus_20db, gain_plus_6db, clipping
  ACOUSTICS:        reverb_300ms
  NETWORK:          packet_loss_2pct, packet_loss_5pct

For each audio sample:
  1. Evaluate clean baseline through streaming pipeline.
  2. For each degraded condition, transform audio and evaluate through pipeline.
  3. Compute paired deltas: delta_aasist, delta_risk, decision flips, policy transitions.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(API_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Invariant check must run first
from evaluation.runners.invariant_check import verify_invariants

from app.core.config import settings
settings.MODEL_DIR = str(API_ROOT / "models")
settings.PIPELINE_MODE = "real_ml"

from app.ml.preprocessing.audio import decode_pcm
from app.ml.preprocessing.ingest import load_audio_file, iter_pcm_chunks
from app.ml.preprocessing.stream import SAMPLE_RATE
from evaluation.datasets.base import BONAFIDE, SPOOF, Sample, label_distribution
from evaluation.datasets.multidomain_loader import (
    SEED,
    load_asvspoof_eval,
    load_inthewild,
)
from app.risk.engine import EvidenceBundle, compute_risk
from app.risk.policy import evaluate
from evaluation.metrics.detection import eer, roc_auc, metrics_at
from evaluation.robustness.transforms import CONDITIONS, apply_condition
from evaluation.run_pipeline_multidomain import PipelineEvaluator


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_robustness_evaluation(
    out_dir: Path,
    samples_per_class: int = 50,
    seed: int = SEED,
    limit_samples: Optional[int] = None,
    conditions_subset: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute paired robustness evaluation across the 19 conditions."""
    verify_invariants(strict=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    conditions = conditions_subset or list(CONDITIONS.keys())
    assert "clean" in conditions, "Canonical conditions must include 'clean' baseline"

    # Select representative canonical evaluation subset:
    # Balanced bona-fide and spoof from in-domain (ASVspoof) and out-of-domain (InTheWild)
    log("Loading balanced representative samples for robustness benchmarking...")
    half = max(1, samples_per_class // 2)
    asv_bundle = load_asvspoof_eval(per_class=half, seed=seed)
    itw_bundle = load_inthewild(per_class=half, seed=seed)

    selected_samples: List[Sample] = asv_bundle.samples + itw_bundle.samples
    if limit_samples:
        selected_samples = selected_samples[:limit_samples]

    log(f"Selected {len(selected_samples)} samples across 19 degradation conditions.")
    log(f"Distribution: {label_distribution(selected_samples)}")

    evaluator = PipelineEvaluator()
    if asv_bundle.enrollment_refs:
        evaluator.pre_enroll_speakers(asv_bundle.enrollment_refs)
    if itw_bundle.enrollment_refs:
        evaluator.pre_enroll_speakers(itw_bundle.enrollment_refs)

    # Per-window rows for all condition evaluations
    all_window_rows: List[Dict[str, Any]] = []
    # Paired sample comparison records
    paired_records: List[Dict[str, Any]] = []

    t_eval_start = time.perf_counter()

    for s_idx, sample in enumerate(selected_samples):
        log(f"Evaluating sample {s_idx + 1}/{len(selected_samples)}: {Path(sample.audio_path).name} (label={sample.label})")
        clean_audio, meta = load_audio_file(sample.audio_path)

        # Baseline clean evaluation
        clean_sess = f"rob-clean-{s_idx:04d}"
        clean_windows, clean_summary = evaluator.evaluate_stream(sample, session_id=clean_sess)
        for w in clean_windows:
            w["condition"] = "clean"
            all_window_rows.append(w)

        clean_mean_aasist = clean_summary["mean_aasist_l_score"]
        clean_mean_risk = clean_summary["mean_risk_score"]
        clean_decision = clean_summary["final_decision"]
        clean_transcript = " ".join(w["stt_transcript"] for w in clean_windows if w["stt_transcript"])

        # Degraded condition evaluations
        for cond_name in conditions:
            if cond_name == "clean":
                continue

            # Apply deterministic condition transform
            degraded_audio = apply_condition(cond_name, clean_audio, seed=seed + s_idx)

            # Create transient in-memory sample representing transformed audio
            # We stream the degraded audio by passing it through evaluate_stream directly
            # To do so without disk I/O, we can use an evaluator helper or transient session
            cond_sess = f"rob-{cond_name}-{s_idx:04d}"

            # Ensure minimum stream duration via standard upstream tiling
            min_samples = int(SAMPLE_RATE * 5.0)
            audio_buf = degraded_audio
            if len(audio_buf) < min_samples:
                reps = int(min_samples / max(1, len(audio_buf))) + 1
                audio_buf = np.tile(audio_buf, reps)[:min_samples]

            chunks = list(iter_pcm_chunks(audio_buf, chunk_ms=250))
            evaluator.windower.reset(cond_sess)

            ref_emb = None
            if sample.speaker_id and sample.speaker_id in evaluator.enrolled_embeddings:
                ref_emb = evaluator.enrolled_embeddings[sample.speaker_id]

            deg_windows: List[Dict[str, Any]] = []
            win_idx = 0
            in_band_ref = None

            for chunk_bytes in chunks:
                chunk_np = decode_pcm(chunk_bytes)
                if chunk_np is None:
                    continue
                window = evaluator.windower.push(cond_sess, chunk_np)
                if window is None:
                    continue

                win_idx += 1
                t0 = time.perf_counter()
                prod_score = evaluator.aasist.score(window)
                aasist_raw = prod_score.synthetic_probability

                ecapa_sim = None
                if ref_emb is not None:
                    live_emb = evaluator.ecapa.embed(window)
                    ecapa_sim = float(np.dot(live_emb, ref_emb))
                else:
                    if in_band_ref is None:
                        in_band_ref = evaluator.ecapa.embed(window)
                        ecapa_sim = 1.0
                    else:
                        live_emb = evaluator.ecapa.embed(window)
                        ecapa_sim = float(np.dot(live_emb, in_band_ref))

                seg = evaluator.stt.transcribe(cond_sess, window)
                stt_text = seg.text if seg else ""

                ctx = evaluator.context_classifier.classify(
                    cond_sess, stt_text, transcript_is_mock=False,
                    transcript_model="faster-whisper-tiny", transcript_pipeline_mode="real_ml"
                )
                ctx_risk = (ctx.score / 100.0) if ctx else 0.0
                consequence = ctx.consequence if ctx else "low"

                bundle = EvidenceBundle(
                    authenticity=prod_score.synthetic_probability,
                    authenticity_confidence=prod_score.model_confidence,
                    identity_similarity=ecapa_sim,
                    identity_confidence=0.70 if ecapa_sim is not None else 0.0,
                    context_risk=ctx_risk,
                    context_confidence=0.60 if stt_text else 0.0,
                    consequence=consequence,
                )
                risk_res = compute_risk(bundle, evaluator.policy_config)
                policy_dec = evaluate(
                    risk_state=risk_res.state, consequence=consequence,
                    reasons=risk_res.reasons, evidence_confidence=risk_res.evidence_confidence,
                    policy_config=evaluator.policy_config,
                )

                win_rec = {
                    "dataset": sample.dataset,
                    "sample_id": Path(sample.audio_path).stem,
                    "condition": cond_name,
                    "ground_truth_label": sample.label,
                    "window_idx": win_idx,
                    "aasist_l_score": round(aasist_raw, 4),
                    "prod_authenticity_score": round(prod_score.synthetic_probability, 4),
                    "ecapa_similarity": round(ecapa_sim, 4) if ecapa_sim is not None else "N/A",
                    "stt_transcript": stt_text,
                    "risk_score": risk_res.score,
                    "risk_state": risk_res.state,
                    "policy_decision": policy_dec.decision,
                }
                deg_windows.append(win_rec)
                all_window_rows.append(win_rec)

            deg_mean_aasist = round(float(np.mean([w["aasist_l_score"] for w in deg_windows])), 4) if deg_windows else clean_mean_aasist
            deg_mean_risk = round(float(np.mean([w["risk_score"] for w in deg_windows])), 2) if deg_windows else clean_mean_risk
            deg_decision = deg_windows[-1]["policy_decision"] if deg_windows else "NO_WINDOW"
            deg_transcript = " ".join(w["stt_transcript"] for w in deg_windows if w["stt_transcript"])

            paired_records.append({
                "sample_id": Path(sample.audio_path).stem,
                "dataset": sample.dataset,
                "ground_truth_label": sample.label,
                "condition": cond_name,
                "clean_aasist": clean_mean_aasist,
                "degraded_aasist": deg_mean_aasist,
                "delta_aasist": round(deg_mean_aasist - clean_mean_aasist, 4),
                "clean_risk": clean_mean_risk,
                "degraded_risk": deg_mean_risk,
                "delta_risk": round(deg_mean_risk - clean_mean_risk, 2),
                "clean_decision": clean_decision,
                "degraded_decision": deg_decision,
                "decision_flipped": deg_decision != clean_decision,
                "flip_type": f"{clean_decision}->{deg_decision}",
                "clean_transcript_len": len(clean_transcript),
                "degraded_transcript_len": len(deg_transcript),
                "transcript_lost": bool(clean_transcript and not deg_transcript),
            })

    total_rob_time = round(time.perf_counter() - t_eval_start, 2)
    log(f"Robustness sweep finished in {total_rob_time}s across {len(paired_records)} paired evaluations.")

    # ── Write Outputs ─────────────────────────────────────────────────────────
    paired_csv = out_dir / "paired_deltas.csv"
    with open(paired_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(paired_records[0].keys()))
        writer.writeheader()
        for r in paired_records:
            writer.writerow(r)

    scores_csv = out_dir / "scores_robustness.csv"
    with open(scores_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(all_window_rows[0].keys()))
        writer.writeheader()
        for w in all_window_rows:
            writer.writerow(w)

    # ── Build Robustness Performance Matrix ───────────────────────────────────
    matrix: Dict[str, Any] = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "total_samples": len(selected_samples),
            "total_conditions": len(conditions),
            "total_eval_time_s": total_rob_time,
        },
        "conditions": {},
    }

    # Compute per-condition headline statistics
    for cond in conditions:
        cond_wins = [w for w in all_window_rows if w["condition"] == cond]
        cond_pairs = [p for p in paired_records if p["condition"] == cond]

        y = np.array([w["ground_truth_label"] for w in cond_wins], dtype=int)
        scores = np.array([w["aasist_l_score"] for w in cond_wins], dtype=float)

        eer_v, eer_t = (float("nan"), float("nan"))
        auc_v = float("nan")
        far_50 = float("nan")
        frr_50 = float("nan")

        if len(np.unique(y)) > 1:
            eer_v, eer_t = eer(y, scores)
            auc_v = roc_auc(y, scores)
            op = metrics_at(y, scores, threshold=0.50)
            far_50 = op.far * 100.0
            frr_50 = op.frr * 100.0

        mean_delta_aasist = float(np.mean([p["delta_aasist"] for p in cond_pairs])) if cond_pairs else 0.0
        mean_delta_risk = float(np.mean([p["delta_risk"] for p in cond_pairs])) if cond_pairs else 0.0
        flip_rate = (sum(1 for p in cond_pairs if p["decision_flipped"]) / len(cond_pairs) * 100.0) if cond_pairs else 0.0

        flips_dist: Dict[str, int] = {}
        for p in cond_pairs:
            if p["decision_flipped"]:
                flips_dist[p["flip_type"]] = flips_dist.get(p["flip_type"], 0) + 1

        matrix["conditions"][cond] = {
            "windows_scored": len(cond_wins),
            "eer_percent": round(eer_v * 100.0, 2) if not np.isnan(eer_v) else "N/A",
            "roc_auc": round(auc_v, 4) if not np.isnan(auc_v) else "N/A",
            "far_apcer_at_0_50": round(far_50, 2) if not np.isnan(far_50) else "N/A",
            "frr_bpcer_at_0_50": round(frr_50, 2) if not np.isnan(frr_50) else "N/A",
            "mean_delta_aasist": round(mean_delta_aasist, 4),
            "mean_delta_risk": round(mean_delta_risk, 2),
            "decision_flip_rate_pct": round(flip_rate, 2),
            "decision_flip_distribution": flips_dist,
        }

    matrix_path = out_dir / "paired_delta_matrix.json"
    with open(matrix_path, "w", encoding="utf-8") as fh:
        json.dump(matrix, fh, indent=2)

    log(f"Robustness results successfully written to {out_dir}:")
    log(f"  • {paired_csv.name}")
    log(f"  • {scores_csv.name}")
    log(f"  • {matrix_path.name}")

    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.8 Paired Pipeline Robustness Runner")
    parser.add_argument("--out", default="evaluation/results/phase1_8_robustness", help="Output directory")
    parser.add_argument("--samples-per-class", type=int, default=50, help="Balanced samples per class")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed")
    parser.add_argument("--limit", type=int, default=None, help="Limit total samples evaluated (for pilot)")
    args = parser.parse_args()

    run_robustness_evaluation(
        out_dir=Path(args.out),
        samples_per_class=args.samples_per_class,
        seed=args.seed,
        limit_samples=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
