# Dhwani AI — ML Evaluation

Status legend used throughout:

- **PIPELINE IMPLEMENTED** — the harness exists, is tested, and runs.
- **BENCHMARK COMPLETED** — a measurement was actually taken on real data.

These are not the same thing and this document never conflates them.

---

## 1. Pipeline audit (Phase 1) — recorded *before* any change

The state of the authenticity path at the start of this evaluation phase.

| Property | Value |
|---|---|
| Model in production default | AASIST-L, with cascade to AASIST enabled |
| Model used for evaluation | AASIST-L, **cascade disabled** (see below) |
| Checkpoint source | `github.com/clovaai/aasist` — MIT, © NAVER Corp |
| AASIST SHA-256 | `51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0` |
| AASIST-L SHA-256 | `814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a` |
| Parameters | AASIST 297,866 · AASIST-L 85,306 |
| Sample rate | 16 000 Hz mono |
| Model input length | 64 600 samples (4.0375 s) |
| Length policy | tile if short, centre-crop if long (upstream convention) |
| Normalisation | none beyond float32 in [-1, 1] |
| Speech gate | windows below mean power `1e-5` are refused → *no evidence* |
| Minimum analysis | `MIN_ANALYSIS_MS = 400` |
| Rolling window / hop | `ANALYSIS_WINDOW_MS = 4038` / `ANALYSIS_HOP_MS = 1000` |
| Device | CPU (`ML_DEVICE=auto`; no CUDA on the evaluation host) |
| Score interpretation | `synthetic_probability = 1 − softmax(logits)[1]`; column 1 is the bona-fide class per upstream |
| Spoof threshold before this phase | **none existed** — the raw score fed the Risk Engine as a weighted contribution; there was no binary spoof decision |
| Fallback | missing checkpoint / torch / inference error → heuristic DSP, labelled `heuristic_fallback`, `is_mock=true` |
| Confidence | `clip(0.25 + 0.5 · decisiveness · sufficiency, 0, 0.80)` — a decisiveness proxy, never calibrated, capped below 1.0 |

**Cascade is disabled for evaluation.** The production cascade escalates from
AASIST-L to AASIST when the light tier lands near 0.5. That makes the effective
scoring function depend on the score itself, which is fine as a policy but
invalid as a benchmark: a reported EER must characterise one model. Cascade
behaviour is measured separately.

### Guarantee that evaluation uses the real model

`evaluation/runners/score.py` calls `build_detector()`, which raises
`NotRealModel` if any required checkpoint is missing, and scores by invoking the
loaded `torch` module directly. There is no code path in the runner that can
reach the heuristic backend, the demo detector, generated PCM, or a constant.
Every run records the SHA-256 of the checkpoints actually loaded.

---

## 2. Datasets

### Acquisition summary

| Dataset | Source | Licence | Size | Access | Outcome |
|---|---|---|---|---|---|
| ASVspoof 2019 LA | Edinburgh DataShare, DOI 10.7488/ds/2555 | Open Data Commons Attribution | 7.64 GB | Public, no auth | **Obtained in full** — 122,328 files, `sha256 208a7e4e…e4ec` |
| MLAAD-tiny v9 | HF `mueller91/MLAAD-tiny` | Non-commercial (see dataset NOTICE) | 3.54 GB | Public but **anonymous rate-limited** (HTTP 429 on snapshot) | **Obtained as a balanced subset** — 392 bona fide + 5,555 spoof via targeted per-file download |
| WaveFake | Zenodo 5642694 | CC-BY-SA-4.0 | 28.9 GB (+ LJSpeech 2.6 GB for bona fide) | Public, no auth | **Obtained** — documented subset via HTTP range reads (see below) |
| MLAAD full v9 | Fraunhofer owncloud | — | ~50 GB+ | **Blocked**: webdav 401, direct download unavailable | Not obtained; superseded by the authors' own MLAAD-tiny |

Datasets live in `data/external/` and are git-ignored. Only manifests, configs,
hashes and results are committed.

**How the WaveFake subset was obtained, and why it is a fair sample.**
WaveFake ships as a single 28.9 GB ZIP. Rather than download all of it, the
ZIP64 central directory was fetched by HTTP range request (20.7 MB), giving an
exact index of all 134,278 entries; a contiguous storage-order block per vocoder
was then pulled directly. This matters for validity: **within the archive,
storage order is randomised with respect to LJSpeech utterance id** (verified —
the first entries of `ljspeech_melgan` are LJ013-0060, LJ046-0060, LJ022-0034,
LJ018-0179…), so a contiguous block is a random sample of utterances, not an
alphabetical prefix. The subset is therefore documented and reproducible rather
than cherry-picked. The JSUT (Japanese) and Common-Voice FastSpeech2 portions
were excluded because their bona-fide counterparts are different corpora.

### Split discipline

| Role | Split | Used for |
|---|---|---|
| Calibration / threshold tuning | ASVspoof 2019 LA **dev** | fitting calibration, choosing thresholds |
| Final test | ASVspoof 2019 LA **eval** | reporting only |
| Out-of-domain test | MLAAD-tiny (generator-disjoint) | reporting only |
| Out-of-domain test | WaveFake + LJSpeech (vocoder- and utterance-disjoint) | reporting only |

The final test split is never used to fit calibration, select thresholds, or
choose policy boundaries. `evaluation/datasets/base.audit_split_disjointness`
is run on every pair and its output is stored with the results.

**Honest caveat about "unseen".** AASIST's released weights were trained by
their authors on ASVspoof 2019 LA *train*, and dev shares that corpus's
recording conditions and attack set (A01–A06). Our calibration split is
therefore not unseen by the model's developers. `eval` contains attacks A07–A19
that are unseen in training, which is what makes it a genuine generalisation
test within the corpus — but it remains the same recording pipeline. Neither
split says anything about telephony.

---

## 3. Metric definitions

Fixed labels: **BONAFIDE = 0, SPOOF = 1**. Scores are synthetic probability;
higher means more spoof-like. A sample is called SPOOF when `score ≥ threshold`.

| Metric | Definition |
|---|---|
| **FAR** | spoof wrongly accepted as bona fide = FN / n_spoof. **The security-critical error.** |
| **FRR** | bona fide wrongly rejected as spoof = FP / n_bonafide. The usability error. |
| **EER** | operating point where FAR and FRR meet |
| **ROC-AUC** | threshold-independent ranking quality |
| **APCER / BPCER** | the PAD vocabulary for FAR / FRR respectively |

Accuracy is reported but never alone: on an imbalanced spoof-heavy corpus it is
close to meaningless.

---

## 4. Robustness methodology

Nineteen deterministic conditions in `evaluation/robustness/transforms.py`:
clean; white/pink/babble noise at 20/10/5/0 dB SNR; 8 kHz resample round trip;
low-pass at 4 kHz and 3.4 kHz; 300–3400 Hz telephone band; µ-law companding;
a combined telephone chain; −20 dB and +6 dB gain; hard clipping; 300 ms
synthetic reverberation; 2 % and 5 % packet loss.

**These are synthetic approximations, not field validation.** A band-limit plus
companding is not a real GSM/AMR codec over a real network, and a synthetic
impulse response is not a measured room. Results indicate sensitivity to a known
perturbation and nothing more. No "telephony robustness" claim is made on this
basis.

---

## 5. Calibration methodology

A raw AASIST softmax value is a decision score, not a probability. Calibration
fits a monotonic map on the **calibration split only** and is evaluated on the
held-out test split.

- **Platt / logistic** — two parameters, stable, sigmoid-shaped correction only.
- **Isotonic** — free-form monotonic, more flexible, more prone to overfitting.

Quality is measured by **Brier score** and **Expected Calibration Error**, with
a reliability curve stored as data. Both methods are monotonic, so ROC-AUC and
EER are unchanged by calibration — only the probability scale moves.

The raw score is always retained. Calibration adds `calibrated_spoof_probability`,
`calibration_method` and `calibration_version`; it never overwrites the model
output.

---

## 6. Reproducibility

Every run writes `evaluation/results/<run>/run_metadata.json` containing the
model variant and checkpoint hashes, preprocessing version, software and
hardware, seeds, dataset manifest paths, subset parameters, and timestamps.
Manifests are committed; audio is not.

---

## 7. Results

All numbers below are produced by the scripts in `evaluation/` against the real
AASIST-L checkpoint (`sha256 814331d0…ce27a`), CPU, `prep-v1` preprocessing,
cascade disabled. Raw scores, manifests, leakage audits and run metadata for
every table are committed under `evaluation/results/<tag>/`. No number in this
section is estimated, extrapolated or copied from a paper.

### 7.1 Headline

| Protocol | Dataset scope | Test condition | n (test) | ROC-AUC | EER |
|---|---|---|---|---|---|
| ASVspoof 2019 LA, official dev→eval (`asvspoof_official`) | **full LA corpus obtained**; stratified 1500/class test subset | attacks A07–A19, unseen | 3000 | 0.9987 | 1.07% |
| ASVspoof 2019 LA, speaker-disjoint (`asvspoof_indomain`) | **full LA corpus obtained**; 1000/class test subset | attacks A07–A19 | 2000 | 0.9990 | 1.20% |
| **MLAAD-tiny subset**, generator-disjoint (`mlaad_ood`) | subset of *MLAAD-tiny*, itself a compact variant — **not full MLAAD v9** | 22 unseen modern TTS | 355 | **0.6055** | **43.40%** |
| **WaveFake subset** + LJSpeech (`wavefake_ood`) | ~150 files per vocoder from the 28.9 GB archive — **not full WaveFake** | 4 unseen vocoders, single speaker | 1250 | **0.5970** | **41.60%** |

**Scope discipline.** Rows 3 and 4 are subsets of subsets and are labelled that
way everywhere in this document. `MLAAD-tiny` is the authors' own compact
release; full MLAAD v9 was **not** obtained (§2) and nothing here should be read
as a full-MLAAD result. The WaveFake row is a single-speaker English read-speech
corpus (LJSpeech) — it is **not** a measurement of real-world performance, and
its value is diagnostic (§7.5), not representative.

The corpus the model was trained on is essentially solved. Two independent
out-of-domain corpora — one testing unseen TTS systems, one testing unseen
vocoders on matched content — both land near a coin flip. **All of these are
true of the same checkpoint at the same time**, and the out-of-domain rows are
the ones that describe deployment.

§7.5 identifies the mechanism, and it is not the obvious one: the dominant
cause is **domain shift in the bona-fide distribution**, not generator novelty.

### 7.2 ASVspoof 2019 LA — official protocol (the threshold-transfer result)

Calibration split = dev (A01–A06, 20 speakers), test split = eval (A07–A19,
67 speakers). Leakage audit: file overlap 0, speaker overlap 0, **attack-system
overlap 0** — dev and eval share no attack.

Subsets: 1000/class on dev, 1500/class on eval, stratified over `system_id`.

| Split | n | ROC-AUC | EER |
|---|---|---|---|
| dev (calibration) | 2000 | 0.9992 | 0.70% @ thr 0.9545 |
| eval (test) | 3000 | 0.9987 | 1.07% *(reference only — not used to pick anything)* |

Thresholds chosen **on dev**, then applied unchanged to eval:

| Threshold chosen on dev | value | dev FRR | **test FAR** | test FRR |
|---|---|---|---|---|
| dev EER point | 0.9545 | 0.70% | **13.33%** | 0.20% |
| dev FAR ≤ 1% | 0.9750 | 0.70% | **16.93%** | 0.13% |
| dev FAR ≤ 5% | 0.9990 | 0.20% | **37.73%** | 0.00% |

**This is the single most important measurement in this document.** A threshold
selected to admit at most 1% of spoofs admits **16.93%** of them one split
later — a 17× miss of its own security target — while ROC-AUC barely moves
(0.9992 → 0.9987). Ranking quality transferred; the *score scale* did not.
Any claim of the form "we operate at 1% false-accept" is therefore unsupportable
across attack families, and AUC is not evidence for it.

Per-attack false-accept rate at the dev FAR ≤ 1% threshold:

| Attack | FAR | own AUC | | Attack | FAR | own AUC |
|---|---|---|---|---|---|---|
| A10 | **61.74%** | 0.9966 | | A13 | 14.66% | 0.9992 |
| A07 | **40.87%** | 0.9982 | | A08 | 0.87% | 1.0000 |
| A12 | **32.17%** | 0.9985 | | A09 | 0.00% | 1.0000 |
| A18 | 26.09% | 0.9936 | | A14 | 0.00% | 1.0000 |
| A15 | 19.13% | 0.9992 | | | | |

A10 has an AUC of 0.9966 and still lets 6 of every 10 spoofs through at this
operating point. Per-attack AUC is not a safety property.

### 7.3 ASVspoof 2019 LA — speaker-disjoint within eval

33 calibration speakers / 34 test speakers, disjoint; both sides see A07–A19.
Leakage audit: files 0, speakers 0, duplicates 0.

| | n | ROC-AUC | EER | FAR @ calib EER thr | FRR |
|---|---|---|---|---|---|
| test | 2000 | 0.9990 | 1.20% | 0.60% | 1.70% |

Security operating points (chosen on the calibration speakers, applied to test):

| Threshold chosen on calibration | value | test FAR | test FRR |
|---|---|---|---|
| calibration EER point | 0.0879 | 0.60% | 1.70% |
| FAR ≤ 1% | 0.0570 | **0.50%** | 1.80% |
| FAR ≤ 5% | 0.5090 | 3.50% | 0.50% |

Holding the attack set fixed and varying only the speaker, the threshold
transfers well — the FAR ≤ 1% point built on calibration speakers delivers
0.50% FAR on unseen speakers, i.e. it actually meets its target. Contrast with §7.2,
where the speaker set varied *and* the attacks changed and FAR blew out to
13–17%. **The transfer failure is caused by attack shift, not speaker shift** —
that is why this pair of runs was worth doing separately.

### 7.4 MLAAD-tiny **subset** — out-of-domain, modern TTS

21 calibration generators / 22 test generators, split at `language/system`
granularity; no file, speaker or `language/system` overlap.

*Caveat, stated because it matters:* four generator **families** (Edge-TTS,
FishTTS, Higgs-Audio-V2, Kani-TTS-370M) appear on both sides under different
languages. Because both calibrators are monotonic, this cannot inflate AUC or
EER — it can only affect the chosen threshold. Excluding all four, **4 of the
remaining 18 generators still score below chance**, so the finding is not an
artifact of the overlap.

| | n | ROC-AUC | EER | FAR | FRR |
|---|---|---|---|---|---|
| test (unseen generators) | 355 (196 bona fide / 159 spoof) | **0.6055** | **43.40%** | 41.51% | 46.94% |

FAR/FRR are at the calibration-split EER threshold (0.6450). The calibration
split itself measures EER 40.65% — the detector is barely separating classes on
*either* side of this split.

Per-generator ROC-AUC on the test side — **7 of 22 are worse than chance**:

| Generator | AUC | | Generator | AUC |
|---|---|---|---|---|
| FireRedTTS-2.0 | **0.269** | | Chatterbox | 0.536 |
| Kani-TTS-370M | **0.332** | | Index-TTS-2.0 | 0.701 |
| Higgs-Audio-V2 | **0.333** | | Edge-TTS | 0.723 |
| Nari Dia2 | **0.388** | | MegaTTS3 | 0.846 |
| MiniCPM-o-2.6 | **0.405** | | RVC | 0.912 |
| FishTTS | **0.420** | | facebook_mms-tts-deu | 0.925 |
| OuteTTS | **0.437** | | Maya1 TTS | 0.939 |

An AUC below 0.5 means the detector systematically scores that generator's
output as *more* bona fide than real speech. For those seven systems the
detector is worse than useless — it is actively misleading, and thresholding it
harder makes it worse, not better.

> **Naming note.** `Resemble.ai (April 12th, 2025)` in the table above is the
> name of a *generator in the MLAAD dataset* — audio that system produced, used
> here as spoof test material. Dhwani AI does not call, integrate or depend on
> Resemble AI or any other commercial detector; the constraint is unchanged.

Older/simpler synthesis (griffin-lim-adjacent, `facebook-MMS`, `RVC`, `Maya1`)
is still caught. The failures cluster on 2024–2025 neural codec / LLM-style TTS,
which did not exist when the ASVspoof 2019 training data was built.

**There is no usable operating point out of domain.** Bounding the security
error costs essentially all of the legitimate traffic:

| Threshold chosen on calibration generators | value | test FAR | test FRR |
|---|---|---|---|
| calibration EER point | 0.6450 | 41.51% | 46.94% |
| FAR ≤ 1% | **0.0000** (degenerate) | 0.00% | **100.00%** |
| FAR ≤ 5% | 0.0040 | 6.92% | **93.88%** |

For the 1% target there is genuinely *no* threshold above 0.0 that qualifies —
the search falls back to its documented floor, which flags every sample as
spoof. For the 5% target a real threshold exists (0.0040), and it rejects
**93.88% of genuine callers** while still admitting 6.92% of spoofs, overshooting
its own 5% target.

That is worth stating precisely because it is not a tuning problem. No choice of
threshold, and no recalibration, can manufacture separation that the scores do
not contain.

### 7.5 WaveFake **subset** — unseen vocoders, and the real cause of the collapse

WaveFake resynthesises LJSpeech utterances with neural vocoders, so the
bona-fide half is the *original recording of the same sentence*. Speaker,
words and recording chain are held constant; only the vocoder artifact differs.
Two disjointness axes are enforced at once — calibration vocoders
{hifiGAN, melgan, parallel_wavegan} never appear in test
{full_band_melgan, melgan_large, multi_band_melgan, waveglow}, and every
LJSpeech utterance id is assigned to exactly one side by SHA-256 parity
(measured overlap: **0** files, **0** utterances).

| Split | n | ROC-AUC | EER |
|---|---|---|---|
| calibration (vocoders the threshold *did* see) | 864 | 0.5998 | 41.67% |
| test (unseen vocoders) | 1250 | 0.5970 | 41.60% |

Per unseen vocoder:

| Vocoder | ROC-AUC | EER |
|---|---|---|
| full_band_melgan | **0.5043** | 48.73% |
| multi_band_melgan | **0.5296** | 47.47% |
| waveglow | 0.6445 | 38.41% |
| melgan_large | 0.7117 | 34.18% |

**The decisive observation is that the calibration and test splits score the
same (0.5998 vs 0.5970).** Vocoder novelty explains almost none of the failure —
the detector does no better on the three vocoders whose scores it was tuned on.
Something else is wrong, and the score distributions say what:

| Test set | bona fide mean | spoof mean | separation |
|---|---|---|---|
| ASVspoof 2019 LA eval | 0.007 | 0.955 | **0.948** |
| MLAAD-tiny, unseen TTS | 0.529 | 0.643 | 0.114 |
| WaveFake, unseen vocoders | **0.906** | 0.940 | **0.034** |

On WaveFake the detector assigns a mean spoof probability of **0.906 to
genuine, unmodified human speech** — clean single-speaker studio recordings
from LJSpeech. It is not missing the fakes here; it is condemning the real
audio. And these are exactly the same generic errors on both classes, which is
why AUC lands near 0.5 while the *scores* look confidently spoof-like.

This reframes the MLAAD result in §7.4. The failure is not primarily "modern
TTS is too good to detect". It is **domain shift in the bona-fide distribution**:
AASIST learned what bona fide sounds like *in ASVspoof 2019*, and any other
clean corpus reads as synthetic. A detector that flags 90% of real speech is
not conservative, it is uninformative, and no threshold repairs it — the
FAR ≤ 1% point on the calibration split already costs FRR 98.61%.

Interestingly this is the one out-of-domain setting where calibration helps a
lot on paper (Platt ECE 0.4324 → 0.0093). That improvement is real and
worthless: a calibrator can correct a systematically over-confident *scale*, but
it cannot create ranking information that the scores do not contain, and AUC is
unchanged at 0.597 by construction (both calibrators are monotone). It is a
clean demonstration that **good calibration is not evidence of good detection.**

*Subset note:* documented subset of 1,057 spoof files (≈150 per vocoder) and
1,057 bona-fide LJSpeech files. The LJSpeech pool available locally was 11,573
of 13,100 utterances (the archive download was truncated); bona-fide samples are
drawn at random from that pool, which spans LJ001–LJ050, i.e. the whole corpus.

### 7.6 Robustness (19 conditions)

Clean-EER threshold 0.0879 applied unchanged to every condition, 300 samples
each, ASVspoof eval material. Clean baseline: AUC 0.9977, FAR 2.00%, FRR 1.33%.

| Condition | AUC | ΔAUC | FAR | FRR |
|---|---|---|---|---|
| resample_8k | 0.9978 | +0.0000 | 0.67% | 1.33% |
| lowpass_3k4 | 0.9977 | +0.0000 | 0.67% | 1.33% |
| **clean** | 0.9977 | — | 2.00% | 1.33% |
| mu_law | 0.9977 | −0.0000 | 1.33% | 1.33% |
| lowpass_4k | 0.9975 | −0.0002 | 0.67% | 1.33% |
| gain_plus_6db | 0.9954 | −0.0023 | **6.00%** | 2.67% |
| clipping | 0.9953 | −0.0024 | 0.67% | 7.33% |
| noise_white_20db | 0.9870 | −0.0108 | 0.00% | 20.67% |
| telephone_band | 0.9845 | −0.0132 | 0.00% | 52.00% |
| telephone_chain | 0.9841 | −0.0136 | 0.00% | 50.00% |
| packet_loss_2pct | 0.9807 | −0.0170 | 0.67% | 21.33% |
| noise_babble_10db | 0.9658 | −0.0320 | 0.00% | 94.00% |
| packet_loss_5pct | 0.9607 | −0.0370 | 0.00% | 48.00% |
| noise_white_10db | 0.9336 | −0.0641 | 0.00% | 98.00% |
| **gain_minus_20db** | 0.8742 | −0.1235 | **18.00%** | 23.33% |
| noise_pink_10db | 0.8442 | −0.1535 | 0.00% | 98.00% |
| noise_white_5db | 0.8350 | −0.1628 | 0.00% | 100.00% |
| noise_white_0db | 0.5298 | −0.4679 | 0.00% | 100.00% |
| reverb_300ms | 0.4840 | **−0.5137** | 0.00% | 100.00% |

Three findings:

1. **Band-limiting is harmless; room acoustics are fatal.** Everything that
   merely narrows the band — 8 kHz resampling, 3.4 kHz low-pass, µ-law — costs
   ≤ 0.0002 AUC. `reverb_300ms` destroys the detector outright (AUC 0.484,
   *below chance*), and `noise_white_0db` nearly so. A speakerphone in a hard
   room is a bigger threat to this detector than the telephone codec is.
2. **Degradation almost always inflates FRR, not FAR.** Under 14 of 19
   conditions FAR stays at or below clean while FRR climbs, in six cases past
   90%. Degraded audio drives everything toward "spoof", so the failure mode is
   mostly *annoying* rather than *unsafe* — with one exception:
3. **Quiet audio is the dangerous condition.** `gain_minus_20db` is the only
   condition that materially raises false accepts (**18.00%**, 9× clean), and
   mean spoof score collapses 0.933 → 0.553. `gain_plus_6db` also raises FAR
   (6.00%). A quiet or badly-gained caller is the one degradation that makes the
   system *less* safe, and it is trivial for an attacker to induce.

These are synthetic approximations applied offline (see §4), not field
measurements on live telephony.

### 7.7 Streaming stability

Production `StreamWindower`, window 4038 ms / hop 1000 ms, threshold 0.0879,
6 streams × 8 scored windows.

| | max σ | max jitter | isolated flips |
|---|---|---|---|
| bona fide streams | 0.1393 | 0.0892 | **0** |
| spoof streams | 0.0005 | 0.0004 | **0** |

Aggregator comparison (mean across all streams):

| Aggregator | mean σ | mean jitter | isolated flips |
|---|---|---|---|
| raw | 0.0234 | 0.0150 | 0 |
| ema_0.4 | 0.0217 | 0.0097 | 0 |
| median_3 | 0.0243 | 0.0117 | 0 |
| median_5 | 0.0244 | 0.0122 | 0 |
| confirm_2 / confirm_3 / hysteresis | 0.0234 | — | 0 |

#### Transitions and what "0.0 s" actually means

bona fide→spoof is detected in the **first scored window at or after the
switch** (`delay_raw_s = 0.0`, 0 isolated flips); spoof→bona fide settles
immediately too.

**This is not an end-to-end latency of 0 ms, and must not be quoted as one.**
`detection_delay` is defined as `(i − transition_window) × hop_ms / 1000` — it
counts *additional hops beyond the first window that already contains the
switch*. It deliberately excludes window accumulation, hop quantisation,
inference and transport. The honest decomposition, measured on this machine
(CPU, `torch 2.2.2`, 10 threads):

| Stage | Latency | Source |
|---|---|---|
| Audio window accumulation | **4038 ms** | `ANALYSIS_WINDOW_MS`; a full window must exist before *any* score |
| Hop interval (steady state) | **1000 ms** | `ANALYSIS_HOP_MS`; new score each hop, so onset→window-boundary costs 0–1000 ms |
| Model inference, AASIST-L, 1 window | **421.7 ms** mean, 398.5 median, **513.5 p95** | measured, n=20, cascade off |
| Model inference, production path | **433.6 ms** mean, 417.7 median, **514.3 p95** | measured, n=15, `AASIST_CASCADE=True` |
| Risk fusion + policy decision | **0.0079 ms** (7.9 µs mean, 8.3 µs p95) | measured, n=3000 |
| Aggregation/smoothing | **0 ms** | none applied — raw per-window scoring retained |
| Network transport | **not measured** | out of scope for this study |

These inference figures are consistent with the independent benchmark in
`docs/models.md` §7 (AASIST-L p50 455.7 ms, cascade p50 401.9 ms, 30 runs), which
remains the canonical latency reference.

Combining these:

* **Cold start** — from the first audio sample of a session to the first
  authenticity evidence: **4038 ms + ~422 ms ≈ 4.5 s**. Before that the pipeline
  emits nothing and the Risk Engine sits at `INSUFFICIENT_EVIDENCE`.
* **Steady state** — from a spoof onset mid-call to a decision:
  **0–1000 ms hop quantisation + ~422 ms inference + ~0.008 ms policy
  ≈ 0.4–1.4 s**, plus network transport, which was not measured.
* The measured `0.0 s` means **no additional hops were needed** beyond that
  first window — the detector did not need corroborating windows to make up its
  mind. That is a real and useful property (it is what "0 isolated flips, no
  smoothing needed" rests on), but it is a statement about *window count*, not
  about milliseconds.

Note also that the transition windows are *mixed* — the first window after a
switch still contains up to 4038 ms of pre-switch audio — so a 0-hop detection
means the model flipped on partially-spoofed audio, which is favourable but was
measured on clean concatenated segments, not on live calls.

Edge cases behave as designed: **silence yields 0 scored windows** and
**2 s of speech yields 0 scored windows** (both shorter than the 4038 ms
window), so the pipeline emits no evidence rather than a guess — which is what
`INSUFFICIENT_EVIDENCE` exists for. `speech_then_silence` scored 6 of 8 windows
and skipped 2 for lack of evidence.

**Decision: no aggregation change.** Every smoothing strategy was measured and
none removed a flip, because there were no flips to remove. EMA halves jitter
(0.0150 → 0.0097) but that buys nothing operationally and would add at least one
hop (1000 ms) to the steady-state delay above. Raw per-window scoring is
retained. *This conclusion is scoped to clean ~8-window segments of concatenated
ASVspoof audio; it is not evidence about noisy live telephony.*

### 7.8 Calibration

| Run | Method | Brier before → after | ECE before → after | Verdict |
|---|---|---|---|---|
| speaker-disjoint (same attacks) | Platt | 0.0145 → 0.0132 | 0.0202 → 0.0350 | mixed |
| speaker-disjoint (same attacks) | **Isotonic** | 0.0145 → **0.0093** | 0.0202 → **0.0075** | **helps** |
| official dev→eval (attack shift) | Platt | 0.0145 → 0.0157 | 0.0186 → 0.0273 | **hurts** |
| official dev→eval (attack shift) | **Isotonic** | 0.0145 → **0.0354** | 0.0186 → **0.0562** | **hurts badly** |
| MLAAD OOD (fitted on MLAAD calib generators) | Isotonic | 0.3681 → 0.2363 | 0.3450 → 0.0512 | helps *within MLAAD* |
| WaveFake OOD (fitted on calib vocoders) | Platt | 0.4401 → 0.2476 | 0.4324 → **0.0093** | helps, and means nothing (§7.5) |
| WaveFake OOD (fitted on calib vocoders) | Isotonic | 0.4401 → 0.2452 | 0.4324 → 0.0298 | same |

Read together these rows say one thing: **calibration transfers across speakers
and does not transfer across attack families.** Isotonic regression is the best
method when the attack distribution holds fixed (ECE 0.0202 → 0.0075, a 2.7×
improvement) and the *worst* when it shifts (ECE 0.0186 → 0.0562, 3× worse than
doing nothing). The MLAAD row is not a counterexample: that calibrator was
fitted on MLAAD generators and applied to MLAAD generators.

This mirrors §7.2 exactly — a monotone rescaling fitted on known attacks is
just as scale-fragile as a threshold fitted on known attacks, and for the same
reason.

The WaveFake rows are the sharpest warning in the table. Platt calibration takes
ECE from 0.4324 to **0.0093** there — by far the best calibration number in this
document — on a split where ROC-AUC is **0.5970**. Because every calibrator here
is monotone, AUC is mathematically unchanged by calibration. **A well-calibrated
coin flip is still a coin flip**, and any dashboard that showed only the
calibrated probability would look most trustworthy exactly where the detector is
least useful. That is the concrete reason the calibrated value is reported as
labelled evidence and never fused.

**Shipping decision.** The isotonic calibrator fitted on the speaker-disjoint
ASVspoof split ships as
`services/api/models/calibration/authenticity_isotonic_asvspoof2019la.json`,
and `USE_CALIBRATED_SCORE_FOR_FUSION` stays **`False`**. The calibrated value is
computed, returned and labelled with its `calibration_version` and provenance,
but **the Risk Engine continues to fuse the raw score**. Given the dev→eval
result, promoting the calibrated probability into fusion would mean shipping a
number that is better-looking in-domain and measurably worse than uncalibrated
under exactly the shift we expect in the field. It is kept as reported evidence,
not as a decision input, until there is a calibration set drawn from the real
deployment distribution.

### 7.9 Consolidated operating points — FAR / FRR / TPR / TNR

Every protocol actually evaluated, with the full confusion picture. **Every
threshold in the "thresh" column was selected on that protocol's validation
split and then applied unchanged to its test split.** The test-split EER
threshold is shown for reference only and was never used to select anything.

Convention (as defined in §3): the positive class is **spoof**.
`FAR` = spoof wrongly accepted as bona fide (the security error).
`FRR` = bona fide wrongly rejected. `TPR` = spoof correctly caught.
`TNR` = bona fide correctly passed.

**A. ASVspoof 2019 LA — official dev→eval** (dev A01–A06 → eval A07–A19)
validation n=2000, AUC 0.9992 · test n=3000, AUC 0.9987
validation EER 0.0070 @ 0.9545 · test own EER 0.0107 @ 0.1367 *(reference only)*

| Operating point (chosen on dev) | thresh | FAR | FRR | TPR | TNR |
|---|---|---|---|---|---|
| validation EER point | 0.9545 | 0.1333 | 0.0020 | 0.8667 | 0.9980 |
| **security: FAR ≤ 1%** | 0.9750 | **0.1693** | 0.0013 | 0.8307 | 0.9987 |
| security: FAR ≤ 5% | 0.9990 | 0.3773 | 0.0000 | 0.6227 | 1.0000 |

**B. ASVspoof 2019 LA — speaker-disjoint within eval** (33 → 34 speakers)
validation n=2000, AUC 0.9988 · test n=2000, AUC 0.9990
validation EER 0.0140 @ 0.0879 · test own EER 0.0120 @ 0.2146 *(reference only)*

| Operating point (chosen on calibration speakers) | thresh | FAR | FRR | TPR | TNR |
|---|---|---|---|---|---|
| validation EER point | 0.0879 | 0.0060 | 0.0170 | 0.9940 | 0.9830 |
| **security: FAR ≤ 1%** | 0.0570 | **0.0050** | 0.0180 | 0.9950 | 0.9820 |
| security: FAR ≤ 5% | 0.5090 | 0.0350 | 0.0050 | 0.9650 | 0.9950 |

**C. MLAAD-tiny subset — generator-disjoint** (21 → 22 unseen generators)
validation n=351, AUC 0.6227 · test n=355, AUC 0.6055
validation EER 0.4065 @ 0.6450 · test own EER 0.4340 @ 0.7091 *(reference only)*

| Operating point (chosen on calibration generators) | thresh | FAR | FRR | TPR | TNR |
|---|---|---|---|---|---|
| validation EER point | 0.6450 | 0.4151 | 0.4694 | 0.5849 | 0.5306 |
| security: FAR ≤ 1% | 0.0000 † | 0.0000 | **1.0000** | 1.0000 | 0.0000 |
| security: FAR ≤ 5% | 0.0040 | 0.0692 | **0.9388** | 0.9308 | 0.0612 |

**D. WaveFake subset + LJSpeech — vocoder- and utterance-disjoint** (3 → 4 unseen vocoders)
validation n=864, AUC 0.5998 · test n=1250, AUC 0.5970
validation EER 0.4167 @ 0.9892 · test own EER 0.4160 @ 0.9888 *(reference only)*

| Operating point (chosen on calibration vocoders) | thresh | FAR | FRR | TPR | TNR |
|---|---|---|---|---|---|
| validation EER point | 0.9892 | 0.4288 | 0.4000 | 0.5712 | 0.6000 |
| security: FAR ≤ 1% | 0.1150 | 0.0000 | **0.9808** | 1.0000 | 0.0192 |
| security: FAR ≤ 5% | 0.5810 | 0.0432 | **0.9296** | 0.9568 | 0.0704 |

† **Degenerate point.** No threshold above 0.0 satisfies FAR ≤ 1% on the MLAAD
validation split, so the search returns its documented floor of 0.0, which flags
every sample as spoof. It is listed for completeness, not as a usable setting.

Reading A–D together: the security operating point behaves as designed in B
(FAR ≤ 1% target met: 0.50% achieved), fails to transfer in A (target 1%,
achieved 16.93%), and is unattainable at any acceptable cost in C and D
(FRR 93–100%).

**Correction notice.** The FAR ≤ 1% / FAR ≤ 5% rows for protocols B and C were
**recomputed on 2026-09-09** from the stored per-file scores. The original runs
for those two protocols executed before a fix to `find_threshold_for_far`, which
had returned the *lowest* qualifying threshold (trivially 0.0) instead of the
highest. The model scores are unchanged and were not re-run; only this derived
threshold selection was recomputed. The superseded values are recorded in
`correction_note` inside each run's `results.json` and
`threshold_sweep_calibration.json`. Protocols A and D were produced after the
fix and are unaffected. Three regression tests in
`tests/test_evaluation_metrics.py` pin the corrected direction.

---

## 8. Risk Engine threshold tuning

The brief asked for evidence-driven tuning of the Risk Engine. The evidence was
gathered, every candidate threshold was examined against it, and **the
conclusion is that no weight or threshold change is justified by what was
measured.** That is a result, not an omission, and the reasoning for each
candidate is recorded below so it can be challenged.

### 8.1 Why the measurements do not support tightening

Tuning a threshold is only meaningful if the score it thresholds has a stable
scale. §7.2 measured the opposite: the same score cut moved from 1% to 16.93%
FAR when the attack family changed, and §7.7 measured that a monotone
recalibration does not repair this. Re-tuning the *fusion* thresholds against
ASVspoof-derived numbers would therefore transfer a false precision into the
policy layer — it would look principled and be arbitrary.

Critically, **there is no runtime domain detector**. The system cannot tell, on
a live call, whether it is in the regime where authenticity has AUC 0.999 or the
regime where it has AUC 0.60. Any threshold tuned for the first regime is unsafe
in the second, and none of the measurements let us distinguish them at inference
time.

§7.5 makes this worse in a specific way that is worth spelling out. The
out-of-domain failure is not confined to spoofs slipping through; on WaveFake
the detector scored **genuine human speech at a mean of 0.906**. So the same
untuned threshold produces opposite errors on different corpora — misses on
MLAAD, false alarms on WaveFake. There is no single direction to move a
threshold that improves both.

### 8.2 Candidates considered, and the decision on each

| # | Candidate | Old | New | Dataset / split | Measured tradeoff | Decision & security justification |
|---|---|---|---|---|---|---|
| 1 | `weights.authenticity` ↑ (0.50 → 0.65) | 0.50 | **0.50 (unchanged)** | MLAAD-tiny + WaveFake test splits | Would raise a stream measuring **AUC 0.6055** (unseen TTS) and **0.5970** (unseen vocoders); 7 of 22 MLAAD generators below chance | **Rejected.** Increasing the weight of a near-chance signal increases both false accepts and false alarms. The in-domain 0.9990 AUC is not evidence for the deployment regime. |
| 2 | `weights.authenticity` ↓ (0.50 → 0.35) | 0.50 | **0.50 (unchanged)** | ASVspoof eval, speaker-disjoint | Would weaken the stream in the regime where it measures **AUC 0.9990 / EER 1.20%** | **Rejected.** Without a runtime domain detector, lowering the weight degrades the cases the detector gets right, and §8.3 shows fusion already caps single-stream influence. |
| 3 | `thresholds.suspicious` ↓ (40 → 30) | 40 | **40 (unchanged)** | ASVspoof official dev→eval | Dev-tuned cut points missed their FAR target by 17× on eval | **Rejected.** Tightening on a scale shown not to transfer buys measured FRR for unmeasured FAR benefit. |
| 4 | `thresholds.critical` ↓ (85 → 75) | 85 | **85 (unchanged)** | §8.3 fusion analysis | Would let **authenticity alone at critical consequence (score 75) reach CRITICAL → HOLD** | **Rejected.** This is precisely the single-stream dominance the architecture exists to prevent, and it would be driven by the least reliable stream. |
| 5 | `min_confidence_for_allow` ↑ (0.25 → 0.40) | 0.25 | **0.25 (unchanged)** | §8.3 policy trace | Already escalates the thin-evidence high-consequence case to VERIFY at 0.25 (coverage 0.333 × conf 0.9 = 0.300) | **Rejected as unnecessary.** The guard already fires on the dangerous case; raising it only adds false VERIFYs on low-consequence traffic. |
| 6 | Treat low authenticity as *negative* risk | not implemented | **still not implemented** | MLAAD-tiny, 7/22 generators AUC < 0.5 | For those generators a low score is anti-correlated with truth | **Confirmed correct as-is.** `contributions["authenticity"] = auth × w × 100` means a "clean" verdict contributes **0**, never a subtraction. A fooled detector cannot talk the score *down*. |
| 7 | Add a high-authenticity auto-escalation rule | not implemented | **still not implemented** | WaveFake test, bona fide mean score **0.906** | On an unseen corpus the detector scores *genuine* speech at 0.9+; an auto-escalate-on-high-score rule would fire on real callers | **Rejected.** §7.5 shows a high authenticity score is not reliable evidence of synthesis out of domain. Escalation must stay a multi-stream decision. |

### 8.3 Fusion behaviour, verified empirically

Measured by driving `compute_risk` + `policy.evaluate` directly:

**Can one stream dominate?** No. Authenticity alone, at maximum alarm and full confidence:

| Consequence | Score | State | Decision |
|---|---|---|---|
| low | 50 | suspicious | VERIFY |
| medium | 57 | suspicious | VERIFY |
| high | 65 | high | VERIFY |
| critical | 75 | high | VERIFY |

Authenticity alone **cannot reach CRITICAL (85) or HOLD** at any consequence
level — its ceiling is 50 points, 75 after the ×1.5 multiplier. Single-stream
dominance is structurally impossible under the current weights, which is why
candidate #4 was rejected.

**Does the system survive a total authenticity failure?** Yes — this is the
measured payoff of keeping the three streams separate. Simulating the §7.4
failure mode, where an unseen generator is confidently scored as bona fide
(authenticity = 0.05 on an actual spoof):

| Scenario | Score | State | Decision |
|---|---|---|---|
| authenticity only, low consequence | 2 | insufficient_evidence | ALLOW |
| authenticity only, critical consequence | 4 | insufficient_evidence | **VERIFY** *(confidence guard)* |
| authenticity fooled **+ identity 0.2 + context 0.85**, critical | 66 | high | **VERIFY** |

In the last row authenticity contributes 2.5 points out of 66 — it has failed
completely — and the call is still escalated to independent verification by the
identity and context streams. **This is the strongest argument in this document
for the multi-stream architecture, and unlike the accuracy numbers it holds
regardless of which TTS system the attacker uses.**

### 8.4 What would actually justify a change

Stated so the absence of tuning is falsifiable rather than convenient:

1. A calibration set drawn from **real telephony** in the deployment
   population — at which point §7.7's shipping decision should be revisited and
   `USE_CALIBRATED_SCORE_FOR_FUSION` reconsidered.
2. A detector whose OOD AUC is materially above 0.6055 — retraining or
   replacing AASIST on a modern corpus (MLAAD, ASVspoof 5) is the highest-value
   next step, and is worth far more than any threshold move.
3. A **runtime input-quality guard**. §7.5 found `gain_minus_20db` is the one
   degradation that raises false accepts (18.00%, 9× clean). A level check that
   downgrades `authenticity_confidence` on very quiet audio is a genuinely
   evidence-backed improvement; it is deliberately **not** implemented here
   because it is a new runtime feature rather than a threshold change, and the
   brief scoped this task to evaluation and tuning.
