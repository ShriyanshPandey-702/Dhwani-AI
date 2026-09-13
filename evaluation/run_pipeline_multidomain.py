#!/usr/bin/env python3
"""
Phase 1.8 — Multi-Domain Streaming Pipeline Evaluation Runner.
============================================================
Evaluates the complete, authentic, frozen VoiceShield real-time pipeline across
the 5 local audio datasets:
  1. ASVspoof 2019 LA (official eval split)
  2. In-The-Wild (release_in_the_wild)
  3. MLAAD-tiny (local subset)
  4. WaveFake (test vocoders paired with exact LJSpeech utterances)
  5. LJSpeech-1.1 (standalone bona-fide speech)

Pipeline Flow:
Audio Stream -> 250ms PCM Chunks -> StreamWindower (64,608 / 16,000 / 80,608)
             -> AASIST-L Authenticity + ECAPA-TDNN Identity + faster-whisper STT
             -> Risk Engine Fusion -> Security Policy -> ALLOW / VERIFY / HOLD / BLOCK
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

# Resolve repo root and api path
REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "services" / "api"
for p in (str(API_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Invariant check must run first
from evaluation.runners.invariant_check import verify_invariants

from app.core.config import settings
# Ensure real ML models load checkpoints from services/api/models
settings.MODEL_DIR = str(API_ROOT / "models")
settings.PIPELINE_MODE = "real_ml"

from app.ml.authenticity.aasist import AASISTDetector, NB_SAMP
from app.ml.context.classifier import ContextClassifier
from app.ml.context.transcriber import Transcriber
from app.ml.identity.ecapa import ECAPAEmbedder
from app.ml.preprocessing.audio import decode_pcm, measure_quality
from app.ml.preprocessing.ingest import iter_pcm_chunks, load_audio_file
from app.ml.preprocessing.stream import SAMPLE_RATE, StreamWindower
from app.risk.engine import EvidenceBundle, compute_risk
from app.risk.policy import DEFAULT_POLICY_CONFIG, evaluate

from evaluation.datasets.base import BONAFIDE, SPOOF, Sample, label_distribution
from evaluation.datasets.multidomain_loader import (
    SEED,
    DatasetBundle,
    load_all_evaluation_datasets,
    load_asvspoof_eval,
    load_inthewild,
    load_ljspeech_standalone,
    load_mlaad_tiny,
    load_wavefake_paired,
)
from evaluation.metrics.detection import eer, pr_auc, roc_auc, metrics_at


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class PipelineEvaluator:
    """Encapsulates the loaded production ML models and executes streaming inference."""

    def __init__(self, device: str = "auto"):
        log("Initializing production ML components...")
        self.device = device
        self.windower = StreamWindower(
            window_ms=settings.ANALYSIS_WINDOW_MS,
            hop_ms=settings.ANALYSIS_HOP_MS,
        )
        self.aasist = AASISTDetector(
            model_dir=str(API_ROOT / "models"),
            variant="AASIST-L",
            cascade=True,
            device=device,
        )
        self.aasist.warmup()

        self.ecapa = ECAPAEmbedder(
            model_dir=str(API_ROOT / "models"),
            device=device,
        )
        self.ecapa.warmup()

        self.stt = Transcriber(pipeline_mode="real_ml")
        self.context_classifier = ContextClassifier()
        self.policy_config = dict(DEFAULT_POLICY_CONFIG)

        # Pre-computed speaker reference embeddings cache
        self.enrolled_embeddings: Dict[str, np.ndarray] = {}
        log("Production ML components initialized successfully.")

    def pre_enroll_speakers(self, enrollment_refs: Dict[str, str]) -> None:
        """Embed and cache reference genuine audio for each speaker."""
        log(f"Pre-enrolling {len(enrollment_refs)} speaker reference profiles...")
        for spk, path in enrollment_refs.items():
            if spk in self.enrolled_embeddings:
                continue
            try:
                audio, _ = load_audio_file(path)
                if len(audio) >= SAMPLE_RATE:
                    emb = self.ecapa.embed(audio)
                    self.enrolled_embeddings[spk] = emb
            except Exception as e:
                log(f"Warning: Failed to enroll speaker {spk} from {path}: {e}")

    def evaluate_stream(
        self,
        sample: Sample,
        session_id: str,
        chunk_ms: int = 250,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Stream one audio sample through StreamWindower and full pipeline.
        Returns:
          windows_data: list of dicts with per-window metrics & telemetry
          summary_data: dict with sample-level metrics & policy stability
        """
        self.windower.reset(session_id)
        audio, meta = load_audio_file(sample.audio_path)
        # If audio is shorter than the streaming window requirement (64,608 samples = 4.038s),
        # apply standard upstream tiling up to 5.0 seconds so StreamWindower accumulates at least 1 window.
        min_stream_samples = int(SAMPLE_RATE * 5.0)
        if len(audio) < min_stream_samples:
            reps = int(min_stream_samples / max(1, len(audio))) + 1
            audio = np.tile(audio, reps)[:min_stream_samples]

        chunks = list(iter_pcm_chunks(audio, chunk_ms=chunk_ms))

        # Determine speaker reference embedding
        ref_emb: Optional[np.ndarray] = None
        if sample.speaker_id and sample.speaker_id in self.enrolled_embeddings:
            ref_emb = self.enrolled_embeddings[sample.speaker_id]

        windows_data: List[Dict[str, Any]] = []
        window_idx = 0
        in_band_ref: Optional[np.ndarray] = None

        first_detection_s: Optional[float] = None
        decision_flips = 0
        last_decision: Optional[str] = None
        sample_error: Optional[str] = None

        t_session_start = time.perf_counter()

        for chunk_idx, pcm_bytes in enumerate(chunks):
            chunk_audio = decode_pcm(pcm_bytes)
            if chunk_audio is None:
                continue

            # Push chunk into production StreamWindower
            window = self.windower.push(session_id, chunk_audio)
            if window is None:
                continue

            # A full analysis window is emitted!
            window_idx += 1
            w_start_s = (window_idx - 1) * 1.0  # 1s hop
            w_end_s = w_start_s + 4.038

            t_win_start = time.perf_counter()

            # 1. AASIST-L Authenticity
            t0 = time.perf_counter()
            prod_score = self.aasist.score(window)
            aasist_l_raw = prod_score.synthetic_probability
            aasist_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            # 2. ECAPA-TDNN Speaker Identity
            t0 = time.perf_counter()
            ecapa_sim: Optional[float] = None
            if ref_emb is not None:
                live_emb = self.ecapa.embed(window)
                ecapa_sim = float(np.dot(live_emb, ref_emb))
            else:
                # In-band session reference (first window acts as call baseline)
                if in_band_ref is None:
                    in_band_ref = self.ecapa.embed(window)
                    ecapa_sim = 1.0
                else:
                    live_emb = self.ecapa.embed(window)
                    ecapa_sim = float(np.dot(live_emb, in_band_ref))
            ecapa_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            # 3. faster-whisper STT & Context Classifier
            t0 = time.perf_counter()
            seg = self.stt.transcribe(session_id, window)
            stt_text = seg.text if seg else ""
            stt_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            t0 = time.perf_counter()
            ctx = self.context_classifier.classify(
                session_id,
                stt_text,
                transcript_is_mock=False,
                transcript_model="faster-whisper-tiny",
                transcript_pipeline_mode="real_ml",
            )
            context_risk = (ctx.score / 100.0) if ctx else 0.0
            consequence = ctx.consequence if ctx else "low"
            context_flags = (
                [k for k in ("urgency", "financial_request", "otp_request",
                             "credential_request", "sensitive_information_request",
                             "social_engineering", "authority_claim")
                 if getattr(ctx, k, False)]
                if ctx else []
            )
            ctx_ms = round((time.perf_counter() - t0) * 1000.0, 2)

            # 4. Multimodal Fusion via Risk Engine
            t0 = time.perf_counter()
            bundle = EvidenceBundle(
                authenticity=prod_score.synthetic_probability,
                authenticity_confidence=prod_score.model_confidence,
                identity_similarity=ecapa_sim,
                identity_confidence=0.70 if ecapa_sim is not None else 0.0,
                context_risk=context_risk,
                context_confidence=0.60 if stt_text else 0.0,
                consequence=consequence,
            )
            risk_result = compute_risk(bundle, self.policy_config)

            # 5. Security Policy Evaluation
            policy_decision = evaluate(
                risk_state=risk_result.state,
                consequence=consequence,
                reasons=risk_result.reasons,
                evidence_confidence=risk_result.evidence_confidence,
                policy_config=self.policy_config,
            )
            fusion_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            win_total_ms = round((time.perf_counter() - t_win_start) * 1000.0, 2)

            curr_dec = policy_decision.decision
            if last_decision is not None and curr_dec != last_decision:
                decision_flips += 1
            last_decision = curr_dec

            if first_detection_s is None and curr_dec in ("VERIFY", "HOLD", "BLOCK"):
                first_detection_s = w_start_s

            win_record = {
                "dataset": sample.dataset,
                "sample_id": Path(sample.audio_path).stem,
                "audio_path": sample.audio_path,
                "speaker_id": sample.speaker_id or "unknown",
                "ground_truth_label": sample.label,
                "ground_truth_name": "bonafide" if sample.label == BONAFIDE else "spoof",
                "attack_type": sample.attack_type or "none",
                "system_id": sample.system_id or "none",
                "window_idx": window_idx,
                "window_start_s": round(w_start_s, 2),
                "window_end_s": round(w_end_s, 2),
                "aasist_l_score": round(aasist_l_raw, 4),
                "prod_authenticity_score": round(prod_score.synthetic_probability, 4),
                "authenticity_confidence": round(prod_score.model_confidence, 3),
                "ecapa_similarity": round(ecapa_sim, 4) if ecapa_sim is not None else "N/A",
                "stt_transcript": stt_text,
                "context_flags": ";".join(context_flags),
                "risk_score": risk_result.score,
                "risk_state": risk_result.state,
                "policy_decision": policy_decision.decision,
                "policy_action": policy_decision.action,
                "reasons": ";".join(policy_decision.reasons),
                "ms_aasist": aasist_ms,
                "ms_ecapa": ecapa_ms,
                "ms_stt": stt_ms,
                "ms_context": ctx_ms,
                "ms_fusion": fusion_ms,
                "ms_total": win_total_ms,
            }
            windows_data.append(win_record)

        summary_data = {
            "dataset": sample.dataset,
            "sample_id": Path(sample.audio_path).stem,
            "audio_path": sample.audio_path,
            "speaker_id": sample.speaker_id or "unknown",
            "ground_truth_label": sample.label,
            "ground_truth_name": "bonafide" if sample.label == BONAFIDE else "spoof",
            "duration_s": round(meta.duration_s, 2),
            "windows_count": window_idx,
            "first_decision": windows_data[0]["policy_decision"] if windows_data else "NO_WINDOW",
            "final_decision": windows_data[-1]["policy_decision"] if windows_data else "NO_WINDOW",
            "max_risk_score": max((w["risk_score"] for w in windows_data), default=0),
            "mean_risk_score": round(float(np.mean([w["risk_score"] for w in windows_data])), 2) if windows_data else 0.0,
            "mean_aasist_l_score": round(float(np.mean([w["aasist_l_score"] for w in windows_data])), 4) if windows_data else 0.0,
            "decision_flips": decision_flips,
            "time_to_detection_s": first_detection_s if first_detection_s is not None else "N/A",
            "detected": first_detection_s is not None,
            "error": sample_error,
        }

        return windows_data, summary_data


def run_multidomain_evaluation(
    out_dir: Path,
    per_class: int = 500,
    seed: int = SEED,
    target_dataset: Optional[str] = None,
    limit_samples: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute evaluation across selected or all datasets."""
    verify_invariants(strict=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    if target_dataset:
        if target_dataset == "asvspoof2019la":
            bundles = {"asvspoof2019la": load_asvspoof_eval(per_class=per_class, seed=seed)}
        elif target_dataset == "in_the_wild":
            bundles = {"in_the_wild": load_inthewild(per_class=per_class, seed=seed)}
        elif target_dataset == "mlaad_tiny":
            bundles = {"mlaad_tiny": load_mlaad_tiny(per_class=per_class, seed=seed)}
        elif target_dataset == "wavefake":
            bundles = {"wavefake": load_wavefake_paired(per_class=per_class, seed=seed)}
        elif target_dataset == "ljspeech":
            bundles = {"ljspeech": load_ljspeech_standalone(n_samples=per_class, seed=seed)}
        else:
            raise ValueError(f"Unknown dataset {target_dataset}")
    else:
        bundles = load_all_evaluation_datasets(per_class=per_class, seed=seed)

    evaluator = PipelineEvaluator()

    # Pre-enroll all available genuine speaker references
    for bundle in bundles.values():
        if bundle.enrollment_refs:
            evaluator.pre_enroll_speakers(bundle.enrollment_refs)

    all_windows: List[Dict[str, Any]] = []
    all_summaries: List[Dict[str, Any]] = []
    failed_files: List[Dict[str, str]] = []

    t_eval_start = time.perf_counter()

    for ds_name, bundle in bundles.items():
        log(f"--- Evaluating dataset: {ds_name} ({len(bundle.samples)} samples) ---")
        samples_to_run = bundle.samples[:limit_samples] if limit_samples else bundle.samples

        for i, sample in enumerate(samples_to_run):
            if (i + 1) % 50 == 0 or i == 0 or (i + 1) == len(samples_to_run):
                log(f"  [{ds_name}] {i + 1}/{len(samples_to_run)}: {Path(sample.audio_path).name} (label={sample.label})")

            session_id = f"eval-{ds_name}-{i:05d}"
            try:
                win_data, sum_data = evaluator.evaluate_stream(sample, session_id=session_id)
                all_windows.extend(win_data)
                all_summaries.extend([sum_data])
            except Exception as e:
                log(f"  ERROR processing {sample.audio_path}: {e}")
                failed_files.append({"dataset": ds_name, "path": sample.audio_path, "error": str(e)})

    total_eval_time_s = round(time.perf_counter() - t_eval_start, 2)
    log(f"Evaluation complete in {total_eval_time_s}s. Emitted {len(all_windows)} windows across {len(all_summaries)} files.")

    # ── Write Manifest & Scores ───────────────────────────────────────────────
    manifest_path = out_dir / "manifest_test.csv"
    with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["dataset", "sample_id", "audio_path", "speaker_id", "ground_truth_label",
                        "ground_truth_name", "duration_s", "windows_count", "first_decision",
                        "final_decision", "max_risk_score", "mean_risk_score", "mean_aasist_l_score",
                        "decision_flips", "time_to_detection_s", "detected", "error"]
        )
        writer.writeheader()
        for s in all_summaries:
            writer.writerow(s)

    scores_path = out_dir / "scores_pipeline.csv"
    if all_windows:
        with open(scores_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(all_windows[0].keys()))
            writer.writeheader()
            for w in all_windows:
                writer.writerow(w)

    # ── Compute Domain Metrics & Decision Matrix ──────────────────────────────
    decision_matrix: Dict[str, Any] = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "total_files_evaluated": len(all_summaries),
            "total_windows_emitted": len(all_windows),
            "total_eval_time_seconds": total_eval_time_s,
            "failed_files_count": len(failed_files),
            "failed_files": failed_files,
        },
        "scorecard": {},
        "decision_distributions": {},
    }

    for ds_name, bundle in bundles.items():
        ds_summaries = [s for s in all_summaries if s["dataset"] == ds_name]
        ds_windows = [w for w in all_windows if w["dataset"] == ds_name]
        if not ds_summaries:
            continue

        n_total = len(ds_summaries)
        n_bona = sum(1 for s in ds_summaries if s["ground_truth_label"] == BONAFIDE)
        n_spoof = sum(1 for s in ds_summaries if s["ground_truth_label"] == SPOOF)

        # Policy decision counts
        dec_counts = {"ALLOW": 0, "VERIFY": 0, "HOLD": 0, "BLOCK": 0, "NO_WINDOW": 0}
        for s in ds_summaries:
            dec_counts[s["final_decision"]] = dec_counts.get(s["final_decision"], 0) + 1

        scorecard_entry: Dict[str, Any] = {
            "samples_total": n_total,
            "bonafide_count": n_bona,
            "spoof_count": n_spoof,
            "windows_count": len(ds_windows),
            "decision_distribution": dec_counts,
        }

        # Authenticity metrics (Valid only if both bona-fide and spoof exist in windows)
        y_win = np.array([w["ground_truth_label"] for w in ds_windows], dtype=int) if ds_windows else np.array([], dtype=int)
        scores_win = np.array([w["aasist_l_score"] for w in ds_windows], dtype=float) if ds_windows else np.array([], dtype=float)
        both_classes_in_windows = len(np.unique(y_win)) > 1 if len(y_win) > 0 else False

        if bundle.metric_capabilities.get("authenticity", False) and both_classes_in_windows:

            eer_val, eer_thresh = eer(y_win, scores_win)
            roc_auc_val = roc_auc(y_win, scores_win)
            pr_auc_val = pr_auc(y_win, scores_win)

            # Operating point at fixed decision threshold = 0.50
            op = metrics_at(y_win, scores_win, threshold=0.50)

            scorecard_entry["authenticity_metrics"] = {
                "eer_percent": round(eer_val * 100.0, 2),
                "eer_threshold": round(eer_thresh, 4),
                "roc_auc": round(roc_auc_val, 4),
                "pr_auc": round(pr_auc_val, 4),
                "far_apcer_at_0_50": round(op.far * 100.0, 2),
                "frr_bpcer_at_0_50": round(op.frr * 100.0, 2),
                "accuracy_at_0_50": round(op.accuracy * 100.0, 2),
            }
        else:
            scorecard_entry["authenticity_metrics"] = {
                "eer_percent": "N/A — single class or insufficient metadata",
                "roc_auc": "N/A — single class or insufficient metadata",
                "pr_auc": "N/A — single class or insufficient metadata",
                "far_apcer_at_0_50": "N/A" if n_spoof == 0 else "computable",
                "frr_bpcer_at_0_50": round(float(np.mean([w["aasist_l_score"] >= 0.5 for w in ds_windows])) * 100.0, 2) if n_bona > 0 else "N/A",
                "note": bundle.notes,
            }

        # ECAPA speaker verification metrics
        if bundle.metric_capabilities.get("speaker_verification_fmr_fnmr", False):
            # Compute matched genuine vs impostor cosine similarities
            valid_wins = [w for w in ds_windows if w["ecapa_similarity"] != "N/A"]
            matched_sims = [w["ecapa_similarity"] for w in valid_wins if w["ground_truth_label"] == BONAFIDE]
            spoof_sims = [w["ecapa_similarity"] for w in valid_wins if w["ground_truth_label"] == SPOOF]

            scorecard_entry["ecapa_speaker_verification"] = {
                "evaluated": True,
                "mean_genuine_similarity": round(float(np.mean(matched_sims)), 4) if matched_sims else "N/A",
                "mean_clone_spoof_similarity": round(float(np.mean(spoof_sims)), 4) if spoof_sims else "N/A",
                "std_genuine_similarity": round(float(np.std(matched_sims)), 4) if matched_sims else "N/A",
            }
        else:
            scorecard_entry["ecapa_speaker_verification"] = {
                "evaluated": False,
                "status": "N/A — speaker metadata insufficient or single-speaker corpus",
                "reason": bundle.notes,
            }

        # Pipeline Policy Metrics
        # Policy False Accept = spoof sample given ALLOW final decision
        # Policy False Reject = bona-fide sample given BLOCK/HOLD final decision
        spoof_summaries = [s for s in ds_summaries if s["ground_truth_label"] == SPOOF]
        bona_summaries = [s for s in ds_summaries if s["ground_truth_label"] == BONAFIDE]

        policy_fa = sum(1 for s in spoof_summaries if s["final_decision"] == "ALLOW")
        policy_fr = sum(1 for s in bona_summaries if s["final_decision"] in ("BLOCK", "HOLD"))

        scorecard_entry["policy_behavior"] = {
            "policy_false_accept_rate_pct": round((policy_fa / len(spoof_summaries)) * 100.0, 2) if spoof_summaries else "N/A",
            "policy_false_reject_rate_pct": round((policy_fr / len(bona_summaries)) * 100.0, 2) if bona_summaries else "N/A",
            "policy_verify_rate_bona_pct": round((sum(1 for s in bona_summaries if s["final_decision"] == "VERIFY") / len(bona_summaries)) * 100.0, 2) if bona_summaries else "N/A",
            "policy_verify_rate_spoof_pct": round((sum(1 for s in spoof_summaries if s["final_decision"] == "VERIFY") / len(spoof_summaries)) * 100.0, 2) if spoof_summaries else "N/A",
        }

        # Time to detection on detected spoofs
        ttd_spoofs = [s["time_to_detection_s"] for s in spoof_summaries if s["time_to_detection_s"] != "N/A"]
        scorecard_entry["time_to_detection_s"] = {
            "mean": round(float(np.mean(ttd_spoofs)), 2) if ttd_spoofs else "N/A",
            "median": round(float(np.median(ttd_spoofs)), 2) if ttd_spoofs else "N/A",
            "min": round(float(np.min(ttd_spoofs)), 2) if ttd_spoofs else "N/A",
            "max": round(float(np.max(ttd_spoofs)), 2) if ttd_spoofs else "N/A",
        }

        decision_matrix["scorecard"][ds_name] = scorecard_entry

    matrix_path = out_dir / "decision_matrix.json"
    with open(matrix_path, "w", encoding="utf-8") as fh:
        json.dump(decision_matrix, fh, indent=2)

    log(f"Results successfully saved to {out_dir}:")
    log(f"  • {manifest_path.name}")
    log(f"  • {scores_path.name}")
    log(f"  • {matrix_path.name}")

    return decision_matrix


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 1.8 Multi-Domain Streaming Pipeline Runner")
    parser.add_argument("--out", default="evaluation/results/phase1_8_multidomain", help="Output directory")
    parser.add_argument("--per-class", type=int, default=500, help="Samples per class (bona-fide/spoof)")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed for stratified sampling")
    parser.add_argument("--dataset", default=None, help="Evaluate a single dataset (optional)")
    parser.add_argument("--limit", type=int, default=None, help="Limit total samples evaluated (for pilot)")
    args = parser.parse_args()

    run_multidomain_evaluation(
        out_dir=Path(args.out),
        per_class=args.per_class,
        seed=args.seed,
        target_dataset=args.dataset,
        limit_samples=args.limit,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
