#!/usr/bin/env python3
"""
Controlled Memory Investigation for VoiceShield Phase 1.6
==========================================================
Isolates memory consumption across:
A. Repeated AASIST inference only (120 iterations)
B. Repeated ECAPA inference only (120 iterations)
C. Repeated AASIST + ECAPA inference (120 iterations)
D. Full production streaming pipeline (120 seconds, 480 chunks)

Tracks:
- Current RSS (via psutil)
- Python heap object count (via gc.get_objects())
- PyTorch / tensor memory allocations
- Internal session dictionaries and audio buffers
"""
from __future__ import annotations

import asyncio
import gc
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List

import numpy as np
import psutil
import torch

API = Path(__file__).resolve().parents[1]
ROOT = API.parent.parent
for p in (str(API), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("PIPELINE_MODE", "real_ml")

from app.core.config import settings
from app.ml.authenticity.detector import AuthenticityDetector
from app.ml.identity.speaker import SpeakerIdentity
from app.ml.preprocessing.stream import StreamWindower, SAMPLE_RATE
from app.ml.preprocessing.ingest import iter_pcm_chunks
from app.websocket.manager import SessionState, manager
from app.websocket.pipeline import (
    analyze_window, stream_windower, authenticity_detector,
    speaker_identity, fuse_and_decide
)


def banner(t: str):
    print(f"\n{'═'*78}\n  {t}\n{'═'*78}")

def make_audio(secs: float = 4.5, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(SAMPLE_RATE * secs)) / SAMPLE_RATE
    a = 0.3 * np.sin(2 * np.pi * 150 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))
    return (a + rng.standard_normal(t.size) * 0.01).astype(np.float32)

proc = psutil.Process()

def get_rss_mb() -> float:
    return proc.memory_info().rss / (1024.0 * 1024.0)

def get_obj_count() -> int:
    return len(gc.get_objects())


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT A: REPEATED AASIST INFERENCE ONLY
# ─────────────────────────────────────────────────────────────────────────────
def exp_a_aasist():
    banner("EXPERIMENT A: REPEATED AASIST INFERENCE ONLY (120 ITERATIONS)")
    audio = make_audio(4.038, seed=1)
    
    # Warmup
    authenticity_detector.analyze(audio)
    
    rss0 = get_rss_mb()
    objs0 = get_obj_count()
    print(f"  Start      : RSS = {rss0:.2f} MB | Python Objects = {objs0}")
    
    milestones = {}
    for i in range(1, 121):
        authenticity_detector.analyze(audio)
        if i in (30, 60, 90, 120):
            rss_i = get_rss_mb()
            objs_i = get_obj_count()
            milestones[i] = (rss_i, objs_i)
            print(f"  Iter {i:3d}   : RSS = {rss_i:.2f} MB (+{rss_i - rss0:6.2f} MB) | Objects = {objs_i} ({objs_i - objs0:+d})")
            
    growth_30_to_120 = milestones[120][0] - milestones[30][0]
    print(f"  Growth (30 -> 120 iter): {growth_30_to_120:+.2f} MB")
    return {"name": "AASIST Only", "growth": growth_30_to_120, "milestones": milestones}


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT B: REPEATED ECAPA INFERENCE ONLY
# ─────────────────────────────────────────────────────────────────────────────
def exp_b_ecapa():
    banner("EXPERIMENT B: REPEATED ECAPA INFERENCE ONLY (120 ITERATIONS)")
    audio = make_audio(4.038, seed=2)
    sid = "mem-ecapa"
    speaker_identity.enroll(sid, audio)
    speaker_identity.analyze(sid, audio)
    
    rss0 = get_rss_mb()
    objs0 = get_obj_count()
    print(f"  Start      : RSS = {rss0:.2f} MB | Python Objects = {objs0}")
    
    milestones = {}
    for i in range(1, 121):
        speaker_identity.analyze(sid, audio)
        if i in (30, 60, 90, 120):
            rss_i = get_rss_mb()
            objs_i = get_obj_count()
            milestones[i] = (rss_i, objs_i)
            print(f"  Iter {i:3d}   : RSS = {rss_i:.2f} MB (+{rss_i - rss0:6.2f} MB) | Objects = {objs_i} ({objs_i - objs0:+d})")
            
    growth_30_to_120 = milestones[120][0] - milestones[30][0]
    speaker_identity.clear(sid)
    print(f"  Growth (30 -> 120 iter): {growth_30_to_120:+.2f} MB")
    return {"name": "ECAPA Only", "growth": growth_30_to_120, "milestones": milestones}


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT C: REPEATED AASIST + ECAPA INFERENCE
# ─────────────────────────────────────────────────────────────────────────────
def exp_c_both():
    banner("EXPERIMENT C: REPEATED AASIST + ECAPA INFERENCE (120 ITERATIONS)")
    audio = make_audio(4.038, seed=3)
    sid = "mem-both"
    speaker_identity.enroll(sid, audio)
    
    rss0 = get_rss_mb()
    objs0 = get_obj_count()
    print(f"  Start      : RSS = {rss0:.2f} MB | Python Objects = {objs0}")
    
    milestones = {}
    for i in range(1, 121):
        authenticity_detector.analyze(audio)
        speaker_identity.analyze(sid, audio)
        if i in (30, 60, 90, 120):
            rss_i = get_rss_mb()
            objs_i = get_obj_count()
            milestones[i] = (rss_i, objs_i)
            print(f"  Iter {i:3d}   : RSS = {rss_i:.2f} MB (+{rss_i - rss0:6.2f} MB) | Objects = {objs_i} ({objs_i - objs0:+d})")
            
    growth_30_to_120 = milestones[120][0] - milestones[30][0]
    speaker_identity.clear(sid)
    print(f"  Growth (30 -> 120 iter): {growth_30_to_120:+.2f} MB")
    return {"name": "AASIST + ECAPA", "growth": growth_30_to_120, "milestones": milestones}


# ─────────────────────────────────────────────────────────────────────────────
# EXPERIMENT D: FULL PRODUCTION STREAMING PIPELINE (120s SOAK)
# ─────────────────────────────────────────────────────────────────────────────
async def exp_d_production():
    banner("EXPERIMENT D: FULL PRODUCTION STREAMING PIPELINE (120s SOAK)")
    SID = "mem-prod"
    from app.risk.policy import DEFAULT_POLICY_CONFIG
    from app.ml.preprocessing.audio import decode_pcm
    
    stream_windower.reset(SID)
    speaker_identity.clear(SID)
    state = SessionState(session_id=SID, user_id="mem", policy_config=dict(DEFAULT_POLICY_CONFIG))
    pool = ThreadPoolExecutor(max_workers=settings.ML_POOL_WORKERS, thread_name_prefix="mem_prod")
    loop = asyncio.get_running_loop()
    
    audio = make_audio(65.0, seed=4)
    chunks = list(iter_pcm_chunks(audio, chunk_ms=250))
    
    # Warmup
    raw0 = decode_pcm(chunks[0])
    stream_windower.push(SID, raw0)
    
    rss0 = get_rss_mb()
    objs0 = get_obj_count()
    print(f"  Start (t=0s) : RSS = {rss0:.2f} MB | Python Objects = {objs0}")
    
    milestones = {}
    t0 = time.perf_counter()
    idx = 0
    
    # Track internal data structure sizes
    internal_telemetry = {}
    
    while time.perf_counter() - t0 <= 120.5:
        elapsed = time.perf_counter() - t0
        pcm = chunks[idx % len(chunks)]
        idx += 1
        
        async with state.processing_lock:
            def step():
                raw = decode_pcm(pcm)
                w = stream_windower.push(SID, raw)
                if w is None:
                    return False
                if not speaker_identity.is_enrolled(SID):
                    speaker_identity.enroll(SID, w)
                a = authenticity_detector.analyze(w)
                i = speaker_identity.analyze(SID, w)
                state.last_authenticity = a.to_dict() if a else None
                state.last_identity = i.to_dict() if i else None
                fuse_and_decide(state, "live")
                return True
                
            await loop.run_in_executor(pool, step)
            
        # Sample at 20s, 30s, 60s, 90s, 120s
        for target in (20, 30, 60, 90, 120):
            if target not in milestones and elapsed >= target:
                rss_t = get_rss_mb()
                objs_t = get_obj_count()
                
                # Check internal sizes
                buf_samples = stream_windower._buffers.get(SID).samples.size if SID in stream_windower._buffers else 0
                buf_bytes = stream_windower._buffers.get(SID).samples.nbytes if SID in stream_windower._buffers else 0
                history_len = len(speaker_identity._history.get(SID, []))
                risk_hist_len = len(state.risk_history)
                
                milestones[target] = (rss_t, objs_t)
                internal_telemetry[target] = {
                    "buf_samples": buf_samples,
                    "buf_bytes": buf_bytes,
                    "id_history_len": history_len,
                    "risk_history_len": risk_hist_len
                }
                print(f"  t={target:3d}s       : RSS = {rss_t:.2f} MB (+{rss_t - rss0:6.2f} MB) | Objects = {objs_t} ({objs_t - objs0:+d}) | Buf = {buf_samples} samp ({buf_bytes/1024:.1f} KB) | RiskHist = {risk_hist_len}")
                
        await asyncio.sleep(0.25)

    if 120 not in milestones:
        milestones[120] = (get_rss_mb(), get_obj_count())

        
    pool.shutdown(wait=False)
    stream_windower.reset(SID)
    speaker_identity.clear(SID)
    
    growth_30_to_120 = milestones[120][0] - milestones[30][0]
    print(f"\n  Production Soak Growth (30s -> 120s): {growth_30_to_120:+.2f} MB")
    return {"name": "Production Streaming", "growth": growth_30_to_120, "milestones": milestones, "telemetry": internal_telemetry}


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
async def main():
    banner("CONTROLLED MEMORY EXPERIMENT SUITE")
    print(f"  PyTorch version : {torch.__version__}")
    print(f"  PyTorch threads : {torch.get_num_threads()}")
    
    res_a = exp_a_aasist()
    res_b = exp_b_ecapa()
    res_c = exp_c_both()
    res_d = await exp_d_production()
    
    banner("COMPARATIVE MEMORY ANALYSIS RESULTS")
    print(f"  {'Experiment':<30} | {'30s/Iter RSS':<14} | {'120s/Iter RSS':<14} | {'Post-Stab Growth':<16}")
    print(f"  {'-'*30}-+-{'-'*14}-+-{'-'*14}-+-{'-'*16}")
    for r in (res_a, res_b, res_c):
        k30 = list(r['milestones'].keys())[0]  # 30
        k120 = list(r['milestones'].keys())[-1] # 120
        v30 = r['milestones'][k30][0]
        v120 = r['milestones'][k120][0]
        print(f"  {r['name']:<30} | {v30:11.2f} MB | {v120:11.2f} MB | {r['growth']:+13.2f} MB")
    
    v30_d = res_d['milestones'][30][0]
    v120_d = res_d['milestones'][120][0]
    print(f"  {res_d['name']:<30} | {v30_d:11.2f} MB | {v120_d:11.2f} MB | {res_d['growth']:+13.2f} MB")

if __name__ == "__main__":
    asyncio.run(main())
