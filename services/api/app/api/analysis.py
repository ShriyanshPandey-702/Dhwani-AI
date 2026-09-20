"""
Manual Audio Analysis Endpoint — POST /analysis/audio

Allows a user to upload a recorded audio file (and optional speaker reference)
and run it through VoiceShield's existing Core:

Manual Audio → Bounded Ingestion → Normalization (16 kHz Mono)
→ Whisper Context Classification → Exact 64,608 / 16,000 Window Geometry
→ AASIST-L Authenticity + ECAPA-TDNN Identity (Adapter)
→ Model B Gated Corroboration Fusion → Policy Engine → ManualAnalysisReport

ADAPTER-LAYER DESIGN NOTE
--------------------------
This module constructs its own dedicated detector instances
(authenticity_detector, transcriber, speaker_identity) with
pipeline_mode="real_ml" and an absolute-resolved MODEL_DIR.

It does NOT import the global mock-configured singletons from
app.websocket.pipeline; those singletons exist solely for the WebSocket
real-time path, whose pipeline_mode is governed by settings.PIPELINE_MODE.

The manual-analysis endpoint always attempts real_ml regardless of the global
PIPELINE_MODE setting. Each detector's existing graceful-fallback logic
handles the case where a checkpoint or dependency is unavailable on the
current host — it falls back to its heuristic/demo backend and labels the
result is_mock=True, so the caller can see exactly what ran.
"""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict

from app.ml.authenticity.detector import AuthenticityDetector, AuthenticityResult
from app.ml.context.classifier import ContextClassifier, ContextResult
from app.ml.context.transcriber import Transcriber
from app.ml.identity.speaker import SpeakerIdentity, ENROLLED, NOT_ENROLLED
from app.ml.preprocessing.audio import measure_quality
from app.ml.preprocessing.ingest import AudioIngestError, load_audio_file
from app.risk.engine import EvidenceBundle, compute_risk
from app.risk.policy import DEFAULT_POLICY_CONFIG, evaluate

log = structlog.get_logger()
router = APIRouter()

# ── Endpoint Security Limits ──────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 25 * 1024 * 1024       # 25 MB ceiling per file
CHUNK_READ_SIZE = 64 * 1024               # 64 KiB bounded read buffer
MAX_AUDIO_DURATION_S = 300.0              # 5.0 minutes maximum
MIN_ANALYSIS_SAMPLES = 64608              # 4.038 s at 16 kHz: minimum for 1 full ML window
WINDOW_SAMPLES = 64608                    # Exact 4038 ms window
HOP_SAMPLES = 16000                       # Exact 1000 ms hop
SELF_CONSISTENCY = "SELF_CONSISTENCY"

# ── Absolute model directory ──────────────────────────────────────────────────
# Resolved from the file's own location so this module is CWD-independent.
# Layout: services/api/app/api/analysis.py
#                              parents[0] = api/
#                              parents[1] = app/
#                              parents[2] = services/api/
#                                                       → models/
_MANUAL_MODEL_DIR: str = str(Path(__file__).resolve().parents[2] / "models")

# ── Dedicated real_ml detector instances for manual analysis ──────────────────
# Constructed at module import time (once, shared across requests).
# We temporarily set MODEL_DIR in the environment so that each detector's
# own _init_real_ml() resolves the absolute path instead of the relative
# "models" default.  The environment is restored immediately afterwards so
# the WebSocket path and other subsystems are unaffected.
_orig_model_dir = os.environ.get("MODEL_DIR")
os.environ["MODEL_DIR"] = _MANUAL_MODEL_DIR

authenticity_detector = AuthenticityDetector(pipeline_mode="real_ml")
transcriber = Transcriber(pipeline_mode="real_ml")
speaker_identity = SpeakerIdentity(pipeline_mode="real_ml")

if _orig_model_dir is None:
    os.environ.pop("MODEL_DIR", None)
else:
    os.environ["MODEL_DIR"] = _orig_model_dir
del _orig_model_dir

# Shared real context classifier (stateless rule engine, no model dir needed):
context_classifier = ContextClassifier()


def _build_model_versions() -> dict:
    """
    Build model_versions from the LIVE instances, not static strings.

    This makes it structurally impossible to report real_ml when a mock
    backend actually ran: is_mock, pipeline_mode, and model_name all
    come directly from the instantiated detectors.
    """
    return {
        "authenticity": authenticity_detector.model_version,
        "identity": speaker_identity.model_version,
        "stt": transcriber.model_version,
        "context": ContextClassifier.MODEL_VERSION,
        "authenticity_backend": authenticity_detector.pipeline_mode,
        "identity_backend": speaker_identity.pipeline_mode,
        "stt_backend": transcriber.pipeline_mode,
        # Reflects what actually initialised, not the global config setting:
        "pipeline_mode": (
            "real_ml"
            if authenticity_detector.pipeline_mode == "real_ml"
            else authenticity_detector.pipeline_mode
        ),
        # Expose fallback reasons for transparency when real_ml could not load:
        "authenticity_is_mock": not authenticity_detector.is_real_ml,
        "identity_is_mock": not speaker_identity.is_real_ml,
        "stt_is_mock": not transcriber.is_real_ml,
        "authenticity_fallback_reason": authenticity_detector.fallback_reason,
        "identity_fallback_reason": speaker_identity.fallback_reason,
        "stt_fallback_reason": transcriber.fallback_reason,
    }


class WindowAnalysisSnapshot(BaseModel):
    window_index: int
    offset_ms: int
    duration_ms: int
    authenticity_spoof_prob: float
    identity_similarity: Optional[float]
    window_risk_score: int
    window_risk_state: str


class ManualAnalysisReport(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    status: str
    analysis_completed: bool
    filename: str
    duration_seconds: float
    sample_rate: int
    channels: int
    quality: dict

    # Unified Risk & Policy Verdict (None if analysis not completed)
    risk_score: Optional[int]
    risk_state: Optional[str]
    decision: str
    action: str
    recommended_action: str
    reasons: List[str]
    evidence_confidence: float
    contributions: Dict[str, float]

    # Evidence Stream Breakdown
    authenticity: Optional[dict] = None
    identity: Optional[dict] = None
    context: Optional[dict] = None

    # Windows & Execution Telemetry
    windows_evaluated: int
    window_timeline: List[WindowAnalysisSnapshot] = []
    processing_time_ms: float
    model_versions: dict


async def _save_upload_to_temp(upload: UploadFile, prefix: str = "vs_upload_") -> Path:
    """Stream uploaded file in bounded chunks to a secure temporary file."""
    temp_file = tempfile.NamedTemporaryFile(prefix=prefix, suffix=".tmp", delete=False)
    total_bytes = 0
    try:
        while True:
            chunk = await upload.read(CHUNK_READ_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            if total_bytes > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={"code": "FILE_TOO_LARGE", "message": f"File exceeds the 25 MB limit ({total_bytes} bytes)."},
                )
            temp_file.write(chunk)
        temp_file.flush()
    finally:
        temp_file.close()

    if total_bytes == 0:
        Path(temp_file.name).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_FILE", "message": "Uploaded file is 0 bytes."},
        )
    return Path(temp_file.name)


@router.post("/audio", response_model=ManualAnalysisReport, status_code=status.HTTP_200_OK)
async def analyze_audio(
    file: UploadFile = File(...),
    speaker_reference: Optional[UploadFile] = File(None),
):
    """
    Analyze a pre-recorded audio file using VoiceShield's multi-modal ML core.
    Supports WAV, MP3, FLAC, OGG.
    """
    t_start = time.perf_counter()
    temp_main_path: Optional[Path] = None
    temp_ref_path: Optional[Path] = None

    try:
        # ── 1. Bounded Stream Ingestion ────────────────────────────────────────
        temp_main_path = await _save_upload_to_temp(file, prefix="vs_main_")
        if speaker_reference is not None:
            temp_ref_path = await _save_upload_to_temp(speaker_reference, prefix="vs_ref_")

        # ── 2. Canonical Decoding & Audio Ingestion ────────────────────────────
        try:
            audio, meta = load_audio_file(temp_main_path)
        except AudioIngestError as e:
            msg = str(e)
            if "cannot decode audio" in msg or "Format not recognised" in msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "CORRUPTED_CONTAINER", "message": f"Audio container could not be decoded: {msg}"},
                )
            if "NaN or Inf" in msg:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "AUDIO_CONTAINS_NAN_INF", "message": msg},
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "INVALID_AUDIO", "message": msg},
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "UNSUPPORTED_AUDIO_FORMAT", "message": f"Could not process audio: {e}"},
            )

        # ── 3. Duration Limits Check ──────────────────────────────────────────
        if meta.duration_s > MAX_AUDIO_DURATION_S:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "AUDIO_TOO_LONG",
                    "message": f"Audio duration ({meta.duration_s:.1f}s) exceeds the 300.0s maximum limit.",
                },
            )

        quality = measure_quality(audio)
        model_versions = _build_model_versions()

        # ── 4. Short-Audio & Silence Gates ────────────────────────────────────
        if len(audio) < MIN_ANALYSIS_SAMPLES:
            proc_ms = round((time.perf_counter() - t_start) * 1000, 2)
            return ManualAnalysisReport(
                status="insufficient_duration",
                analysis_completed=False,
                filename=file.filename or "uploaded_audio",
                duration_seconds=meta.duration_s,
                sample_rate=meta.original_sample_rate,
                channels=meta.original_channels,
                quality=quality.to_dict(),
                risk_score=None,
                risk_state=None,
                decision="VERIFY",
                action="verify",
                recommended_action="Audio duration is too short for automated analysis (minimum 4.038 seconds required). Perform manual verification.",
                reasons=["audio_duration_less_than_window_size"],
                evidence_confidence=0.0,
                contributions={"authenticity": 0.0, "identity": 0.0, "context": 0.0},
                authenticity=None,
                identity=None,
                context=None,
                windows_evaluated=0,
                window_timeline=[],
                processing_time_ms=proc_ms,
                model_versions=model_versions,
            )

        if quality.is_silent:
            proc_ms = round((time.perf_counter() - t_start) * 1000, 2)
            return ManualAnalysisReport(
                status="silent_audio",
                analysis_completed=False,
                filename=file.filename or "uploaded_audio",
                duration_seconds=meta.duration_s,
                sample_rate=meta.original_sample_rate,
                channels=meta.original_channels,
                quality=quality.to_dict(),
                risk_score=None,
                risk_state=None,
                decision="VERIFY",
                action="verify",
                recommended_action="Uploaded audio is silent or below minimum speech energy. Check audio source.",
                reasons=["silence_detected"],
                evidence_confidence=0.0,
                contributions={"authenticity": 0.0, "identity": 0.0, "context": 0.0},
                authenticity=None,
                identity=None,
                context=None,
                windows_evaluated=0,
                window_timeline=[],
                processing_time_ms=proc_ms,
                model_versions=model_versions,
            )

        # ── 5. Whisper Context Classification Orchestration ───────────────────
        session_id = f"manual_{uuid.uuid4().hex[:12]}"
        chunk_step = 30 * 16000  # 30-second non-overlapping blocks
        transcript_texts = []
        # Initialise with the actual backend state, not hardcoded mock strings:
        is_mock_stt = not transcriber.is_real_ml
        stt_model_name = transcriber.model_name
        stt_pipeline_mode = transcriber.pipeline_mode
        stt_lang = ""
        stt_conf = 0.0

        for start_idx in range(0, len(audio), chunk_step):
            block = audio[start_idx : start_idx + chunk_step]
            if len(block) >= 16000:
                seg = transcriber.transcribe(session_id, block)
                if seg and seg.text:
                    transcript_texts.append(seg.text)
                    is_mock_stt = seg.is_mock
                    stt_model_name = seg.model_name
                    stt_pipeline_mode = seg.pipeline_mode
                    stt_lang = seg.language
                    stt_conf = seg.confidence

        full_transcript = " ".join(transcript_texts).strip()
        context_result: Optional[ContextResult] = None
        if full_transcript:
            context_result = context_classifier.classify(
                session_id,
                full_transcript,
                transcript_is_mock=is_mock_stt,
                transcript_model=stt_model_name,
                transcript_pipeline_mode=stt_pipeline_mode,
                transcript_language=stt_lang,
                transcript_confidence=stt_conf,
            )

        ctx_risk = (context_result.score / 100.0) if context_result else None
        consequence = context_result.consequence if context_result else "low"
        ctx_conf = context_result.confidence if context_result else 0.0

        # ── 6. ECAPA Identity Setup & Mode Selection ──────────────────────────
        ref_embedding: Optional[np.ndarray] = None
        identity_mode = NOT_ENROLLED

        if temp_ref_path is not None:
            try:
                ref_audio, ref_meta = load_audio_file(temp_ref_path)
                if len(ref_audio) >= 16000:
                    ref_embedding = speaker_identity._embed(ref_audio)
                    identity_mode = ENROLLED
            except Exception as e:
                log.warning("manual_analysis.ref_decode_failed", error=str(e))
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "REFERENCE_DECODE_FAILED", "message": f"Speaker reference could not be decoded: {e}"},
                )

        # ── 7. Window Slicing & Model Inference ───────────────────────────────
        policy_config = DEFAULT_POLICY_CONFIG
        id_thresh = policy_config.get("identity_corroboration_threshold", 0.40)
        sim_mismatch_thresh = 1.0 - id_thresh  # 0.60
        corroboration_persistence = policy_config.get("corroboration_persistence", 2)

        consecutive_mismatches = 0
        window_snapshots: List[WindowAnalysisSnapshot] = []
        scored_windows: List[dict] = []

        total_samples = len(audio)
        num_windows = max(0, (total_samples - WINDOW_SAMPLES) // HOP_SAMPLES + 1)

        # Initialize internal reference for SELF_CONSISTENCY if not enrolled
        if identity_mode != ENROLLED and num_windows > 0:
            first_win = audio[0:WINDOW_SAMPLES]
            ref_embedding = speaker_identity._embed(first_win)
            identity_mode = SELF_CONSISTENCY

        last_auth: Optional[AuthenticityResult] = None
        last_id_dict: Optional[dict] = None

        for k in range(num_windows):
            offset = k * HOP_SAMPLES
            win_audio = audio[offset : offset + WINDOW_SAMPLES]
            offset_ms = int(1000 * offset / 16000)

            # A. Authenticity Inference (AASIST + DSP)
            auth = authenticity_detector.analyze(win_audio)
            if auth is not None:
                last_auth = auth

            auth_val = (auth.spoof_probability if auth else None)
            auth_conf = (auth.confidence if auth else 0.0)

            # B. Identity Inference
            sim: Optional[float] = None
            match_score: int = 0
            id_conf: float = 0.0

            if ref_embedding is not None and win_audio is not None:
                try:
                    win_emb = speaker_identity._embed(win_audio)
                    if speaker_identity.is_real_ml and speaker_identity._ecapa:
                        cmp = speaker_identity._ecapa.compare(win_emb, ref_embedding, duration_s=4.038)
                        sim = cmp.similarity
                        match_score = cmp.match_score
                        id_conf = cmp.model_confidence
                    else:
                        sim = float(speaker_identity._demo.similarity(win_emb, ref_embedding))
                        match_score = int(round(float(np.clip(sim, 0.0, 1.0)) * 100))
                        id_conf = 0.50
                except Exception as e:
                    log.warning("manual_analysis.identity_window_failed", error=str(e))
                    sim = None

            # C. Persistence & Corroboration Evaluation
            # CRITICAL (Directive 2): SELF_CONSISTENCY must NEVER corroborate identity
            identity_corroborated = False
            identity_corroboration_pending = False

            if identity_mode == ENROLLED:
                if sim is not None and sim <= sim_mismatch_thresh:
                    consecutive_mismatches += 1
                else:
                    consecutive_mismatches = 0

                if consecutive_mismatches >= corroboration_persistence:
                    identity_corroborated = True
                elif consecutive_mismatches == 1:
                    identity_corroboration_pending = True
            else:
                consecutive_mismatches = 0

            # D. Risk Engine Fusion
            evidence = EvidenceBundle(
                authenticity=auth_val,
                authenticity_confidence=auth_conf,
                identity_similarity=sim,
                identity_confidence=id_conf,
                context_risk=ctx_risk,
                context_confidence=ctx_conf,
                consequence=consequence,
                identity_corroborated=identity_corroborated,
                identity_corroboration_pending=identity_corroboration_pending,
            )

            risk_res = compute_risk(evidence, policy_config)

            # Record snapshot
            snap = WindowAnalysisSnapshot(
                window_index=k,
                offset_ms=offset_ms,
                duration_ms=4038,
                authenticity_spoof_prob=round(auth_val, 4) if auth_val is not None else 0.0,
                identity_similarity=round(sim, 4) if sim is not None else None,
                window_risk_score=risk_res.score,
                window_risk_state=risk_res.state,
            )
            window_snapshots.append(snap)

            last_id_dict = {
                "match_score": match_score,
                "confidence": id_conf,
                "consistency": "GOOD" if (sim is not None and sim > 0.70) else ("VARIABLE" if (sim is not None and sim > 0.50) else "POOR"),
                "enrollment_status": identity_mode,
                "model_version": speaker_identity.model_version,
                "is_mock": not speaker_identity.is_real_ml,
                "model_name": speaker_identity.model_name,
                "pipeline_mode": speaker_identity.pipeline_mode,
                "similarity": round(sim, 4) if sim is not None else 0.0,
            }

            scored_windows.append({
                "risk_res": risk_res,
                "auth": auth,
                "identity": last_id_dict,
            })

        # ── 8. Aggregate Verdict & Policy Decision ─────────────────────────────
        if not scored_windows:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "PROCESSING_FAILURE", "message": "No analysis windows could be evaluated."},
            )

        # Select peak risk window for overall verdict
        peak_entry = max(scored_windows, key=lambda w: w["risk_res"].score)
        peak_risk = peak_entry["risk_res"]

        # Policy evaluation based on peak state and consequence
        decision = evaluate(
            peak_risk.state,
            consequence=consequence,
            reasons=peak_risk.reasons,
            evidence_confidence=peak_risk.evidence_confidence,
            policy_config=policy_config,
        )

        proc_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return ManualAnalysisReport(
            status="completed",
            analysis_completed=True,
            filename=file.filename or "uploaded_audio",
            duration_seconds=meta.duration_s,
            sample_rate=meta.original_sample_rate,
            channels=meta.original_channels,
            quality=quality.to_dict(),
            risk_score=peak_risk.score,
            risk_state=peak_risk.state,
            decision=decision.decision,
            action=decision.action,
            recommended_action=decision.recommended_action,
            reasons=list(dict.fromkeys(peak_risk.reasons + decision.reasons)),
            evidence_confidence=peak_risk.evidence_confidence,
            contributions=peak_risk.contributions,
            authenticity=peak_entry["auth"].to_dict() if peak_entry["auth"] else (last_auth.to_dict() if last_auth else None),
            identity=peak_entry["identity"],
            context=context_result.to_dict() if context_result else None,
            windows_evaluated=len(window_snapshots),
            window_timeline=window_snapshots,
            processing_time_ms=proc_ms,
            model_versions=model_versions,
        )

    finally:
        # ── 9. Guaranteed Disk Cleanup ────────────────────────────────────────
        if temp_main_path is not None:
            temp_main_path.unlink(missing_ok=True)
        if temp_ref_path is not None:
            temp_ref_path.unlink(missing_ok=True)
