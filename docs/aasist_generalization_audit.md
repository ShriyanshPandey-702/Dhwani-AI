# Dhwani AI — AASIST Domain-Generalization Audit

**Status: AUDIT ONLY. Nothing in this document has been implemented.**
No model was trained, no dataset downloaded, no source file modified, no
threshold changed. Every measured number quoted here comes from the frozen
baseline in [`ml_evaluation.md`](ml_evaluation.md) and
`evaluation/results/`; every forward-looking number is labelled as an estimate.

---

## 1. Executive Summary

The frozen baseline shows a detector that is excellent on its training corpus
and near chance on two independent out-of-domain corpora:

| Protocol | Scope | ROC-AUC | EER |
|---|---|---|---|
| ASVspoof 2019 LA, official dev→eval | full corpus obtained | 0.9987 | 1.07% |
| ASVspoof 2019 LA, speaker-disjoint | full corpus obtained | 0.9990 | 1.20% |
| MLAAD-**tiny** subset, generator-disjoint | subset of a compact release | 0.6055 | 43.40% |
| WaveFake subset + LJSpeech | subset, single speaker | 0.5970 | 41.60% |

**The diagnosis is not the obvious one.** The dominant failure is *not* that
modern TTS has become too good to detect. It is **domain shift in the bona-fide
distribution**. Three pieces of evidence, all already measured:

1. On WaveFake the detector scores *genuine, unmodified human speech* at a mean
   spoof probability of **0.906** (versus 0.007 on ASVspoof bona fide).
2. On WaveFake, held-out vocoders score **the same** as the vocoders the
   threshold was tuned on (AUC 0.5970 vs 0.5998). Generator novelty explains
   almost none of the gap.
3. Class-mean separation collapses monotonically with corpus distance:
   0.948 (ASVspoof) → 0.114 (MLAAD-tiny) → 0.034 (WaveFake).

AASIST-L learned what bona fide sounds like *in ASVspoof 2019 LA*. Any other
clean corpus reads as synthetic.

**This reframes the entire remediation plan.** Adding more spoof types would
address the wrong failure. The primary intervention must be **bona-fide
diversity across corpora, channels and recording conditions**, with modern
spoof coverage as a secondary axis.

Four findings gate any future work:

- **The repository has zero training capability.** It is strictly inference-only
  (§3). Everything — data loading, losses, optimiser, checkpointing,
  reproducibility — must be built before a single training step.
- **MLAAD-tiny is licence-blocked for training.** Its `NOTICE_NO_COMMERCIAL_USE`
  states CC BY-NC and explicitly covers "model training, model evaluation,
  hyperparameter tuning". It must remain an **unseen non-commercial test set**
  (§4, §7).
- **AASIST-L is tiny (85,306 parameters).** Full fine-tuning is computationally
  trivial; the real risk is catastrophic forgetting and overfitting, not compute.
- **If you tune against MLAAD-tiny and WaveFake, they stop being unseen.** A
  fourth, untouched corpus must be reserved before any training begins (§12).

Recommended primary strategy: **balanced multi-domain fine-tuning with ASVspoof
rehearsal, checkpoint selection on worst-case-domain EER**, not average.

---

## 2. Current AASIST Architecture

Audited in `services/api/app/ml/authenticity/`.

| Property | Value | Source |
|---|---|---|
| Architecture | AASIST — graph attention over raw waveform (spectro-temporal heterogeneous GAT) | `vendor/aasist_model.py` |
| Upstream | `github.com/clovaai/aasist`, © NAVER Corp | `vendor/NOTICE.md` |
| Licence (code) | **MIT** — full text vendored at `vendor/LICENSE.aasist` | verified |
| Paper | Jung et al., ICASSP 2022 | `aasist.py` docstring |
| Vendoring | architecture file **unmodified** apart from a header, so released checkpoints load with `strict=True` | `NOTICE.md` |
| Active variant | `AASIST-L`, **85,306** parameters | `AASIST_VARIANT`; runtime log |
| Heavy tier | `AASIST`, **297,866** parameters | runtime log |
| Trained on | ASVspoof 2019 LA **train** (A01–A06), by the original authors — *not by us* | upstream |
| Input | raw waveform, **16 kHz mono**, **64,600 samples ≈ 4.0375 s** | `NB_SAMP` |
| Output | 2 logits; **index 1 is bona fide** (upstream convention); score = `1 − softmax[1]` | `_run()` |

### Checkpoints and verification

| Variant | File | Size | SHA-256 (verified on disk) |
|---|---|---|---|
| AASIST-L | `models/aasist/AASIST-L.pth` | 0.43 MB | `814331d0…ce27a` |
| AASIST | `models/aasist/AASIST.pth` | 1.28 MB | `51d2d9cf…a1c0` |

Weights are **never committed**. `scripts/fetch_models.py` downloads them and
verifies SHA-256 before use; a mismatch aborts. `AASISTDetector.missing_checkpoints()`
is checked at start-up, and a missing checkpoint raises `CheckpointMissing`
rather than silently substituting a heuristic. Expected hashes are additionally
pinned in `aasist.py::CHECKPOINTS`, so the verification is duplicated at both
the fetch and the load path.

### Preprocessing and gating

| Stage | Behaviour |
|---|---|
| Decode | int16 LE PCM → float32 `[-1, 1]` (`preprocessing/audio.py`) |
| Resampling | `scipy.resample_poly` when source ≠ 16 kHz (evaluation path) |
| Channels | mono (averaged) |
| Normalisation | **none beyond float32 scaling** — no CMVN, no peak/RMS normalisation |
| Length policy | **tile** if short, **centre-crop** if long (upstream convention; tiling avoids the zero-pad artefact) |
| Speech gating | mean-square energy `< 1e-5` → return `None` (no evidence), *not* a score |
| Min duration | `MIN_ANALYSIS_MS = 400`; below this → `None` |
| Streaming | window 4038 ms, hop 1000 ms (`StreamWindower`) |

The energy gate is a **level-based guard, not a VAD.** There is no
voice-activity model. This matters: §7.6 of the baseline found
`gain_minus_20db` is the one degradation that *raises* false accepts (FAR 18%,
9× clean), and a level-threshold gate is exactly the wrong instrument for
detecting that condition.

### Inference path and cascade

`AuthenticityDetector.analyze()` → `AASISTDetector.score()`:

1. Run `AASIST-L`.
2. If `|p − 0.5| < AASIST_CASCADE_MARGIN` (0.25), re-run on the heavy `AASIST`
   and take its score.
3. `confidence` = `clip(0.25 + 0.5·decisiveness·sufficiency, 0, 0.80)` —
   **deliberately capped at 0.80**, an explicit statement that this checkpoint
   is unvalidated on our audio.
4. Optional isotonic calibrator applied **only** in `real_ml` mode; the fused
   value stays raw because `USE_CALIBRATED_SCORE_FOR_FUSION = False`.

Cascade was **disabled for all benchmark runs** (escalation depends on the score
being measured, which is valid as policy but invalid as a benchmark).

### Device behaviour

`resolve_device()`: honours an explicit `ML_DEVICE`, else CUDA if available,
else **CPU**. MPS is deliberately not selected — AASIST's FFT ops fall back to
CPU anyway. Verified environment: macOS arm64, torch 2.2.2, 10 threads,
**CUDA unavailable**.

### Inference-only or fine-tunable?

**Structurally fine-tunable; operationally inference-only.**

- The vendored `Model` is a standard `nn.Module` with `BatchNorm1d/2d`, dropout
  and ordinary trainable parameters — gradients would flow normally.
- But every call site does `model.eval()` + `torch.no_grad()`, weights are
  loaded with `strict=True` from a fixed hash, and there is no optimiser, loss,
  data loader or checkpoint-writing path anywhere in the repository.

Two consequences for a future phase: `BatchNorm` layers will update running
statistics the moment `.train()` is called (a real catastrophic-forgetting
vector at small batch sizes), and any new checkpoint invalidates the SHA-256
pinning in two places plus the shipped calibrator's provenance.

---

## 3. Current Training / Fine-Tuning Capability

**None. Verified by exhaustive search of all project Python (excluding
`.venv`/`node_modules`):**

| Capability | Present? | Evidence |
|---|---|---|
| Training script | **No** | `services/api/scripts/` holds only `fetch_models.py`, `benchmark_ml.py` |
| Fine-tuning script | **No** | — |
| `.backward()` / optimiser / `CrossEntropyLoss` / `lr_scheduler` / `GradScaler` / `DataLoader` | **No** | zero matches repo-wide |
| `.train()` call | **No** | zero matches |
| Dataset loaders | **Evaluation-only** | `evaluation/datasets/{asvspoof,mlaad,wavefake,base}.py` return `Sample` metadata lists, not tensor batches |
| Loss / optimiser / LR schedule | **No** | — |
| Checkpoint save/resume | **No** | load-only, `strict=True` |
| Mixed precision / grad accumulation | **No** | — |
| Class weighting / early stopping | **No** | — |
| Experiment config | **No** | `evaluation/configs/` exists and is **empty** |
| Seed control | **Partial** | `SEED = 1337` in each runner; `random.Random(seed)` for sampling only — no torch/numpy global seeding, no cuDNN determinism |
| Reproducibility | **Strong, for evaluation** | `run_metadata.json` records checkpoint SHA-256, preprocessing version, software/hardware, seed, settings |

### What must be added later (do NOT add now)

1. `training/` package, separate from `evaluation/` so the benchmark harness
   cannot import training code (protects against leakage by construction).
2. A `torch.utils.data.Dataset` yielding `(waveform[64600], label)` with the
   **same** `prep-v1` preprocessing as inference — any divergence silently
   invalidates comparison against the frozen baseline.
3. Loss: `CrossEntropyLoss` with class weights (ASVspoof LA is ~9:1 spoof-heavy)
   or balanced sampling; upstream AASIST used weighted CE.
4. Optimiser + scheduler, gradient clipping, deterministic seeding of
   `random`/`numpy`/`torch`(+cuda), `cudnn.deterministic`.
5. Checkpoint writer emitting SHA-256, full config, and the resolved split
   manifests alongside every saved model.
6. Early stopping and checkpoint selection on a **worst-domain** metric (§9).
7. An experiment registry (§11).

---

## 4. Dataset Inventory

### 4.1 ASVspoof 2019 LA — **full corpus obtained**

| | |
|---|---|
| Version | ASVspoof 2019, Logical Access |
| Source | Edinburgh DataShare, DOI 10.7488/ds/2555 |
| Licence | **Open Data Commons Attribution (ODC-BY)** — `LICENSE.txt` verified in the extracted tree |
| Redistribution | Permitted with attribution |
| Archive | 7.64 GB, `sha256 208a7e4e…e4ec`, 122,328 files |
| On disk | `LA_extract_full` 96,919 flac; `LA_extract` 55,388 flac (earlier partial recovery, still referenced by two frozen runs) |

Official protocol splits present locally:

| Split | Files | Bona fide | Spoof | Speakers | Attacks |
|---|---|---|---|---|---|
| train | 25,380 | 2,580 | 22,800 | 20 | A01–A06 |
| dev | 24,844 | 2,548 | 22,296 | 20 | A01–A06 |
| eval | 71,237 | 7,355 | 63,882 | 67 | A07–A19 |

**Speaker overlap measured: train∩dev = 0, train∩eval = 0, dev∩eval = 0.** All
three splits are speaker-disjoint by construction.

Suitability: **train → TRAIN (rehearsal only, see §5)** · **dev → VALIDATION** ·
**eval → the frozen regression benchmark**. Note the eval split is already
consumed by the frozen baseline; re-using it as the *primary* selection signal
in a future phase would silently convert it into a validation set.

### 4.2 MLAAD-**tiny** subset — *not full MLAAD*

| | |
|---|---|
| Name | **MLAAD-tiny v9** — the authors' own compact release, **not MLAAD v9 full** |
| Source | HuggingFace `mueller91/MLAAD-tiny` (anonymous access rate-limited, HTTP 429) |
| Licence | **CC BY-NC** for `fake/` — `NOTICE_NO_COMMERCIAL_USE.txt` |
| Redistribution | **No** (non-commercial; commercial use requires a Fraunhofer licence) |
| Frozen eval subset | calibration 196 bona fide / 155 spoof · test 196 bona fide / 159 spoof |
| Current local pool | 10,913 wav — 3,013 bona fide (`original/`), 7,900 spoof (`fake/`), 79 generator directories |
| Languages | en, de only (spoof: 6,400 en / 1,500 de; bona fide: 1,693 en / 1,320 de) |
| Speakers | not annotated per-file in this release |
| Generators | 22 unseen TTS systems in the frozen test side |

> **Licence blocker.** The notice states verbatim that the restriction "applies
> to model training, model evaluation, hyperparameter tuning, and any other use
> of the data." The existing non-commercial evaluation is within scope; **using
> it as training data for anything commercial is not.** Treat MLAAD-tiny as
> UNSEEN TEST only, and obtain a written licence before any other use.

> **Scope discipline.** The local pool has grown since the frozen run (a
> background retry loop kept fetching). The benchmark is defined by the
> committed manifests, not by what is on disk today. Never quote the two as one
> number, and never call this full MLAAD.

Suitability: **UNSEEN TEST only.** Not train. Not validation.

### 4.3 WaveFake subset + LJSpeech — *not general real-world performance*

| | |
|---|---|
| Name | WaveFake (Zenodo 5642694) + LJSpeech-1.1 |
| Licence | WaveFake **CC-BY-SA-4.0**; LJSpeech **public domain** |
| Redistribution | Permitted; **CC-BY-SA share-alike needs legal review** before shipping derivatives |
| Full archive | 28.9 GB, 134,278 entries (indexed via ZIP64 central directory; not fully downloaded) |
| Local subset | **1,057 spoof** (~150/vocoder × 7) + 11,573 LJSpeech bona fide available |
| Frozen eval subset | calibration 432/432 · test 625/625 |
| Languages | **English only** |
| Speakers | **One** (LJSpeech is single-speaker) |
| Vocoders | 7 LJSpeech vocoders; JSUT (Japanese) and Common-Voice FastSpeech2 portions excluded |

> **Scope discipline.** Single speaker, single corpus, studio read speech. This
> is a **diagnostic probe**, not a measurement of real-world performance. Its
> value is that it isolates the bona-fide-shift mechanism (§6) — nothing more.

Suitability: **UNSEEN TEST** (current role). Could become TRAIN in a future
phase *only* with a strict vocoder split, and only if the CC-BY-SA implications
for released weights are cleared.

### 4.4 Not obtained

| Dataset | Blocker |
|---|---|
| MLAAD v9 **full** | Fraunhofer owncloud share returned HTTP 401 to automated access |
| IndieFake, SEA-Spoof, HAV-DF | not attempted in the evaluation phase |

---

## 5. Leakage and Split Analysis

### 5.1 Leakage axes that must be controlled

| Axis | Risk | Control |
|---|---|---|
| **Speaker** | same voice in train and test → memorised timbre | disjoint speaker IDs; ASVspoof provides them, LJSpeech makes it impossible (1 speaker) |
| **Utterance / content** | same sentence bona fide and spoofed across splits | hash-partition utterance IDs (the WaveFake run already does this: SHA-256 parity, measured overlap 0) |
| **Generator / vocoder** | the "unseen generator" claim collapses | partition by generator *family*, not by `lang/system` string |
| **Source corpus** | model learns "corpus ⇒ class" instead of "artefact ⇒ class" — **the failure actually observed** | every corpus must contribute **both** classes |
| **Language** | language becomes a class proxy | balance languages within each class |
| **Recording channel** | channel becomes a class proxy | augment both classes identically |

### 5.2 The corpus-as-label trap — the single most important constraint

The baseline shows AASIST already keyed on ASVspoof's bona-fide channel. The
naive remedy — "add MLAAD spoof audio to training" — would make this **worse**,
because MLAAD spoof and ASVspoof bona fide differ by corpus as well as by class.
The model would learn the corpus, score perfectly in validation, and fail again
on the next corpus.

**Hard rule for any future training set: every source corpus must supply both
bona fide and spoof examples.** A corpus that can only supply one class must be
paired with bona fide from the *same* recording domain, or excluded.

WaveFake satisfies this naturally (LJSpeech original vs LJSpeech vocoded).
MLAAD-tiny nominally has `original/` and `fake/`, but their bona-fide provenance
must be verified as same-domain before use — and its licence blocks training
anyway.

### 5.3 A caveat inherited from the baseline

The MLAAD run is disjoint at `language/system` granularity, but four generator
**families** (Edge-TTS, FishTTS, Higgs-Audio-V2, Kani-TTS-370M) appear on both
sides under different languages. Because both calibrators are monotone this
cannot inflate AUC/EER — only the chosen threshold — and excluding all four,
4 of the remaining 18 generators still score below chance. **A future split must
partition on generator family, not on the `lang/system` string.**

### 5.4 Recommended separation

| Role | Content | Rule |
|---|---|---|
| **TRAIN** | ASVspoof 2019 LA train (A01–A06) as *rehearsal anchor* + new multi-domain corpora (§7), every corpus contributing both classes | never touched by selection |
| **VALIDATION** | ASVspoof 2019 LA dev + a held-out generator group and speaker group from each new corpus | early stopping + checkpoint selection only |
| **UNSEEN TEST α** | ASVspoof 2019 LA eval (A07–A19) | **frozen regression benchmark** — detects forgetting |
| **UNSEEN TEST β** | MLAAD-tiny subset (frozen manifests) | never in train/val |
| **UNSEEN TEST γ** | WaveFake subset (frozen manifests) | never in train/val |
| **UNSEEN TEST δ** | **a fourth corpus, not yet acquired, reserved and untouched** | the only genuinely unseen set after β and γ inform design |

**Why δ is non-negotiable.** β and γ have now shaped the diagnosis and will
shape the training design. Human-in-the-loop iteration against them makes them
validation sets in all but name. Without δ there is no honest generalisation
claim. It must be selected, hashed and sealed **before** training starts, and
opened exactly once.

### 5.5 Should ASVspoof be training, benchmark, or both?

**Both — but with different splits, and for two distinct reasons.**

- `train` (A01–A06) → **TRAIN, as a rehearsal anchor.** It teaches nothing new
  (the checkpoint already saw it) but replaying it is the standard defence
  against catastrophic forgetting. Without it, ASVspoof performance will
  regress, and that regression is a real loss: 0.9987 AUC is genuine capability.
- `dev` → **VALIDATION**, as in the frozen baseline.
- `eval` (A07–A19) → **UNSEEN TEST α**, the regression benchmark. Its purpose
  changes from "headline result" to "did we break what already worked".

It cannot be *only* a benchmark, because dropping it from training guarantees
forgetting; and it cannot be *only* training, because it is the sole evidence
that the model retains in-domain skill.

---

## 6. Domain-Generalization Diagnosis

**Primary cause: bona-fide distribution shift.** Evidence, all from the frozen
baseline:

| Test set | bona-fide mean score | spoof mean | separation | AUC |
|---|---|---|---|---|
| ASVspoof 2019 LA eval | 0.007 | 0.955 | **0.948** | 0.9987 |
| MLAAD-tiny subset | 0.529 | 0.643 | 0.114 | 0.6055 |
| WaveFake subset | **0.906** | 0.940 | 0.034 | 0.5970 |

**Secondary cause: unseen generator families.** Real but smaller. 7 of 22 MLAAD
generators score *below chance* (FireRedTTS-2.0 0.269, Kani-TTS 0.332), while
older synthesis is still caught (Maya1 0.939, facebook-MMS 0.925). Yet on
WaveFake, held-out vocoders scored the same as tuned-on vocoders
(0.5970 vs 0.5998) — so generator novelty alone cannot explain the collapse.

**Consequence for scoring semantics.** The two corpora fail in *opposite*
directions — misses on MLAAD, false alarms on WaveFake — so no single threshold
move improves both. This is why §8 of the baseline concluded no Risk Engine
threshold change is justified, and that conclusion is unaffected by this audit.

**Corollaries.**
- Calibration cannot fix this. On WaveFake, Platt achieves the best ECE in the
  entire evaluation (0.4324 → 0.0093) on a split with AUC 0.5970. A
  well-calibrated coin flip is still a coin flip.
- Threshold tuning cannot fix this (dev→eval FAR target 1% → achieved 16.93%).
- Only changing what the model has *seen* can fix it.

---

## 7. Recommended Additional Training Data

**Nothing below has been downloaded, accessed, or verified in this task.** Sizes
and licences are indicative and **must be confirmed at acquisition time**.
Flagged items require registration, approval, credentials or terms acceptance.

### 7.1 Bona-fide diversity — the highest priority

| Dataset | Provenance | Licence / access | Approx. size | Relevance | Weaknesses / leakage risk | Role |
|---|---|---|---|---|---|---|
| **Mozilla Common Voice** (en, hi, + Indian-English accents) | Mozilla, crowdsourced | **CC0**; download may require account/terms — **verify** | 10s of GB per language | Directly attacks the bona-fide-shift failure: many speakers, consumer mics, real noise | Variable quality; accent labels are self-reported | **TRAIN + VAL** |
| **LibriSpeech** | OpenSLR 12, audiobooks | **CC BY 4.0** | ~60 GB full; ~6 GB clean-100 | Clean read speech from many speakers — counterweight to LJSpeech's single voice | Read speech only; audiobook channel | **TRAIN** |
| **VoxCeleb 1 / 2** | Oxford VGG, YouTube interviews | **Research-only; registration + credentials — FLAGGED** | ~40 / ~300 GB | In-the-wild channels, thousands of speakers — closest to telephony variability | Access friction; YouTube-sourced provenance; licence forbids commercial use — **check against project intent** | **TRAIN** (if licence permits) |
| **AI4Bharat IndicSUPERB / Kathbath** | AI4Bharat, IIT Madras | typically CC BY 4.0 — **verify per release** | 10s of GB | Indian-language bona fide; addresses the stated Indian deployment context | Licence varies by component | **TRAIN + VAL** |
| **IIT-Madras IndicTTS** | IIT Madras | **Request/approval — FLAGGED** | 10s of GB | High-quality Indian-English + Hindi | Manual approval; studio-clean only | **TRAIN** |

### 7.2 Modern spoof coverage — secondary priority

| Dataset | Provenance | Licence / access | Approx. size | Relevance | Weaknesses / leakage risk | Role |
|---|---|---|---|---|---|---|
| **ASVspoof 5** (2024) | ASVspoof consortium | open, **may require registration — FLAGGED** | 100s of GB | Modern TTS/VC at scale; crowdsourced bona fide, so *both* classes share a domain | Large; verify licence | **TRAIN + VAL**, or reserve as **TEST δ** |
| **ASVspoof 2021 DF** | ASVspoof consortium | ODC-BY (verify) | ~100 GB | Codec/compression conditions — directly relevant to telephony | Bona fide still VCTK-derived → partial corpus correlation | **TRAIN** |
| **In-the-Wild** (Müller et al.) | Fraunhofer AISEC | **research-only, likely non-commercial — FLAGGED** | ~20 GB | Real-world spoofs, not lab-generated | Same licensor as MLAAD — expect the same commercial restriction | **TEST δ candidate** |
| **WaveFake (full)** | Zenodo 5642694 | CC-BY-SA-4.0 | 28.9 GB | 7 vocoders, matched LJSpeech content | Single speaker; **share-alike needs legal review** | **TRAIN** with vocoder split |
| **ADD 2022/2023** | Chinese challenge series | **registration + approval — FLAGGED** | 10s of GB | Mandarin coverage | Access friction; language mismatch to primary use case | optional |

### 7.3 Augmentation corpora (not spoof data)

| Dataset | Licence | Relevance |
|---|---|---|
| **MUSAN** (OpenSLR 17) | CC BY 4.0 | Real noise/babble/music — replaces the synthetic babble in §8 |
| **RIR & Noise Database** (OpenSLR 28) | Apache 2.0 | **Real measured room impulse responses** — directly targets the worst measured robustness failure (reverb, ΔAUC −0.5137) |

### 7.4 Explicitly excluded

- **MLAAD-tiny** — licence blocks training (§4.2). TEST only.
- **Synthetic training data generated by us** — out of scope by instruction, and
  it would add a generator whose artefacts we control, inflating results.

---

## 8. Recommended Augmentation Strategy

### 8.1 What exists today

Augmentation exists **only** in `evaluation/robustness/transforms.py`
(19 deterministic conditions) and is used **only** for measurement. There is no
augmentation in the production path and none in training (which does not exist).

### 8.2 Justified by measurement

Ranked by the measured damage each condition causes at the clean operating
threshold:

| Augmentation | Baseline evidence | Priority | Note |
|---|---|---|---|
| **Reverberation** | `reverb_300ms` AUC **0.4840** (Δ −0.5137) — total collapse, below chance | **Highest** | Use **real RIRs** (OpenSLR 28). The current synthetic exponential-decay IR is explicitly "a crude room simulation, not a measured RIR" |
| **Additive noise / SNR sweep** | `noise_white_0db` 0.5298 (Δ −0.4679); pink@10 dB 0.8442; babble@10 dB 0.9658 | **Highest** | Use **MUSAN**; the current babble is "a crude speech-babble stand-in" of band-limited noise |
| **Gain variation** | `gain_minus_20db` — **the only condition that raises FAR** (18.00%, 9× clean); `gain_plus_6db` FAR 6.00% | **High** | The one degradation that makes the system *less safe*; must be trained on |
| **Codec / telephone chain** | `telephone_chain` AUC 0.9841 but **FRR 50%** | **Medium** | AUC barely moves, usability collapses — worth augmenting for the FRR, and it matches the deployment channel |
| **Packet loss** | 2% → FRR 21.3%; 5% → FRR 48.0% | **Medium** | Justified for VoIP; keep rates realistic (≤5%) |
| **Bandwidth limit / resampling / µ-law** | ΔAUC ≤ 0.0002 — essentially free | **Low** | Cheap and harmless; include for coverage, expect no gain |

### 8.3 Rules

1. **Augment both classes identically.** Augmenting only spoof teaches
   "degraded ⇒ spoof" and would deepen the exact failure diagnosed in §6.
2. **Never augment the frozen test sets.** α, β, γ, δ stay pristine; the 19
   robustness conditions remain a separate, unchanged measurement.
3. **Prefer measured impulse responses and real noise** over the synthetic
   stand-ins. The synthetic versions are adequate for *probing* robustness and
   inadequate for *training* it — training on a synthetic IR risks learning that
   specific IR's signature.
4. **Do not chain aggressively.** Stacked degradations can produce audio outside
   any real channel, creating artefacts that are themselves learnable.
5. **Keep an un-augmented replica** of each training corpus in the mix so clean
   performance is not traded away.

---

## 9. Recommended Fine-Tuning Strategy

### 9.1 Options considered

| Approach | Assessment |
|---|---|
| **Full fine-tuning** | Feasible — 85,306 parameters is trivial. Risk is catastrophic forgetting, not compute |
| **Head-only** | Cheap, but the failure is in *representation* (the model mis-encodes unfamiliar bona fide), which a 2-logit head cannot repair. **Insufficient** |
| **Partial (freeze front-end `CONV`/sinc layer)** | Attractive: the sinc front-end encodes generic filterbank behaviour; upper GAT layers encode the corpus-specific decision. A reasonable fallback |
| **Low-LR adaptation** | Not an alternative but a *property* the chosen approach must have |
| **Staged** | Stage 1 head-only to stabilise, Stage 2 unfreeze all at lower LR. Adds a hyperparameter axis for modest benefit |
| **Balanced multi-domain training** | Not an alternative — a **requirement** layered on whichever of the above is chosen (§5.2) |

### 9.2 Primary recommendation

> **Full fine-tuning of AASIST-L on a balanced multi-domain mix with ASVspoof
> rehearsal, selecting checkpoints on worst-case-domain EER.**

Rationale: the diagnosed failure is representational, so the representation must
move (ruling out head-only). The model is small enough that full fine-tuning is
cheap. The genuine risk — forgetting — is addressed by rehearsal and by a
regression gate on TEST α, not by freezing.

Fall back to freezing the sinc front-end only if full fine-tuning proves
unstable on the verified CPU-only hardware.

### 9.3 Recommended settings — starting points to be tuned on VALIDATION only

| Parameter | Recommendation | Reasoning |
|---|---|---|
| Learning rate | **1e-5 – 1e-4**, cosine or step decay; upstream trained from scratch at 1e-4 | Adapting, not retraining; too high erases in-domain skill |
| Freezing | none initially; sinc front-end (`CONV`) as fallback | representational failure |
| **BatchNorm** | consider freezing running statistics (`eval()` on BN) early | at small batch sizes BN drift is a leading forgetting vector — flagged because the vendored model is BN-heavy |
| Batch size | **16–32** | large enough for stable BN; small enough for CPU/modest GPU |
| Epochs | **5–20** with early stopping | small model, small effective dataset — expect early convergence |
| Early stopping | patience 3–5 epochs on **worst-domain validation EER** | see below |
| Checkpoint selection | **best worst-domain EER**, ties broken by ASVspoof-dev EER | see below |
| Class balancing | weighted CE **or** balanced sampling (ASVspoof LA is ~9:1 spoof-heavy) | prevents a majority-class collapse |
| Domain balancing | equal sampling per source corpus, both classes present in each | §5.2 |
| Seeds | ≥3 seeds (e.g. 1337, 2024, 31337); report mean ± spread | a single seed cannot distinguish a real gain from variance |
| Grad clipping | norm 1.0 | standard stabiliser |
| Mixed precision | only if a GPU is used; **not** on CPU | no benefit on CPU |

### 9.4 The single most important choice

**Select on worst-case domain, never on the average.** Averaging lets a large
in-domain gain mask an out-of-domain regression — which is precisely the failure
this whole phase exists to fix. Concretely, minimise
`max(EER_asvspoof_dev, EER_val_domain_2, …, EER_val_domain_n)`.

---

## 10. Compute and Storage Requirements

**Only one hardware configuration has been verified**: macOS 26.6.2, arm64,
Python 3.10.0, torch 2.2.2, 10 threads, **CUDA unavailable**, 109 GiB free disk.
Everything about GPUs below is a recommendation, not a measurement.

### Storage

| Item | Size |
|---|---|
| Currently held datasets | ~24 GB (git-ignored) |
| Committed evaluation artifacts | 5.2 MB / 69 files |
| Proposed new corpora (§7) | **200–600 GB**, depending on how many are taken |
| Augmentation corpora (MUSAN + RIRs) | ~30 GB |
| Checkpoints (small model, many experiments) | < 5 GB |
| **Recommended free space** | **≥ 1 TB** |

Current free space (**109 GiB**) is **insufficient** for the full programme and
adequate only for a minimal pilot.

### Compute

| | Minimum workable | Recommended |
|---|---|---|
| CPU | 8-core (verified: 10 threads) | 8-core+ |
| RAM | 16 GB | 32 GB |
| VRAM | none (CPU-only is viable at 85k params) | 8–16 GB (RTX 3060/4060 class or better) |
| GPU | not required | strongly advised for augmentation-heavy epochs and multi-seed runs |

### Training-duration estimate — *derived, not measured*

Anchored on two measured numbers: **421.7 ms** per forward pass (single window,
AASIST-L, CPU) and **~5.2 files/s** batched throughput at batch 8.

- Backward ≈ 2× forward → ~**1.7–2.6 samples/s** effective on this CPU.
- A 50,000-sample epoch → **~5–8 hours per epoch on CPU**.
- 10 epochs × 3 seeds → **~1 week of wall-clock on CPU alone.**
- A mid-range GPU should reduce this by roughly an order of magnitude, but **this
  has not been measured and must not be quoted as fact.**

**Conclusion: CPU-only is feasible for a pilot and impractical for the full
multi-seed programme.** Budget for a GPU, or accept a substantially reduced
experiment count.

---

## 11. Reproducibility Plan

Every future training run must record — mirroring the discipline already proven
in `run_metadata.json`:

| Field | Detail |
|---|---|
| Dataset versions | name, release/version, download URL, acquisition date |
| Dataset hashes | SHA-256 of each source archive |
| Split manifests | **committed CSVs of exact file IDs** for train/val/each test set |
| Split rules | speaker / utterance / generator-family / corpus partition rules, plus the leakage-audit output |
| Base checkpoint | SHA-256 of the starting weights |
| Output checkpoint | SHA-256 of every saved checkpoint |
| Hyperparameters | full resolved config, not a diff |
| Seeds | `random`, `numpy`, `torch`, cuDNN determinism flags |
| Software | python, torch, torchaudio, numpy, scipy versions |
| Hardware | CPU model, thread count, GPU model, VRAM |
| Preprocessing | `prep-v1` identifier — **must match inference exactly** |
| Augmentation | per-condition parameters and probabilities |
| Duration | wall-clock and per-epoch |
| Selection | which checkpoint was chosen and on which metric |
| Results | all metrics on α, β, γ, δ + robustness + calibration |

### Naming scheme

```
aasist-v2-<NNN>-<shortdesc>-<YYYYMMDD>-seed<S>
e.g. aasist-v2-003-multidomain-rehearsal-20260915-seed1337
```

with `evaluation/results/<experiment_id>/` mirroring the existing layout, and a
top-level `experiments/REGISTRY.md` one line per run: id, hypothesis, headline
metrics, verdict. **The frozen baseline directories must never be overwritten.**

---

## 12. Evaluation Plan

Every candidate model runs **the identical, unmodified harness** used for the
frozen baseline — same scripts, same manifests, same `prep-v1`, cascade
disabled — so results are directly comparable:

1. **TEST α** — ASVspoof 2019 LA official dev→eval (`run_evaluation.py`) —
   regression gate.
2. **TEST β** — MLAAD-tiny subset (`run_mlaad.py`), frozen manifests.
3. **TEST γ** — WaveFake subset (`run_wavefake.py`), frozen manifests.
4. **TEST δ** — the reserved fourth corpus, **opened exactly once**, at the end.
5. **Robustness** — all 19 conditions (`run_robustness.py`).
6. **Streaming** — stability + latency (`run_streaming.py`), re-measuring the
   inference term since a new checkpoint changes it.
7. **Calibration** — Platt + isotonic, fitted on validation only, reported as
   Brier/ECE, and re-checking whether calibration now transfers across attacks.
8. **Statistical rigour** — bootstrap confidence intervals on AUC/EER, and ≥3
   seeds. A gain smaller than the seed spread is not a gain.

Report every metric the baseline reports: ROC-AUC, EER, FAR, FRR, TPR, TNR,
APCER/BPCER, PR-AUC, threshold sweep, plus the §7.9-style operating-point table
with thresholds selected on validation and applied unchanged to test.

---

## 13. Exact Acceptance Criteria

Baseline to beat (frozen, must be quoted unchanged):

| Protocol | ROC-AUC | EER |
|---|---|---|
| α ASVspoof official dev→eval | 0.9987 | 1.07% |
| β MLAAD-tiny subset | 0.6055 | 43.40% |
| γ WaveFake subset | 0.5970 | 41.60% |

### Clear improvement — **all** must hold

| Criterion | Requirement |
|---|---|
| Out-of-domain gain | **β ≥ 0.75 AUC AND γ ≥ 0.75 AUC** (both, not either) |
| OOD error | β and γ EER **≤ 25%** (from 43.40% / 41.60%) |
| In-domain retention | α ROC-AUC **≥ 0.99** and α EER **≤ 2.0%** |
| Operating point | a validation-selected FAR ≤ 5% threshold yields **test FRR ≤ 25%** on β and γ (baseline: 93.88% / 92.96%) |
| Held-out confirmation | **δ shows the same direction** as β and γ |
| Robustness | no condition's AUC falls **> 0.05** below its baseline value; `gain_minus_20db` FAR **≤ 18%** (not worse) |
| Statistical | improvement exceeds the ≥3-seed spread and the bootstrap 95% CI excludes the baseline |

### No meaningful improvement

- β or γ AUC gain **< 0.05**, or within seed spread / CI overlap;
- or OOD improves while the FAR-constrained operating point remains unusable
  (test FRR still > 50%) — a metric gain with no deployable consequence.

### Regression

- **Any** of β, γ, δ **below** its frozen baseline AUC; or
- robustness worse by > 0.05 AUC on any condition; or
- `gain_minus_20db` FAR rises above 18% — the security-relevant direction; or
- streaming isolated flips > 0 (baseline: 0).

### Unacceptable ASVspoof degradation — hard fail, ship nothing

- α ROC-AUC **< 0.99**, **or** α EER **> 2.0%** (≈2× baseline).

Trading away a measured 1.07% EER for an unproven out-of-domain gain is not an
acceptable trade.

### Single-dataset success is explicitly rejected

A model that improves β alone (or γ alone) **does not pass**. That pattern is
consistent with corpus-fitting (§5.2), which is the failure mode being fixed.
Success requires β **and** γ **and** corroboration on δ, with α retained.

---

## 14. Risks and Failure Modes

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Corpus-as-label shortcut** (§5.2) | **High** | Fatal — looks like success, generalises worse | Every corpus supplies both classes; δ as final arbiter |
| **Catastrophic forgetting** of ASVspoof | High | Loses real capability | ASVspoof rehearsal; hard regression gate; possible BN-stat freezing |
| **β/γ silently become validation sets** | **High** | No honest generalisation claim remains | Reserve and seal δ *before* training |
| **MLAAD licence breach** | Medium | Legal — CC BY-NC explicitly names training | MLAAD is TEST-only; obtain a licence before any other use |
| **CC-BY-SA (WaveFake) share-alike on released weights** | Medium | Legal ambiguity | Legal review before shipping any weights trained on it |
| **Overfitting to synthetic augmentation artefacts** | Medium | Robustness gains that do not transfer | Real RIRs/MUSAN, no aggressive chaining |
| **Preprocessing drift** between training and inference | Medium | Silently invalidates all comparisons | Single shared `prep-v1` code path, asserted in tests |
| **Seed-noise mistaken for improvement** | Medium | False positive | ≥3 seeds + bootstrap CIs |
| **Compute underestimate** | Medium | Schedule slip | ~5–8 h/epoch CPU estimate; budget a GPU |
| **Checkpoint-pinning breakage** | Low | Startup failure | New SHA-256 in `fetch_models.py` *and* `aasist.py`; regenerate calibrator provenance |
| **Calibrator invalidation** | **Certain** | Shipped calibrator becomes wrong | It is fitted to the *current* score distribution; a new checkpoint **must** invalidate and refit it |

---

## 15. Recommended Implementation Phases

Sequenced so each phase produces an auditable artifact and can be stopped.

| Phase | Deliverable | Gate to proceed |
|---|---|---|
| **0. Seal the baseline** | Tag current results read-only; select, hash and seal **TEST δ** | δ sealed and documented, unopened |
| **1. Legal clearance** | Written determination on MLAAD (NC), WaveFake (SA), VoxCeleb (research-only) vs. project intent | No corpus enters TRAIN without a cleared licence |
| **2. Data acquisition** | Bona-fide-diverse corpora (§7.1) + MUSAN/RIRs; manifests + hashes committed, audio git-ignored | Leakage audit clean on every axis in §5.1 |
| **3. Training infrastructure** | `training/` package: dataset, loss, optimiser, seeding, checkpointing, registry | Reproduces a **no-op fine-tune** (LR=0) that leaves α metrics **bit-identical** — proves the harness is sound before any learning |
| **4. Augmentation pipeline** | §8 conditions, both classes, real IR/noise | Augmented samples audibly and spectrally sane on inspection |
| **5. Pilot fine-tune** | 1 seed, small mix, short schedule | β **or** γ moves measurably without α collapsing |
| **6. Full training** | ≥3 seeds, balanced multi-domain, worst-domain selection | §13 "clear improvement" on α, β, γ |
| **7. Unseen confirmation** | **Open δ exactly once** | δ agrees in direction |
| **8. Recalibration** | Refit calibrator on new validation; re-test transfer across attacks | Documented whether it now transfers |
| **9. Risk Engine review** | Only if §16 evidence bar is met | Otherwise the current conclusion stands |
| **10. Integration** | New checkpoint behind `AASIST_VARIANT`; mock and heuristic paths untouched | 286 backend / 61 mobile / 0 TS errors still green |

**Phase 3's gate is the one to defend.** A no-op fine-tune that fails to
reproduce the baseline exactly means the training preprocessing has diverged
from inference, and every subsequent number would be uninterpretable.

---

## 16. What Must NOT Change

Unchanged by this audit and by any future phase unless explicitly re-authorised:

- **Risk Engine** — weights `{authenticity 0.50, identity 0.25, context 0.25}`,
  thresholds `{low 20, suspicious 40, high 65, critical 85}`,
  `min_confidence_for_allow 0.25`. Verified unchanged at runtime.
- **`USE_CALIBRATED_SCORE_FOR_FUSION = False`** — the calibrated value stays
  reported, not fused.
- **Frozen evaluation results** — `evaluation/results/*` is append-only. New
  runs go in new directories.
- **Mock mode** and the labelled heuristic fallbacks — a fallback is never
  presented as real ML.
- **Three-stream separation** — authenticity / identity / context fused only in
  the Risk Engine; missing evidence yields `INSUFFICIENT_EVIDENCE`.
- **Dashboard / UI**, **Android audio capture**, **production architecture**.
- **No Resemble AI, no LiveKit, no commercial external detector.**
- **The published baseline numbers** — not to be re-derived, re-interpreted or
  improved.

### Risk Engine policy (§11 of the brief)

**The current conclusion stands unchanged: "No threshold change is justified by
the current evaluation."**

Thresholds could legitimately be reconsidered only when **all** of the following
exist — and none do today:

1. A model meeting §13 "clear improvement" on α, β, γ **and** δ.
2. A **runtime domain indicator** letting the system tell at inference time
   which regime it is in. Today it cannot, which is why a single threshold
   cannot be safe in both.
3. A calibration set drawn from the **actual deployment distribution** (Indian
   telephony), not from research corpora.
4. Re-measured robustness confirming `gain_minus_20db` no longer raises FAR.
5. Evidence that the fusion invariant still holds — authenticity alone must
   remain unable to reach CRITICAL/HOLD.

Even then, changes should be argued per threshold with OLD / NEW / dataset /
validation split / measured tradeoff / security justification, exactly as
recorded in `ml_evaluation.md` §8.2.

---

## 17. Final Recommendation

**Proceed to a training phase, but fix the framing first.**

The instinct this result invites — "train on more modern fakes" — addresses the
*secondary* cause. The measured evidence says the primary cause is that AASIST
does not recognise unfamiliar **bona fide** speech. The plan must be led by
bona-fide diversity (many speakers, many channels, many corpora, Indian English
and Hindi), with modern spoof coverage second, and with the absolute rule that
**every corpus contributes both classes**.

Three things must happen before any training step:

1. **Seal TEST δ.** β and γ have already informed the diagnosis; without a
   fourth untouched corpus there will be no honest generalisation claim left to
   make.
2. **Clear the licences.** MLAAD-tiny is CC BY-NC and its notice names training
   explicitly. It stays a test set.
3. **Build and prove the training harness** with a no-op fine-tune that
   reproduces the frozen baseline exactly.

Highest-value single intervention: **balanced multi-domain fine-tuning of
AASIST-L with ASVspoof rehearsal and worst-domain checkpoint selection.** The
model is small, the compute is affordable, and the failure is representational —
so the representation must move.

Expected outcome, stated honestly: this should substantially narrow the
in-domain/out-of-domain gap. It is **unlikely** to reach in-domain-quality
detection on unseen generators, and the plan must not promise that. If the
result is a genuine but partial improvement, the correct response is to report
it as such — and the Risk Engine conclusion may well remain unchanged even then.

Until a model passes §13, the honest statement is the one already published:

> Dhwani AI's authenticity detector is strong in-domain and near chance
> out of domain. It has not been measured on telephony, Indian-English, or live
> call audio. A model output is evidence to be fused, not a verdict to trust.
