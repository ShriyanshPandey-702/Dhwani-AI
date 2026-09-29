"""
Analysis pipeline — one audio window in, a list of dashboard events out.

    audio window
        ↓
    preprocessing + quality
        ↓
    ┌───────────┬───────────┬───────────┐
    authenticity  identity    context      (independent evidence streams)
    └───────────┴───────────┴───────────┘
        ↓
    Risk Engine  (fusion)
        ↓
    Policy Engine (decision)
        ↓
    events → WebSocket → Zustand → dashboard

The same function serves both the mock demo driver and real client audio; only
`pipeline_mode` differs. Real Android capture (Phase 7) plugs in here with no
downstream change.
"""

from __future__ import annotations

from typing import Callable, List, Optional

import numpy as np
import time
import structlog

from app.core.database import AsyncSessionLocal
from app.ml.authenticity.detector import AuthenticityDetector
from app.ml.context.classifier import ContextClassifier
from app.ml.context.transcriber import Transcriber
from app.ml.identity.speaker import SpeakerIdentity
from app.core.config import settings
from app.ml.preprocessing.audio import (
    decode_pcm, measure_quality, MIN_SPEECH_ENERGY, TARGET_SR as SAMPLE_RATE,
)
from app.ml.preprocessing.stream import StreamWindower
from app.websocket.stt_queue import STT_EVERY_N_WINDOWS
from app.models.models import RiskSnapshot
from app.risk.engine import compute_risk, risk_trend, classify_state
from app.risk.policy import evaluate
from app.websocket import events as ev
from app.websocket.manager import SessionState

log = structlog.get_logger()

# Model singletons — loaded once, shared across sessions.
authenticity_detector = AuthenticityDetector()
speaker_identity = SpeakerIdentity()
transcriber = Transcriber()
context_classifier = ContextClassifier()

# Rolling per-session buffer that assembles the longer windows a trained model
# needs from the ~1 s frames the client sends.
stream_windower = StreamWindower(
    window_ms=settings.ANALYSIS_WINDOW_MS,
    hop_ms=settings.ANALYSIS_HOP_MS,
)

# Built from the live instances, not class attributes, so an incident records
# the backend that actually ran rather than the default one.
MODEL_VERSIONS = {
    "authenticity": authenticity_detector.model_version,
    "identity": speaker_identity.model_version,
    "stt": transcriber.model_version,
    "context": ContextClassifier.MODEL_VERSION,
    "authenticity_backend": authenticity_detector.pipeline_mode,
    "identity_backend": speaker_identity.pipeline_mode,
    "stt_backend": transcriber.pipeline_mode,
    "pipeline_mode": settings.PIPELINE_MODE,
}

# Timeline labels for the codes the pipeline can raise.
_EVENT_LABELS = {
    "voice_authenticity_anomaly": ("Voice anomaly detected", "authenticity", "warning"),
    "moderate_synthetic_indicators": ("Moderate synthetic indicators", "authenticity", "info"),
    "acoustic_anomaly_high": ("Acoustic anomaly increased", "authenticity", "warning"),
    "spectral_anomaly_high": ("Spectral anomaly increased", "authenticity", "warning"),
    "prosody_anomaly_high": ("Prosody anomaly increased", "authenticity", "warning"),
    "speaker_identity_mismatch": ("Speaker does not match enrolment", "identity", "warning"),
    "speaker_identity_inconsistency": ("Speaker consistency degraded", "identity", "info"),
    "urgency": ("Urgency detected", "context", "info"),
    "financial_request": ("Financial request detected", "context", "warning"),
    "otp_request": ("OTP request detected", "context", "critical"),
    "credential_request": ("Credential request detected", "context", "critical"),
    "sensitive_information_request": ("Sensitive information requested", "context", "warning"),
    "social_engineering": ("Social-engineering pattern detected", "context", "warning"),
    "authority_claim": ("Authority claim detected", "context", "info"),
    "audio_quality_poor": ("Audio quality degraded", "session", "info"),
}


def _speech_credible(
    audio_or_quality,
    quality=None,
    is_real_ml: Optional[bool] = None,
) -> bool:
    """
    Return True only when the audio window contains credible speech evidence.

    Gating rules (Phase 5.7 correctness hardening):
    - Silent windows are never credible (``quality.is_silent`` == True).
    - POOR quality (SNR < 8 dB, clipping > 2 %, or silent) is never credible.
    - In real_ml mode, actual voice activity is verified using the bundled
      Silero VAD (faster_whisper.vad) requiring at least 250 ms of speech.
      If VAD execution fails or is unavailable in real_ml mode, it fails closed
      (returns False) to prevent non-speech contamination of speaker identity.
    - In mock / heuristic-demo test modes, lightweight quality-only gating
      is preserved so deterministic unit tests do not require neural VAD.

    AASIST and Whisper are NOT blocked by this predicate. This predicate
    touches identity only (ECAPA auto-enrollment and mismatch streak updates).
    """
    if quality is None:
        if hasattr(audio_or_quality, "is_silent") and hasattr(audio_or_quality, "quality"):
            q = audio_or_quality
            audio = None
        else:
            audio = audio_or_quality
            q = None
    else:
        audio = audio_or_quality
        q = quality

    if q is not None:
        if q.is_silent or q.quality == "POOR":
            return False

    real_ml = is_real_ml if is_real_ml is not None else speaker_identity.is_real_ml
    if real_ml:
        if audio is None or len(audio) == 0:
            return False
        try:
            from faster_whisper.vad import get_speech_timestamps, VadOptions
            opts = VadOptions(min_speech_duration_ms=250)
            audio_f32 = np.ascontiguousarray(audio, dtype=np.float32)
            if audio_f32.ndim > 1:
                audio_f32 = audio_f32.mean(axis=1)
            timestamps = get_speech_timestamps(audio_f32, opts)
            if not timestamps:
                return False
            total_speech_samples = sum(ts["end"] - ts["start"] for ts in timestamps)
            min_samples = int(SAMPLE_RATE * 0.250)  # 250 ms at 16000 Hz = 4000 samples
            return total_speech_samples >= min_samples
        except Exception as e:
            log.warning("speech_credible.vad_error", error=str(e))
            # Fail closed: never allow unverified audio to enroll
            return False

    return True


def analyze_window(state: SessionState, pcm_bytes: bytes,
                   pipeline_mode: str = "mock",
                   stt_submit: Optional[Callable[[int, "np.ndarray"], None]] = None,
                   ) -> List[dict]:
    """
    Run one analysis window and return the events to broadcast, in order.

    Never raises on bad input — a window that cannot be analysed produces an
    audio_quality event and nothing else, leaving the risk picture unchanged.

    `stt_submit(window_seq, audio)`, when given, makes transcription
    asynchronous: the callback enqueues the window and this function returns
    immediately with context evidence still unavailable. Omit it (or run the
    scripted transcriber) for the original synchronous behaviour.
    """
    session_id = state.session_id
    out: List[dict] = []
    t_start = time.perf_counter()
    stage_ms: dict = {}

    raw = decode_pcm(pcm_bytes)
    quality = measure_quality(raw)
    out.append(ev.audio_quality(session_id, quality.to_dict(), active=not quality.is_silent))

    if raw is None or quality.is_silent:
        # Silence is not evidence. The dashboard keeps its last risk picture
        # and the engine is not fed a fabricated observation.
        if quality.quality == "POOR":
            out.extend(_timeline(state, "audio_quality_poor"))
        # Correction 3: Silence / invalid identity evidence: streak = 0
        state.consecutive_identity_mismatches = 0
        state.consecutive_authenticity_anomalies = 0
        return out

    audio = raw

    # ── Evidence stream 1: authenticity (independent) ────────────────────────
    # Every frame feeds the rolling buffer. A trained model is scored on a full
    # analysis window; the heuristic backend keeps working per frame, which is
    # what makes the deterministic demonstration reproducible.
    window = stream_windower.push(session_id, audio)
    model_audio = window if authenticity_detector.is_real_ml else audio

    _t = time.perf_counter()
    auth = authenticity_detector.analyze(model_audio)
    stage_ms["authenticity"] = round((time.perf_counter() - _t) * 1000, 2)
    if auth is not None:
        state.last_authenticity = auth.to_dict()
        if authenticity_detector.is_real_ml and auth.spoof_probability > 0.65 and auth.confidence >= 0.50:
            state.consecutive_authenticity_anomalies += 1
        else:
            state.consecutive_authenticity_anomalies = 0

    # ── Evidence stream 2: identity (independent) ────────────────────────────
    # Demo enrolment happens once, from the first analysable window, and is
    # labelled as such. A production flow enrols out-of-band, before the call.
    #
    # Phase 5.7 correctness: enrolment is gated on credible speech.
    # Silent, POOR-quality, or non-speech windows MUST NOT become the speaker
    # reference — ambient noise/hiss produces a flat-spectrum embedding that
    # every subsequent real-speech window would score as MISMATCH, falsely
    # driving the identity corroboration flag that lifts the uncorroborated cap.
    identity_audio = window if speaker_identity.is_real_ml else audio
    _t = time.perf_counter()
    if not speaker_identity.is_enrolled(session_id) and _speech_credible(identity_audio, quality):
        speaker_identity.enroll(session_id, identity_audio)
        state.consecutive_identity_mismatches = 0
    ident = speaker_identity.analyze(session_id, identity_audio)
    stage_ms["identity"] = round((time.perf_counter() - _t) * 1000, 2)
    state.last_identity = ident.to_dict()

    # Deterministic persistence update (P=2 consecutive ML analysis windows)
    # ML inference occurs when a window is scored: in real_ml, when `window is not None`;
    # in mock mode, on each frame.
    #
    # Phase 5.7 correctness: the streak is only updated on credible-speech
    # windows.  Non-credible audio (silent or POOR quality) is treated as "no
    # identity evidence": it neither increments nor resets the mismatch streak.
    # This ensures only real speaker evidence can establish P=2 corroboration.
    window_scored = (window is not None) if speaker_identity.is_real_ml else True
    if window_scored and _speech_credible(identity_audio, quality):
        if ident is None or ident.enrollment_status == "NOT_ENROLLED":
            state.consecutive_identity_mismatches = 0
        else:
            corroboration_sim_thresh = 1.0 - state.policy_config.get(
                "identity_corroboration_threshold", 0.40
            )  # 1.0 - 0.40 = 0.60
            sim = ident.match_score / 100.0
            if sim <= corroboration_sim_thresh:
                state.consecutive_identity_mismatches += 1
            else:
                state.consecutive_identity_mismatches = 0

    # ── Evidence stream 3: conversation context (independent) ────────────────
    # Real transcription is slow (~537 ms p50) and must not sit in the 1 s
    # acoustic hop. When an async sink is supplied and the real model is
    # active, the window is handed to the STT queue and this function returns
    # without a transcript; context evidence simply arrives later. The scripted
    # mock transcriber is instant, so mock mode keeps running inline unchanged.
    stt_audio = window if transcriber.is_real_ml else audio
    segment = None
    if stt_submit is not None and transcriber.is_real_ml:
        # Count *analysis windows*, not chunks: the STT cadence is defined
        # against windows the model would actually see. Incrementing per chunk
        # would make the modulo almost never coincide with a real window.
        if stt_audio is not None:
            state.window_seq += 1
            if state.window_seq == 1 or state.window_seq % STT_EVERY_N_WINDOWS == 0:
                stt_submit(state.window_seq, stt_audio)
        stage_ms["stt"] = 0.0          # off the critical path by construction
    else:
        _t = time.perf_counter()
        segment = transcriber.transcribe(session_id, stt_audio)
        stage_ms["stt"] = round((time.perf_counter() - _t) * 1000, 2)
    if segment is not None:
        _t = time.perf_counter()
        ctx = context_classifier.classify(
            session_id,
            segment.text,
            transcript_is_mock=segment.is_mock,
            transcript_model=segment.model_name,
            transcript_pipeline_mode=segment.pipeline_mode,
            transcript_language=segment.language,
            transcript_confidence=segment.confidence,
        )
        stage_ms["context"] = round((time.perf_counter() - _t) * 1000, 2)
        if ctx is not None:
            accumulated = state.append_transcript(segment.text)
            ctx_dict = ctx.to_dict()
            ctx_dict["transcript"] = accumulated
            ctx_dict["latest_segment"] = segment.text
            state.last_context = ctx_dict
            state.consequence = ctx.consequence

    # ── Fusion, policy and the resulting events ──────────────────────────────
    _t = time.perf_counter()
    update, verdict = fuse_and_decide(state, pipeline_mode)
    stage_ms["risk_fusion"] = round((time.perf_counter() - _t) * 1000, 2)
    out.append(update)

    # ── Timeline: announce each finding once per session ─────────────────────
    out.extend(_authenticity_timeline(state, auth))
    out.extend(_identity_timeline(state, ident))
    out.extend(_context_timeline(state))

    # Built last so its sequence numbers follow the timeline events it trails.
    out.extend(decision_tail(state, verdict))

    # Observability (§20): metadata only — never audio, transcript or embeddings.
    stage_ms["total"] = round((time.perf_counter() - t_start) * 1000, 2)
    # A window is only *scored* when the rolling buffer emitted one. Chunks that
    # merely top up the buffer cost almost nothing, and averaging them together
    # with real inference would understate latency by an order of magnitude.
    stage_ms["window_scored"] = window is not None
    state.last_stage_ms = stage_ms
    log.info("pipeline.window",
             session_id=session_id,
             pipeline_mode=pipeline_mode,
             audio_ms=int(1000 * len(audio) / SAMPLE_RATE),
             window_scored=window is not None,
             vad_active=not quality.is_silent,
             risk_score=update.get("risk_score"),
             risk_state=update.get("risk_state"),
             **{f"ms_{k}": v for k, v in stage_ms.items()})

    return out


def fuse_and_decide(state: SessionState, pipeline_mode: str) -> tuple:
    """
    Fuse whatever evidence the session currently holds and apply the policy.

    Returns `(risk_update_event, verdict)`. Call `decision_tail(state, verdict)`
    afterwards to build the threshold / policy_decision / alert events — it is
    deliberately separate so the caller controls when those sequence numbers are
    allocated, and they always follow the events actually emitted before them.

    Shared by the audio path and by `recompute_after_outcome`, so a challenge or
    verification result is fused by exactly the same engine and policy as an
    audio window.
    """
    result = compute_risk(state.evidence(), state.policy_config)
    if pipeline_mode == "mock":
        state.record_risk(result.score, result.state)
        final_score = result.score
        final_state = result.state
    else:
        temporal_score = state.record_risk(result.score, result.state)
        final_score = temporal_score
        final_state = classify_state(final_score, state.policy_config.get("thresholds"))
        if result.state == "insufficient_evidence":
            final_score = 0
            final_state = "insufficient_evidence"
    trend = risk_trend(state.risk_history)

    decision = evaluate(
        risk_state=final_state,
        consequence=state.consequence,
        reasons=result.reasons,
        evidence_confidence=result.evidence_confidence,
        policy_config=state.policy_config,
    )

    previous_decision = state.last_decision
    state.last_decision = decision.decision
    state.last_action = decision.action

    update = ev.risk_update(
        session_id=state.session_id,
        risk_score=final_score,
        risk_state=final_state,
        risk_trend=trend,
        evidence_confidence=result.evidence_confidence,
        authenticity=state.last_authenticity,
        identity=state.last_identity,
        context=state.last_context,
        decision=decision.decision,
        reasons=decision.reasons,
        consequence=state.consequence,
        contributions={k: round(v, 2) for k, v in result.contributions.items()},
        pipeline_mode=pipeline_mode,
    )

    return update, (result, decision, previous_decision)


def decision_tail(state: SessionState, verdict: tuple) -> List[dict]:
    """
    Events that trail a risk update: the threshold timeline, a policy_decision
    when the decision actually changed, and an alert when risk is elevated.
    """
    result, decision, previous_decision = verdict
    tail: List[dict] = list(_threshold_timeline(state, result.state))

    if decision.decision != previous_decision:
        tail.append(ev.policy_decision(
            session_id=state.session_id,
            decision=decision.decision,
            action=decision.action,
            reasons=decision.reasons,
            recommended_action=decision.recommended_action,
            risk_state=result.state,
            risk_score=result.score,
        ))

    if result.state in ("high", "critical"):
        key = f"alert:{result.state}"
        if key not in state.announced:
            state.announced.add(key)
            tail.append(ev.alert(
                session_id=state.session_id,
                severity=result.state,
                message=_alert_message(result.state, decision.decision),
                recommended_action=decision.recommended_action,
            ))

    return tail


def recompute_after_outcome(state: SessionState) -> List[dict]:
    """
    Re-fuse and re-decide after interactive evidence arrives — a challenge
    result or an independent-verification result.

    An outcome is evidence in its own right, so the authoritative decision must
    move as soon as it lands. Without this it would only be fused when the next
    audio window happened to arrive, and once the audio stops — exactly when a
    held transaction is waiting on verification — it would never move at all.

    Returns [] when the session has no prior observation to revise; the first
    audio window will fuse the outcome normally in that case.
    """
    if not state.risk_history:
        return []
    update, verdict = fuse_and_decide(state, state.pipeline_mode)
    return [update, *decision_tail(state, verdict)]


# ── Timeline helpers ──────────────────────────────────────────────────────────

def _timeline(state: SessionState, code: str) -> List[dict]:
    """Emit a detected_event for `code`, but only the first time per session."""
    if code in state.announced:
        return []
    label, stream, severity = _EVENT_LABELS.get(code, (code, "risk", "info"))
    state.announced.add(code)
    return [ev.detected_event(state.session_id, code, label, stream, severity)]


def _authenticity_timeline(state: SessionState, auth) -> List[dict]:
    if auth is None:
        return []
    out: List[dict] = []
    if auth.spoof_probability > 0.70:
        out.extend(_timeline(state, "voice_authenticity_anomaly"))
    elif auth.spoof_probability > 0.40:
        out.extend(_timeline(state, "moderate_synthetic_indicators"))
    if auth.acoustic_anomaly == "HIGH":
        out.extend(_timeline(state, "acoustic_anomaly_high"))
    if auth.spectral_anomaly == "HIGH":
        out.extend(_timeline(state, "spectral_anomaly_high"))
    if auth.prosody_anomaly == "HIGH":
        out.extend(_timeline(state, "prosody_anomaly_high"))
    return out


def _identity_timeline(state: SessionState, ident) -> List[dict]:
    if ident is None or ident.enrollment_status == "NOT_ENROLLED":
        return []
    out: List[dict] = []
    if ident.enrollment_status == "MISMATCH":
        out.extend(_timeline(state, "speaker_identity_mismatch"))
    elif ident.consistency == "POOR":
        out.extend(_timeline(state, "speaker_identity_inconsistency"))
    return out


def _context_timeline(state: SessionState) -> List[dict]:
    ctx = state.last_context
    if not ctx:
        return []
    out: List[dict] = []
    for code in (
        "otp_request", "credential_request", "financial_request",
        "sensitive_information_request", "urgency", "authority_claim",
        "social_engineering",
    ):
        if ctx.get(code):
            out.extend(_timeline(state, code))
    return out


def _threshold_timeline(state: SessionState, risk_state: str) -> List[dict]:
    """Announce the first time each elevated risk threshold is crossed."""
    if risk_state not in ("suspicious", "high", "critical"):
        return []
    code = f"threshold_{risk_state}"
    if code in state.announced:
        return []
    state.announced.add(code)
    return [ev.detected_event(
        state.session_id,
        code,
        f"{risk_state.upper()} risk threshold crossed",
        "risk",
        "warning" if risk_state == "suspicious" else "critical",
    )]


def _alert_message(risk_state: str, decision: str) -> str:
    if risk_state == "critical":
        return "Critical risk. Do not act on this call without independent verification."
    return "Elevated risk detected on this call. Independent verification is recommended."


async def persist_snapshot(session_id: str, update: Optional[dict]) -> None:
    """
    Persist one risk observation.

    Called for every risk_update, whichever path produced it — an audio window
    or an interactive outcome — so `GET /risk/{session_id}` always agrees with
    what the live dashboard is showing. A persistence failure is logged and
    swallowed: it must never take down the live stream.
    """
    if not update or update.get("type") != ev.RISK_UPDATE:
        return
    try:
        async with AsyncSessionLocal() as db:
            db.add(RiskSnapshot(
                session_id=session_id,
                risk_score=update["risk_score"],
                risk_state=update["risk_state"],
                authenticity=(update.get("authenticity") or {}).get("spoof_probability"),
                identity=(
                    (update.get("identity") or {}).get("match_score", 0) / 100.0
                    if update.get("identity") else None
                ),
                context=(
                    (update.get("context") or {}).get("score", 0) / 100.0
                    if update.get("context") else None
                ),
                consequence=update.get("consequence"),
                reasons=update.get("reasons", []),
                model_versions=MODEL_VERSIONS,
            ))
            await db.commit()
    except Exception as e:
        log.warning("pipeline.snapshot_persist_failed", session_id=session_id, error=str(e))
