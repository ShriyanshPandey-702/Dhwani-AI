#!/usr/bin/env python3
"""
δ ↔ TRAIN speaker-overlap audit (Phase 0, condition 2).

Question: does any speaker in TEST δ ("In-the-Wild", 58 named public figures)
also appear in a candidate TRAIN corpus? If one did, δ would not be unseen and
every future generalisation claim built on it would be inflated.

Two independent methods, because neither alone is sufficient:

  1. IDENTIFIER / PROVENANCE comparison.
     ASVspoof 2019 LA speaker IDs are anonymised (`LA_0079`) and the corpus is
     VCTK-derived — paid volunteer readers. δ speakers are named public
     figures. The identifier spaces do not intersect and cannot be matched
     directly, so this method can only establish a structural argument, never
     a measurement. That is why method 2 exists.

  2. SPEAKER-EMBEDDING comparison (the actual measurement).
     Uses the ECAPA-TDNN already vendored for VoiceShield's identity stream —
     no new model is introduced. Per-speaker mean embeddings are computed for
     both corpora and compared by cosine similarity. To know what "high" means,
     the cross-corpus distribution is judged against a within-ASVspoof impostor
     distribution (different speakers, same corpus) and the same-speaker
     distribution (same speaker, disjoint utterance halves) measured here.

Embeddings are used only in aggregate and are never written out, logged, or
emitted — consistent with the project's speaker-embedding privacy rule.

    python evaluation/audit_speaker_overlap.py \
        --delta data/external/InTheWild \
        --asvspoof data/external/LA_extract_full \
        --per-speaker 8
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))

from evaluation.datasets import asvspoof, inthewild  # noqa: E402
from evaluation.datasets.base import BONAFIDE  # noqa: E402
from evaluation.runners.score import load_audio  # noqa: E402

SEED = 1337


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def speaker_means(embedder, by_spk, per_speaker, rng, tag):
    """Mean L2-normalised embedding per speaker; also a disjoint second half."""
    out, halves = {}, {}
    for i, (spk, files) in enumerate(sorted(by_spk.items()), 1):
        picked = files if len(files) <= per_speaker else rng.sample(files, per_speaker)
        vecs = []
        for p in picked:
            audio = load_audio(p)
            if audio is None or len(audio) < 16000:
                continue
            vecs.append(embedder.embed(audio))
        if len(vecs) < 2:
            continue
        v = np.stack(vecs)
        m = v.mean(axis=0); m /= (np.linalg.norm(m) + 1e-12)
        out[spk] = m
        h = len(v) // 2
        a = v[:h].mean(axis=0); a /= (np.linalg.norm(a) + 1e-12)
        b = v[h:].mean(axis=0); b /= (np.linalg.norm(b) + 1e-12)
        halves[spk] = (a, b)
        if i % 10 == 0:
            log(f"  {tag}: {i}/{len(by_spk)} speakers embedded")
    return out, halves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--delta", required=True)
    ap.add_argument("--asvspoof", required=True)
    ap.add_argument("--per-speaker", type=int, default=8)
    ap.add_argument("--out", default="evaluation/results/phase0_speaker_overlap_audit.json")
    args = ap.parse_args()
    rng = random.Random(SEED)

    # ── Method 1: identifier / provenance ────────────────────────────────────
    delta = inthewild.load(args.delta)
    d_spk = sorted({s.speaker_id for s in delta if s.speaker_id})
    train = asvspoof.load_split(args.asvspoof, "train")
    a_spk = sorted({s.speaker_id for s in train if s.speaker_id})
    literal = sorted(set(d_spk) & set(a_spk))
    log(f"δ speakers={len(d_spk)}  ASVspoof-train speakers={len(a_spk)}  "
        f"literal ID intersection={len(literal)}")

    # ── Method 2: speaker embeddings ─────────────────────────────────────────
    from app.ml.identity.ecapa import ECAPAEmbedder
    embedder = ECAPAEmbedder(model_dir=str(REPO_ROOT / "services" / "api" / "models"))
    embedder.warmup()
    log("ECAPA-TDNN loaded (existing identity-stream model; no new detector)")

    d_by = collections.defaultdict(list)
    for s in delta:
        if s.label == BONAFIDE and s.speaker_id:      # genuine audio only
            d_by[s.speaker_id].append(s.audio_path)
    a_by = collections.defaultdict(list)
    for s in train:
        if s.label == BONAFIDE and s.speaker_id:
            a_by[s.speaker_id].append(s.audio_path)

    d_mean, d_half = speaker_means(embedder, d_by, args.per_speaker, rng, "δ")
    a_mean, a_half = speaker_means(embedder, a_by, args.per_speaker, rng, "ASVspoof")
    log(f"embedded {len(d_mean)} δ speakers, {len(a_mean)} ASVspoof-train speakers")

    # Reference distributions
    same = [float(np.dot(a, b)) for a, b in list(d_half.values()) + list(a_half.values())]
    ak = sorted(a_mean)
    impostor = [float(np.dot(a_mean[ak[i]], a_mean[ak[j]]))
                for i in range(len(ak)) for j in range(i + 1, len(ak))]

    # Cross-corpus
    dk = sorted(d_mean)
    cross, pairs = [], []
    for x in dk:
        for y in ak:
            c = float(np.dot(d_mean[x], a_mean[y]))
            cross.append(c)
            pairs.append((c, x, y))
    pairs.sort(reverse=True)

    same = np.array(same); impostor = np.array(impostor); cross = np.array(cross)
    # Flag anything above the impostor ceiling or a same-speaker floor.
    imp_max = float(impostor.max()); imp_p999 = float(np.percentile(impostor, 99.9))
    same_min = float(same.min()); same_p1 = float(np.percentile(same, 1))
    threshold = max(imp_max, imp_p999)
    flagged = [(round(c, 4), x, y) for c, x, y in pairs if c >= threshold]

    report = {
        "question": "Does any TEST δ speaker also appear in a candidate TRAIN corpus?",
        "delta": {"corpus": "In-the-Wild", "speakers": len(d_spk), "embedded": len(d_mean)},
        "train_corpus": {"corpus": "ASVspoof 2019 LA train", "speakers": len(a_spk),
                         "embedded": len(a_mean)},
        "method_1_identifier": {
            "literal_id_intersection": literal,
            "note": ("ASVspoof IDs are anonymised VCTK-derived readers; δ speakers are "
                     "named public figures. Disjoint identifier spaces — structural "
                     "argument only, not a measurement."),
        },
        "method_2_embedding": {
            "model": "ECAPA-TDNN spkrec-ecapa-voxceleb (existing identity stream)",
            "utterances_per_speaker": args.per_speaker,
            "same_speaker_similarity": {
                "n": int(same.size), "mean": float(same.mean()),
                "min": same_min, "p1": same_p1},
            "impostor_similarity_within_asvspoof": {
                "n": int(impostor.size), "mean": float(impostor.mean()),
                "max": imp_max, "p99.9": imp_p999},
            "cross_corpus_similarity": {
                "n": int(cross.size), "mean": float(cross.mean()),
                "max": float(cross.max()),
                "p99.9": float(np.percentile(cross, 99.9))},
            "flag_threshold": threshold,
            "flagged_pairs": flagged,
            "top_5_cross_pairs": [(round(c, 4), x, y) for c, x, y in pairs[:5]],
        },
        "verdict": ("NO OVERLAP DETECTED" if not flagged and not literal
                    else "REVIEW REQUIRED"),
        "caveat": ("ECAPA is VoxCeleb-trained, which suits celebrity speech but means "
                   "similarity is not a calibrated identity decision. This audit "
                   "detects overlap; it cannot prove its absence."),
    }
    Path(args.out).write_text(json.dumps(report, indent=2))

    log("── δ ↔ TRAIN speaker overlap ──")
    log(f"  literal ID intersection : {len(literal)}")
    log(f"  same-speaker cosine     : mean {same.mean():.4f}  min {same_min:.4f}")
    log(f"  impostor (ASVspoof)     : mean {impostor.mean():.4f}  max {imp_max:.4f}")
    log(f"  cross-corpus δ↔ASVspoof : mean {cross.mean():.4f}  max {cross.max():.4f}")
    log(f"  flag threshold {threshold:.4f} → flagged pairs: {len(flagged)}")
    log(f"  VERDICT: {report['verdict']}")
    log(f"done -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
