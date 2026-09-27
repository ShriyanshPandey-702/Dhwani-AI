"""
Dhwani AI — User Audio Files Deep Diagnostic Trace & Verification
Traces the complete actual upload path for the 5 user-provided audio files:
1. ElevenLabs_2026-09-19T12_01_32_Max - Elearning and Documentary_pvc_sp100_s50_sb75_se0_b_m2.mp3
2. hi--my-name-is-priyanshu--and-.wav
3. i-didn-t-expect-the-day-to-tur.wav
4. test.wav
5. you-know-what-i-find-interesti.wav
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
API_DIR = BASE_DIR / "services/api"
sys.path.insert(0, str(API_DIR))
os.environ["MODEL_DIR"] = str(API_DIR / "models")

import numpy as np
from fastapi.testclient import TestClient
from main import app
from app.ml.preprocessing.ingest import load_audio_file
from app.ml.preprocessing.audio import measure_quality
from app.ml.authenticity.detector import AuthenticityDetector
from app.ml.identity.speaker import SpeakerIdentity, ENROLLED, NOT_ENROLLED
from app.ml.context.transcriber import Transcriber
from app.ml.context.classifier import ContextClassifier
from app.risk.engine import EvidenceBundle, compute_risk
from app.risk.policy import DEFAULT_POLICY_CONFIG

client = TestClient(app)

auth_detector = AuthenticityDetector(pipeline_mode="real_ml")
spk_identity = SpeakerIdentity(pipeline_mode="real_ml")
transcriber = Transcriber(pipeline_mode="real_ml")
context_classifier = ContextClassifier()

WINDOW_SAMPLES = 64608
HOP_SAMPLES = 16000

USER_FILES = [
    "/Users/shriyansh/Downloads/Audio/ElevenLabs_2026-09-19T12_01_32_Max - Elearning and Documentary_pvc_sp100_s50_sb75_se0_b_m2.mp3",
    "/Users/shriyansh/Downloads/Audio/hi--my-name-is-priyanshu--and-.wav",
    "/Users/shriyansh/Downloads/Audio/i-didn-t-expect-the-day-to-tur.wav",
    "/Users/shriyansh/Downloads/Audio/test.wav",
    "/Users/shriyansh/Downloads/Audio/you-know-what-i-find-interesti.wav"
]

print("=" * 100)
print("DHWANI AI — USER AUDIO FILES DEEP DIAGNOSTIC TRACE")
print("=" * 100)

for file_str in USER_FILES:
    p = Path(file_str)
    if not p.exists():
        print(f"\n[ERROR] File not found: {p}")
        continue
    
    with open(p, "rb") as f:
        file_bytes = f.read()

    # Call the live endpoint
    mime_type = "audio/mpeg" if p.suffix.lower() == ".mp3" else "audio/wav"
    response = client.post(
        "/analysis/audio",
        files={"file": (p.name, file_bytes, mime_type)}
    )
    api_report = response.json()

    # Manual decode & trace
    audio, meta = load_audio_file(p)
    quality = measure_quality(audio)
    duration = meta.duration_s
    sr = meta.original_sample_rate
    num_windows = max(0, (len(audio) - WINDOW_SAMPLES) // HOP_SAMPLES + 1)
    
    # STT & Context
    trans_seg = transcriber.transcribe(f"trace_{p.stem[:6]}", audio[: 30 * 16000])
    transcript_text = trans_seg.text if trans_seg else ""
    ctx_res = context_classifier.classify(f"trace_{p.stem[:6]}", transcript_text) if transcript_text else None
    
    ctx_signals = ctx_res.detected_phrases if ctx_res else []
    ctx_score_val = ctx_res.score if ctx_res else 0.0
    ctx_risk = (ctx_score_val / 100.0) if ctx_res else None
    ctx_conf = ctx_res.confidence if ctx_res else 0.0
    consequence = ctx_res.consequence if ctx_res else "low"
    
    # Window analysis
    window_aasist_raws = []
    window_sims = []
    window_fused_scores = []
    first_emb = spk_identity._embed(audio[0:WINDOW_SAMPLES]) if num_windows > 0 else None
    
    for k in range(num_windows):
        offset = k * HOP_SAMPLES
        win_audio = audio[offset : offset + WINDOW_SAMPLES]
        auth = auth_detector.analyze(win_audio)
        raw_aasist = auth.spoof_probability if auth else 0.0
        window_aasist_raws.append(round(raw_aasist, 4))
        
        win_emb = spk_identity._embed(win_audio)
        if first_emb is not None and win_emb is not None:
            sim = float(np.dot(win_emb, first_emb))
            window_sims.append(round(sim, 4))
        else:
            sim = 1.0

        ev = EvidenceBundle(
            authenticity=raw_aasist,
            authenticity_confidence=auth.confidence if auth else 0.0,
            identity_similarity=None, # NOT enrolled
            identity_confidence=0.0,
            context_risk=ctx_risk,
            context_confidence=ctx_conf,
            consequence=consequence,
            identity_corroborated=False,
            identity_corroboration_pending=False,
        )
        res = compute_risk(ev, DEFAULT_POLICY_CONFIG)
        window_fused_scores.append(res.score)

    agg_aasist = max(window_aasist_raws) if window_aasist_raws else 0.0
    agg_sim = (sum(window_sims) / len(window_sims)) if window_sims else 1.0
    
    # Compute trace for the representative window (window with max score)
    rep_k = int(np.argmax(window_fused_scores)) if window_fused_scores else 0
    rep_aasist = window_aasist_raws[rep_k] if window_aasist_raws else 0.0
    rep_ev = EvidenceBundle(
        authenticity=rep_aasist,
        authenticity_confidence=0.90,
        identity_similarity=None,
        identity_confidence=0.0,
        context_risk=ctx_risk,
        context_confidence=ctx_conf,
        consequence=consequence,
        identity_corroborated=False,
        identity_corroboration_pending=False,
    )
    rep_res = compute_risk(rep_ev, DEFAULT_POLICY_CONFIG)
    raw_fused = sum(rep_res.contributions.values())
    cap_activated = "total_risk_uncorroborated_cap_active" in rep_res.reasons
    cap_reason = "Uncorroborated synthetic voice (no enrolled mismatch, no context scam threat)" if cap_activated else "N/A"

    print(f"\n{'─' * 80}")
    print(f"FILE: {p.name}")
    print(f"{'─' * 80}")
    print(f"  • Filename:                     {p.name}")
    print(f"  • Duration:                     {duration:.2f} s")
    print(f"  • Sample Rate:                  {sr} Hz (normalized to 16000 Hz)")
    print(f"  • Number of Windows:            {num_windows}")
    print(f"  • AASIST Raw Spoof per Window:  {window_aasist_raws}")
    print(f"  • Aggregated AASIST Result:     {agg_aasist:.4f}")
    print(f"  • ECAPA Result (Self-Sim):      {agg_sim:.4f}")
    print(f"  • Identity Enrolled:            NO (No reference enrolled)")
    print(f"  • Self-Consistency Result:      GOOD (internal continuity across windows)" if agg_sim > 0.6 else "VARIABLE")
    print(f"  • Whisper Transcript:           \"{transcript_text}\"")
    print(f"  • Context Signals:              {ctx_signals}")
    print(f"  • Authenticity Score:           {rep_res.contributions['authenticity']:.2f}")
    print(f"  • Identity Score:               {rep_res.contributions['identity']:.2f}")
    print(f"  • Liveness Score:               N/A (Recorded manual analysis)")
    print(f"  • Context Score:                {rep_res.contributions['context']:.2f}")
    print(f"  • Raw Fused Score:              {raw_fused:.2f}")
    corroboration_exists = not cap_activated
    print(f"  • Corroboration Exists:         {corroboration_exists}")
    print(f"  • 38 Cap Activated:             {cap_activated}")
    print(f"  • Exact Reason Cap Activated:   {cap_reason}")
    print(f"  • Final Score:                  {api_report.get('risk_score')}")
    print(f"  • Final Risk State:             {api_report.get('risk_state')}")
    print(f"  • Policy Decision:              {api_report.get('decision')}")
