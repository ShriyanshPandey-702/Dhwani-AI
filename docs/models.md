# Dhwani AI — Models, Provenance and Limitations

Everything in this document is either a fact about a third-party checkpoint or a
number measured on a named machine. **No accuracy figure appears here, because
Dhwani AI has not evaluated any of these models on its own data.**

---

## 1. Two independent switches

Two different things are called "mode" in this system. They are not the same
axis and are reported separately on the wire.

| Axis | Field | Values | Meaning |
|---|---|---|---|
| Audio source | `risk_update.pipeline_mode` | `mock` / `live` | Generated PCM vs audio streamed from a device |
| Inference backend | `<stream>.pipeline_mode` | `real_ml` / `heuristic_demo` / `heuristic_fallback` | Which code produced this number |

`heuristic_fallback` means real ML was requested and could not be used. It is
never displayed as, or conflated with, `real_ml`. `is_mock` is `true` for both
heuristic modes and `false` only for a genuine model inference.

Global switch: `PIPELINE_MODE=mock` (default) or `PIPELINE_MODE=real_ml`.
Each stream degrades independently — a missing Whisper model does not stop
AASIST from running.

---

## 2. Voice authenticity — AASIST

| | |
|---|---|
| Model | AASIST / AASIST-L (spectro-temporal graph attention over raw waveform) |
| Source | https://github.com/clovaai/aasist |
| Licence | MIT, © 2021-present NAVER Corp |
| Paper | Jung et al., *AASIST*, ICASSP 2022 |
| Training data | ASVspoof 2019 Logical Access — **by the original authors, not by us** |
| Input | raw waveform, 16 kHz mono, 64600 samples (4.0375 s) |
| Output | 2 logits; index 1 = bona fide (upstream convention) |
| Parameters | AASIST 297,866 · AASIST-L 85,306 |
| Checkpoint SHA-256 | `51d2d9cf…a1c0` (AASIST) · `814331d0…e27a` (AASIST-L) |

The architecture is vendored **unmodified** at
`app/ml/authenticity/vendor/aasist_model.py` so the released weights load
`strict=True`; a test asserts that. Weights are not committed — fetch with
`python scripts/fetch_models.py`, which verifies each SHA-256 and refuses a
mismatch.

**Cascade.** AASIST-L runs first; AASIST runs only when the light tier lands
within `AASIST_CASCADE_MARGIN` of 0.5. This is a real tiering of two released
checkpoints, not a synthetic arrangement.

**Preprocessing.** Windows shorter than 64600 samples are tiled (as upstream's
evaluation does) and longer ones centre-cropped. Zero-padding is avoided because
padding is itself an artefact the model may react to.

**Known limitations.**
- Trained on ASVspoof 2019 LA: studio-quality English, 2019-era generators.
- Not evaluated on telephony codecs, Indian-English, or any 2024+ generator.
- Output is **not calibrated**. `confidence` is a decisiveness proxy capped at
  0.80, deliberately never 1.0.
- Undefined on non-speech. Silence produced a confident-looking "bona fide"
  score in testing, so the detector now refuses windows below a speech-energy
  floor and reports no evidence instead.

---

## 3. Speaker identity — ECAPA-TDNN

| | |
|---|---|
| Model | ECAPA-TDNN speaker embeddings, 192-d |
| Source | `speechbrain/spkrec-ecapa-voxceleb` (Hugging Face) |
| Licence | Apache-2.0 |
| Training data | VoxCeleb 1 + 2 — by the SpeechBrain authors, not by us |
| Input | 16 kHz mono, ≥ 1 s |
| Output | 192-d embedding; cosine similarity against the enrolled reference |

**Thresholds** (`ECAPA_VERIFIED_AT=0.60`, `ECAPA_MISMATCH_BELOW=0.35`) are the
model card's typical operating region. They are **not** calibrated for our
channel and are configuration, not constants.

**Semantics that must not be blurred.** A low similarity means the voice does
not match the enrolment. It is *not* evidence of synthesis. A genuine but
unfamiliar human and a cloned voice both score low here; this stream cannot
distinguish them and does not try. Only the Risk Engine combines the streams.

**Enrollment.** Production requires a trusted, out-of-band enrollment. The
current pipeline uses a **development fixture** that enrols from the first
analysable window of the session — acceptable for a prototype, unacceptable in
production, where an attacker would then define the reference.

**Privacy.** Embeddings live in memory for the session, are cleared on
disconnect, and never appear in evidence, logs or persistence. A test asserts no
array-shaped field can appear in identity evidence.

---

## 4. Speech-to-text — faster-whisper

| | |
|---|---|
| Model | Whisper (`tiny` by default) via faster-whisper / CTranslate2 |
| Source | Systran faster-whisper conversions on Hugging Face |
| Licence | MIT (faster-whisper); Whisper weights MIT (OpenAI) |
| Input | 16 kHz mono float32, passed in memory |
| Output | transcript, detected language + probability, per-segment `avg_logprob` |

Configurable via `WHISPER_MODEL_SIZE`, `WHISPER_COMPUTE_TYPE`,
`WHISPER_LANGUAGE` (empty = auto-detect), `WHISPER_BEAM_SIZE`.

Transcription runs on the same rolling analysis window as the other streams —
**chunked window transcription, not streaming ASR** with cross-window context.

**Known limitations.**
- Whisper supports many languages. That is **not** a claim that Dhwani AI is
  production-ready for Hindi or code-mixed Hinglish; we have not measured it.
- `tiny` is fast and error-prone. In testing it rendered "lakh" as "lock" — the
  risk-bearing tokens survived, but that is luck, not a guarantee.
- `confidence` derives from `avg_logprob` and is **not** calibrated.
- Silence yields no transcript rather than a fabricated utterance.

---

## 5. Conversation context — rules

Unchanged and **real**: deterministic lexical rules over whatever transcript is
supplied (`app/ml/context/classifier.py`, `rules-v0.2`). Real ML integration
changed only the transcript *source*. Provenance travels with the evidence
(`transcript_model`, `transcript_pipeline_mode`, `transcript_language`,
`transcript_confidence`, `transcript_is_mock`).

A planned transformer classifier would replace the rules; these remain a
high-precision fallback.

---

## 6. Streaming windows

```
client frames (~1 s)
     ↓
rolling per-session buffer (bounded to window + hop)
     ↓
overlapping windows: ANALYSIS_WINDOW_MS=4038, ANALYSIS_HOP_MS=1000
     ↓
model inference
```

Until a full window exists the streams report **insufficient evidence** rather
than scoring a short window. Buffers are cleared on disconnect. The heuristic
demo backend continues to run per frame, which is what keeps the demonstration
reproducible.

---

## 7. Measured latency

Measured with `python scripts/benchmark_ml.py`, 30 runs after warm-up, on one
machine. **Re-run it before quoting any number; this is not a published
benchmark and says nothing about other hardware.**

Host: macOS 26.6.2, arm64, Python 3.10.0, torch 2.2.2, 10 threads, CUDA
unavailable (CPU only). Window: 4037.5 ms / 64600 samples @ 16 kHz.

| Backend | Params | p50 | p95 | max | RTF (p95) |
|---|---|---|---|---|---|
| heuristic-dsp | — | 1.9 ms | 2.5 ms | 12.7 ms | — |
| AASIST-L | 85,306 | 455.7 ms | 805.1 ms | 908.8 ms | 0.199 |
| AASIST | 297,866 | 488.4 ms | 579.4 ms | 586.6 ms | 0.144 |
| AASIST-L + cascade | — | 401.9 ms | 502.5 ms | 593.0 ms | 0.125 |
| ECAPA-TDNN (embed + compare) | — | ~74 ms | ~156 ms | — | — |

RTF = p95 inference time ÷ window duration; below 1.0 means a single stream
keeps up with real time on this host. At this model size AASIST and AASIST-L
cost about the same on CPU — the light tier is not reliably faster here, and
run-to-run variance exceeds the gap.

**RTF < 1.0 is not the same as low latency.** It means the pipeline does not
fall behind; it says nothing about how long a caller waits for a verdict,
because a full 4038 ms window must accumulate first. End-to-end budget, measured
on the same host:

| Stage | Latency |
|---|---|
| Audio window accumulation (`ANALYSIS_WINDOW_MS`) | 4038 ms |
| Hop quantisation (`ANALYSIS_HOP_MS`) | 0–1000 ms |
| Authenticity inference (AASIST-L, n=20) | 421.7 ms mean · 513.5 ms p95 |
| Authenticity inference (production cascade, n=15) | 433.6 ms mean · 514.3 ms p95 |
| Risk fusion + policy decision (n=3000) | 0.0079 ms mean · 0.0083 ms p95 |
| Network transport | **not measured** |

* **Cold start** (session start → first authenticity evidence): **≈ 4.5 s**.
  Until then the Risk Engine reports `INSUFFICIENT_EVIDENCE`.
* **Steady state** (spoof onset mid-call → decision): **≈ 0.4–1.4 s**, excluding
  transport.

The streaming study's "0.0 s transition delay" counts **extra hops**, not
milliseconds, and must never be quoted as zero latency
(`docs/ml_evaluation.md` §7.7).

---

## 8. Evaluation — measured

Full protocol, tables and caveats: **[`docs/ml_evaluation.md`](ml_evaluation.md)**.
Raw scores, manifests and leakage audits: `evaluation/results/`.
Everything below is a real measurement of the shipped AASIST-L checkpoint
(`sha256 814331d0…ce27a`), not a figure quoted from a paper.

| Protocol | Scope | ROC-AUC | EER |
|---|---|---|---|
| ASVspoof 2019 LA, official dev→eval | full LA corpus obtained | 0.9987 | 1.07% |
| ASVspoof 2019 LA, speaker-disjoint | full LA corpus obtained | 0.9990 | 1.20% |
| **MLAAD-tiny subset**, generator-disjoint | subset of MLAAD-**tiny** — not full MLAAD v9 | **0.6055** | **43.40%** |
| **WaveFake subset** + LJSpeech | ~150 files/vocoder; single-speaker corpus | **0.5970** | **41.60%** |

The last two rows are **subsets**, and the WaveFake row is single-speaker
English read speech — diagnostic, **not** a real-world performance figure.

**The honest summary is that the in-domain rows do not generalise to the
out-of-domain rows.** The detector is excellent on the corpus it was trained on
and close to a coin flip on both out-of-domain corpora; 7 of 22 unseen MLAAD
generators score *below chance*.

The mechanism, isolated by the WaveFake run, is **domain shift in the bona-fide
distribution** rather than generator novelty. Mean score on genuine human
speech: **0.007** on ASVspoof, **0.529** on MLAAD, **0.906** on LJSpeech. On an
unfamiliar corpus AASIST calls real speech synthetic, and it scores unseen
vocoders no better than the vocoders its threshold was tuned on (AUC 0.5970 vs
0.5998). This is a stronger and more useful statement than "modern TTS is hard".

Two further findings bound what may be claimed:

* **Thresholds do not transfer across attack families.** A cut point chosen on
  ASVspoof dev to hold FAR ≤ 1% admitted **16.93%** of spoofs on eval, while
  ROC-AUC moved only 0.9992 → 0.9987. No fixed operating point is safe.
* **Calibration does not transfer either, and good calibration is not good
  detection.** Isotonic regression improves calibration across speakers
  (ECE 0.0202 → 0.0075) and degrades it across attacks (ECE 0.0186 → 0.0562).
  On WaveFake, Platt achieves the best ECE in the whole evaluation (0.0093) on a
  split whose ROC-AUC is 0.5970 — a perfectly calibrated coin flip. The shipped
  calibrator is therefore **reported but not fused**
  (`USE_CALIBRATED_SCORE_FOR_FUSION = False`).

Robustness (19 synthetic conditions): band-limiting, 8 kHz resampling and µ-law
are essentially free (ΔAUC ≤ 0.0002); `reverb_300ms` collapses the detector to
AUC 0.484 and `noise_white_0db` to 0.530. Degradation almost always inflates
false *rejections*, not false accepts — the exception is quiet audio
(`gain_minus_20db`, FAR 18.00%), which is the one condition that makes the
system less safe.

Streaming: 0 isolated decision flips across all streams and aggregators;
silence and sub-window speech produce **no evidence** rather than a guess. No
aggregation change was warranted. The measured "0.0 s transition delay" means
**zero extra hops** beyond the first window containing the switch — it is *not*
zero end-to-end latency. Measured decomposition: 4038 ms window fill + 1000 ms
hop + **421.7 ms** mean inference (513.5 ms p95) + 0.0079 ms policy, giving
**≈4.5 s cold start** and **≈0.4–1.4 s steady-state** detection delay,
excluding transport. See `docs/ml_evaluation.md` §7.7.

So the supportable claim is unchanged in spirit and now has numbers behind it:

> Dhwani AI performs multi-signal detection and risk-based decisioning using
> pretrained open-source models. Its authenticity detector is strong in-domain
> (ASVspoof 2019 LA: ROC-AUC 0.9987, EER 1.07%) and **near chance out of domain**
> (MLAAD-tiny unseen TTS: 0.6055; WaveFake unseen vocoders: 0.5970), because it
> generalises poorly to unfamiliar recording conditions in *both* classes. It has
> not been measured on telephony, on Indian-English, or on live call audio.

Datasets used: ASVspoof 2019 LA (full, 7.64 GB), MLAAD-tiny (balanced subset),
WaveFake + LJSpeech (documented subset). Not yet obtained: IndieFake, SEA-Spoof,
HAV-DF. The full MLAAD v9 release is
behind a Fraunhofer owncloud share that returned 401 to automated access.

Dhwani AI has **not** trained on private telecom or banking data, and has no
partnerships or data-sharing arrangements of any kind. No model in this repo has
been fine-tuned by us; all weights are upstream releases.

---

## 9. Data retention

| Data | Retained? |
|---|---|
| Raw call audio | **No.** Decoded to memory, windowed, discarded. Never written to disk. |
| Rolling audio buffer | In memory only, bounded to window + hop, cleared on disconnect |
| Speaker embeddings | In memory only, per session, cleared on disconnect. Never emitted, logged or persisted |
| Transcript text | Held in the current context evidence; not logged |
| Evidence + risk snapshots | Persisted (scores, bands, flags, model versions) |
| Incident records | Persisted with a SHA-256 integrity hash |

Whisper receives audio as an in-memory array; no temporary WAV is written.

---

## 10. Reproducing this setup

```bash
cd services/api
pip install -r requirements.txt
python scripts/fetch_models.py          # AASIST checkpoints, SHA-256 verified
PIPELINE_MODE=real_ml uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

ECAPA-TDNN and Whisper weights are fetched from Hugging Face on first use and
cached. Without network access those two streams fall back and say so; AASIST
works offline once fetched.

Leave `PIPELINE_MODE=mock` for the deterministic demonstration.
