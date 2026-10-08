# Dhwani AI — Phase 0 Dataset & Experiment Design Review

**PLANNING ONLY.** Nothing downloaded, no code changed, no training run, no
dataset modified, no Risk Engine or dashboard change. Verified numbers come from
the frozen baseline and from read-only inspection of the vendored model.

---

## 0. Two corrections to the previous audit

Read-only inspection of `vendor/aasist_model.py` produced two facts that change
the experiment design. Both are stated up front because the earlier audit was
wrong on the first.

**(a) "Freeze the sinc front-end" is a no-op.** `conv_time` (the `CONV`
sinc-convolution layer) has **0 trainable parameters** — the Mel-spaced
band-pass filters are computed in `__init__` and are not `nn.Parameter`s. The
previous audit offered "freeze the sinc front-end" as the conservative fallback.
That fallback does not exist. Partial fine-tuning must be defined over the
**encoder** and **GAT** blocks instead.

**(b) The architecture already ships a training-time augmentation.**
`Model.forward(x, Freq_aug=False)` passes `mask=True` into `CONV.forward`, which
zeroes a random contiguous band of up to 20 sinc filters. This is upstream's own
frequency-masking augmentation, available at zero implementation cost and
architecture-sanctioned. It should be enabled during training and must remain
`False` at inference (it already is).

### Measured parameter budget (AASIST-L, 85,306 total)

| Module | Params | % |
|---|---|---|
| `encoder` (6 residual blocks) | 50,792 | 59.54% |
| `HtrgGAT_layer_ST11/12/21/22` | 29,664 | 34.77% |
| `GAT_layer_S` + `GAT_layer_T` | 3,744 | 4.39% |
| `pos_S`, `master1`, `master2` | 600 | 0.70% |
| pooling layers | 182 | 0.21% |
| **`out_layer` (the classifier head)** | **322** | **0.38%** |
| `first_bn` | 2 | 0.00% |
| `conv_time` (sinc) | **0** | 0.00% |

Per encoder block: `[0] 6,592 · [1] 12,480 · [2] 10,552 · [3] 7,056 · [4] 7,056 · [5] 7,056`.

---

## 1. TEST δ — exact candidate

### Primary: **"In-the-Wild" audio deepfake dataset** (Müller et al., 2022)

| Property | Value |
|---|---|
| Full name | *Does Audio Deepfake Detection Generalize?* — "In-the-Wild" release |
| Version | the single public `release_in_the_wild` archive |
| Composition *(as reported by the authors — **to be verified at acquisition**)* | ≈31,700 clips; ≈20.8 h bona fide, ≈17.2 h spoofed |
| Languages | **English only** |
| Speakers | **58** named public figures (politicians, celebrities) |
| Generators / vocoders | **Unlabelled and uncontrolled** — spoofs were *collected from the internet*, not synthesised by the authors |
| Licence | Research / non-commercial (Fraunhofer AISEC, same licensor family as MLAAD) — **must be verified in writing** |
| Accessibility | Public download; historically no approval gate — **verify** |

**Why it is genuinely useful as δ.** It is the only candidate whose *bona-fide*
half is real-world audio — interviews, speeches, podcasts — rather than studio
read speech or a TTS corpus's source recordings. The frozen diagnosis is that
AASIST-L fails on **unfamiliar bona fide** (mean score 0.906 on genuine
LJSpeech). δ must therefore stress the bona-fide side hardest, and In-the-Wild
is the only listed corpus that does. It is also structurally orthogonal to
α (VCTK-derived studio), β (TTS-corpus audio) and γ (single-speaker audiobook),
so a δ result cannot be explained by similarity to any set already used.

**Its weakness, stated plainly.** No generator labels, so δ **cannot** measure
unseen-generator performance. That measurement stays with β (22 labelled MLAAD
generators). Division of labour: **β = unseen generators, γ = unseen vocoders on
matched content, δ = unseen real-world domain.**

**Non-commercial caveat.** If δ is research-only, every δ result is
non-commercial evidence — acceptable for the current academic research context,
identical to how β is already used, but it must be recorded, and it means δ
cannot underwrite a commercial claim later.

### Fallback: **ASVspoof 5 evaluation partition**

Use only if In-the-Wild proves inaccessible or its licence forbids even
evaluation. **This fallback is expensive**, because §3 assigns ASVspoof 5 to
TRAIN — it is the load-bearing both-classes modern corpus. Spending it as δ
leaves the training set without modern attacks. If the fallback is triggered,
the programme should pause rather than proceed with a weak training mix.

### The leakage risk that decides a training exclusion

In-the-Wild is celebrity and politician speech harvested from the internet.
**VoxCeleb is also celebrity speech harvested from YouTube.** Speaker overlap
between the two is not merely possible, it is likely by construction. Training
on VoxCeleb while testing on δ would leak speakers into the "unseen" set and
silently inflate the headline result.

→ **VoxCeleb is excluded from TRAIN** (§3). This is independent of, and
additional to, its research-only licence.

---

## 2. Exact TRAIN / VALIDATION / TEST design

| Role | Content | Partition rule |
|---|---|---|
| **TRAIN** | ASVspoof 2019 LA **train** (2,580 bona fide / 22,800 spoof, 20 speakers, A01–A06) — *rehearsal anchor* · **ASVspoof 5 train** (pending §3) — *modern both-classes source* · optional bona-fide-only corpora, **ablated** | never used for any selection |
| **VALIDATION** | ASVspoof 2019 LA **dev** (2,548 / 22,296, 20 speakers, A01–A06) · held-out **speakers ∧ attacks** carved from ASVspoof 5 train | early stopping + checkpoint selection **only** |
| **TEST α** | ASVspoof 2019 LA **eval** (A07–A19, 67 speakers) — frozen manifests | regression gate |
| **TEST β** | MLAAD-tiny frozen subset (196/155 calib, 196/159 test) | sealed |
| **TEST γ** | WaveFake + LJSpeech frozen subset (432/432 calib, 625/625 test) | sealed |
| **TEST δ** | In-the-Wild, sealed at Phase 0 | opened **once** |

**Verified disjointness already on disk:** ASVspoof 2019 LA train ∩ dev = **0**
speakers, train ∩ eval = **0**, dev ∩ eval = **0**.

**Rules.**
1. No test set (α, β, γ, δ) may influence training, hyperparameter search,
   augmentation choice, early stopping, or checkpoint selection.
2. Split ASVspoof 5 by **speaker and attack simultaneously** — a speaker-only
   split leaves attacks seen; an attack-only split leaves speakers seen.
3. Partition generators by **family**, not by `lang/system` string (the frozen
   β run has four families appearing on both sides under different languages;
   a future split must not repeat that).
4. δ is hashed, manifested and sealed **before** the first training step, and
   audited for speaker overlap against every TRAIN corpus at acquisition.

### The class-corpus correlation constraint — and where it bites

The diagnosed failure is that the model learned *corpus* rather than *artefact*.
The obvious remedy — bulk-adding bona-fide-only corpora (LibriSpeech, Common
Voice) — risks teaching the inverse shortcut: "unfamiliar domain ⇒ spoof",
which is precisely today's failure mode, reinforced.

Therefore:

- **Mandatory:** at least one large corpus supplying **both classes from the
  same recording domain**. ASVspoof 5 is the designated candidate.
- **Permitted but conditional:** bona-fide-only corpora may be added **only**
  with a matching expansion of spoof-side domain diversity, and their
  contribution **must be ablated** (train with and without; compare on δ).
  They are never added on the assumption that more bona fide is automatically
  better.

**Consequence for programme viability:** with β and γ both sealed as test sets,
and MLAAD licence-blocked, **ASVspoof 5 is the single load-bearing acquisition.**
If it cannot be obtained legally, the training mix reduces to 2019-era attacks
plus bona-fide-only corpora, which does not support the diagnosis-driven design.
That is a Phase 2 gate, not a Phase 0 blocker — but it must be resolved before
any compute is spent.

---

## 3. Datasets legally safe for TRAINING

| Dataset | Licence | Training verdict | Reason |
|---|---|---|---|
| **ASVspoof 2019 LA train** | ODC-BY (`LICENSE.txt` verified in the extracted tree) | ✅ **SAFE — use** | Attribution only. Rehearsal anchor |
| **ASVspoof 5 train** | to verify (expected open/ODC-BY); registration possible | ⚠️ **CONDITIONAL — verify first** | Load-bearing; both classes, modern attacks |
| **MUSAN** (OpenSLR 17) | CC BY 4.0 | ✅ **SAFE — augmentation** | Real noise/babble |
| **RIR & Noise DB** (OpenSLR 28) | Apache 2.0 | ✅ **SAFE — augmentation** | Real measured RIRs; targets the worst robustness failure |
| **LibriSpeech** | CC BY 4.0 | ⚠️ **Legally safe; experimentally conditional** | Bona-fide-only → ablation required (§2) |
| **Mozilla Common Voice** | CC0 (verify account/terms) | ⚠️ **Legally safe; experimentally conditional** | Bona-fide-only; adds accents incl. Indian English |
| **AI4Bharat / IndicSUPERB** | varies per release — verify | ⚠️ **CONDITIONAL** | Bona-fide-only; Indian languages |
| **IIT-Madras IndicTTS** | request + approval — **FLAGGED** | ⚠️ **CONDITIONAL** | Manual approval; studio-clean only |
| **MLAAD-tiny** | **CC BY-NC**, notice names "model training… hyperparameter tuning" | ❌ **EXCLUDED** | Licence **and** it is TEST β |
| **WaveFake** | CC-BY-SA-4.0 | ❌ **EXCLUDED** | It is TEST γ; share-alike on derived weights also unresolved |
| **VoxCeleb 1/2** | research-only, registration | ❌ **EXCLUDED** | Licence **and** likely speaker overlap with δ (§1) |
| **In-the-Wild** | research/non-commercial (verify) | ❌ **EXCLUDED from training** | It is TEST δ |
| **Any self-generated synthetic spoof** | n/a | ❌ **EXCLUDED** | Out of scope by instruction; would add a generator whose artefacts we control |

**Nothing enters TRAIN without a written licence determination recorded in the
experiment registry.**

---

## 4. AASIST adaptation experiment design

Full fine-tuning is **not** assumed to win. All three are specified and the
pilot decides on measured worst-domain validation EER.

An important compute fact first: **freezing saves very little here.** The
forward pass is unchanged by freezing and dominates cost (measured 421.7 ms per
window, CPU); the model is 85k parameters, so the backward pass is cheap in
absolute terms. A, B and C therefore cost roughly the same per epoch. **Choose
between them on generalisation and forgetting grounds, not compute.**

### A — Head-only / conservative adaptation

| | |
|---|---|
| Trainable | `out_layer` — **322 params (0.38%)**; optional `+master1/master2/pos_S` → 922 (1.08%) |
| Frozen | everything else, **and all BatchNorm modules kept in `eval()`** |
| LR | **1e-3 – 1e-2** (a linear head tolerates and needs a high LR) |
| Batch | 32–64 (BN frozen, so batch size is unconstrained by BN) |
| Epochs | 10–30 (converges fast) |
| Early stopping | patience 5 on worst-domain val EER |
| Checkpoint | best worst-domain val EER |
| Class balancing | weighted CE (ASVspoof LA train is **8.84:1** spoof-heavy) or balanced sampler |
| Augmentation | `Freq_aug=True` + gain + codec only (light) |
| Compute | ≈ same per-epoch as C; fewest epochs |

**Role: a control, not a contender.** 322 parameters can only translate and
rescale a decision boundary in a 160-dim embedding. If A closes most of the
gap, the failure was calibration-like rather than representational — which would
contradict the §6 diagnosis and is worth knowing. Expected to fail; run it
because a cheap decisive negative is valuable.

### B — Partial fine-tuning (two variants)

| | B1 | B2 |
|---|---|---|
| Trainable | GAT + pooling + head — **34,514 (40.46%)** | encoder blocks 2–5 + GAT + head — **66,234 (77.64%)** |
| Frozen | entire `encoder` | encoder blocks 0–1 (19,072 params) |
| BN in frozen blocks | **must be forced to `eval()`** — otherwise running stats still drift and "frozen" is a fiction | same |
| LR | 5e-5 – 5e-4 | 5e-5 – 5e-4 |
| Batch | 16–32 | 16–32 |
| Epochs | 5–20, early stop patience 3–5 | 5–20, patience 3–5 |
| Checkpoint | best worst-domain val EER | same |
| Class balancing | weighted CE / balanced sampler | same |
| Augmentation | full §6 set | full §6 set |

**B2 is the more principled variant** under the diagnosis: the failure is in how
clean speech is *encoded*, so most of the encoder must be free to move; only the
earliest blocks (closest to the fixed sinc filters, most likely to be generic)
are held.

### C — Full fine-tuning

| | |
|---|---|
| Trainable | **85,306 (100%)** |
| Frozen | nothing (`conv_time` has no parameters to freeze in any case) |
| LR | **1e-5 – 1e-4**, cosine decay, warmup ~1 epoch |
| Batch | 16–32 (BN stability is the binding constraint) |
| Epochs | 5–20, early stop patience 3–5 |
| Checkpoint | best worst-domain val EER, ties broken by ASVspoof-dev EER |
| Class balancing | weighted CE / balanced sampler + equal per-corpus sampling |
| Augmentation | full §6 set, applied **identically to both classes** |
| Grad clipping | norm 1.0 |
| Compute | ≈5–8 h/epoch on the verified CPU (derived from 421.7 ms forward + ≈2× backward); ~1 week for 10 epochs × 3 seeds on CPU alone |

**Highest ceiling, highest forgetting risk.** Mitigated by ASVspoof rehearsal in
the mix and by the hard α regression gate.

### Common to all three

- Seeds **1337 / 2024 / 31337**; report mean ± spread. A gain inside the seed
  spread is not a gain.
- Preprocessing must be the **identical `prep-v1` path** used at inference.
- `Freq_aug=True` during training only.
- Augmentation: real RIRs (OpenSLR 28) and MUSAN noise, gain variation, codec /
  telephone chain, mild packet loss — **both classes, identical distribution**;
  never applied to α/β/γ/δ.

---

## 5. Exact baseline comparison

Every candidate is compared against the **frozen AASIST-L baseline** using the
identical unmodified harness (`prep-v1`, cascade disabled, same manifests, same
metric code):

| Set | Protocol | Frozen ROC-AUC | Frozen EER |
|---|---|---|---|
| **α** | ASVspoof 2019 LA official dev→eval | **0.9987** | **1.07%** |
| **α′** | ASVspoof 2019 LA speaker-disjoint | 0.9990 | 1.20% |
| **β** | MLAAD-tiny subset, generator-disjoint | **0.6055** | **43.40%** |
| **γ** | WaveFake + LJSpeech subset | **0.5970** | **41.60%** |
| **δ** | In-the-Wild | *no baseline yet — must be measured with the frozen checkpoint during Phase 0* | |

**Phase 0 deliverable:** run the **current frozen AASIST-L** on δ to establish
δ's baseline. Without it there is nothing to compare against later. This is an
evaluation of the existing model, not training.

Also re-reported for every candidate: FAR/FRR/TPR/TNR at validation-selected
thresholds (the §7.9 table format), 19-condition robustness, streaming
stability + re-measured inference latency, calibration (Brier/ECE, and whether
it now transfers across attacks), bootstrap 95% CIs, ≥3 seeds.

---

## 6. Objective acceptance criteria

### Clear improvement — **all** must hold

| Dimension | Requirement |
|---|---|
| Cross-dataset AUC | **β ≥ 0.75 AND γ ≥ 0.75 AND δ ≥ baseline_δ + 0.10** |
| Cross-dataset EER | β and γ EER **≤ 25%**; δ EER improved by **≥ 10 points** |
| FAR/FRR | a validation-selected FAR ≤ 5% threshold gives **test FRR ≤ 25%** on β and γ (frozen: **93.88%** and **92.96%**) |
| Unseen generators (β) | **≤ 2 of 22** generators below 0.5 AUC (frozen: **7 of 22**); no generator below **0.40** |
| Robustness | no condition falls **> 0.05 AUC** below its frozen value; `gain_minus_20db` FAR **≤ 18%** (not worse) |
| Calibration | ECE on β and γ **not worse** than frozen, **and** ECE must not be presented as evidence of detection quality (frozen counter-example: WaveFake ECE 0.0093 at AUC 0.5970) |
| ASVspoof retention | α ROC-AUC **≥ 0.99** **and** α EER **≤ 2.0%** |
| Statistical | improvement exceeds ≥3-seed spread and bootstrap 95% CI excludes the frozen value |
| Streaming | isolated flips still **0** |

### No meaningful improvement
β or γ AUC gain **< 0.05**, or within seed spread / overlapping CI, or metrics
improve while the FAR-constrained operating point stays unusable (test FRR still
> 50%).

### Regression
Any of β, γ, δ **below** its baseline; or robustness worse by > 0.05 AUC on any
condition; or `gain_minus_20db` FAR > 18%; or isolated flips > 0.

### Unacceptable ASVspoof degradation — hard fail, ship nothing
α ROC-AUC **< 0.99** or α EER **> 2.0%** (≈2× the frozen 1.07%).

### Single-dataset success is rejected
Improvement on one out-of-domain set alone does **not** qualify. That pattern is
the signature of corpus-fitting — the exact failure being remediated. β **and**
γ **and** δ must move together, with α retained.

---

## 7. Biggest experimental risks

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| 1 | **Corpus/class leakage** — model learns corpus, not artefact | **High** | Fatal; looks like success | Mandatory both-classes corpus; ablate bona-fide-only corpora; δ as arbiter |
| 2 | **Speaker leakage δ ↔ VoxCeleb** (celebrity audio in both) | **High if VoxCeleb used** | Silently inflates δ | **VoxCeleb excluded**; name-level speaker audit of δ vs every TRAIN corpus at acquisition |
| 3 | **Generator leakage** across `lang/system` variants | Medium | Overstates unseen-generator claims | Partition by generator **family** |
| 4 | **Overfitting to β/γ** through human iteration | **High** | Destroys the only unseen claim | Seal δ **before** training; open once; every β/γ-driven design decision logged |
| 5 | **Catastrophic forgetting** of α | High under C | Loses 0.9987 AUC of real capability | ASVspoof rehearsal in the mix; hard α gate; lowest workable LR |
| 6 | **BatchNorm drift** | **High** | "Frozen" layers silently change; small-batch instability | Force `eval()` on BN in frozen blocks; batch ≥16; consider freezing BN stats globally in early epochs |
| 7 | **Class imbalance** (8.84:1 measured) | Certain | Majority-class collapse | Weighted CE or balanced sampler; report per-class metrics |
| 8 | **Licence problems** | Medium | Legal exposure; unusable results | Written determination before TRAIN; MLAAD/WaveFake/VoxCeleb already excluded |
| 9 | **Synthetic augmentation artefacts** | Medium | Gains that do not transfer | Real RIRs + MUSAN; no aggressive chaining; keep clean replicas |
| 10 | **Preprocessing drift** train vs inference | Medium | Invalidates all comparison | Single shared `prep-v1`; no-op fine-tune gate |
| 11 | **δ licence blocks even evaluation** | Low–Medium | Loses the arbiter | Verify in writing during Phase 0; ASVspoof 5 fallback (costly, §1) |
| 12 | **Calibrator invalidation** | **Certain** | Shipped calibrator becomes wrong for new scores | Refit on new validation; regenerate provenance; keep fusion flag `False` |

---

## 8. Recommended experiment order

| Step | Action | Gate |
|---|---|---|
| **0.1** | Tag `evaluation/results/*` read-only; record the frozen baseline hashes | append-only enforced |
| **0.2** | Verify In-the-Wild licence **in writing**; acquire; hash; write manifests; **seal** | licence permits evaluation |
| **0.3** | Speaker-overlap audit: δ vs every candidate TRAIN corpus | zero overlap, or corpus dropped |
| **0.4** | **Measure the frozen AASIST-L on δ** → establishes baseline_δ | δ baseline recorded, then δ sealed |
| **1** | Written licence determinations for all TRAIN candidates | ASVspoof 5 cleared, or pause |
| **2** | Acquire TRAIN/VAL corpora + MUSAN + RIRs; commit manifests/hashes, git-ignore audio | leakage audit clean on all axes |
| **3** | Build `training/` package | **no-op fine-tune (LR=0) reproduces α bit-identically** |
| **4** | Augmentation pipeline (`Freq_aug` + real RIR/MUSAN/gain/codec) | samples spectrally sane on inspection |
| **5** | **Pilot: A vs B1 vs B2 vs C**, 1 seed, short schedule, reduced mix | pick 1–2 winners on worst-domain **validation** EER — β/γ/δ untouched |
| **6** | Full runs of the winner(s), 3 seeds, full balanced mix | §6 "clear improvement" on α, β, γ |
| **7** | **Open δ exactly once** | δ agrees in direction |
| **8** | Refit calibrator on new validation; re-test cross-attack transfer | documented either way |
| **9** | Risk Engine review — only if the §16 evidence bar is met | otherwise conclusion stands |
| **10** | Integrate behind `AASIST_VARIANT`; update both SHA-256 pin sites | 286 backend / 61 mobile / 0 TS still green |

Step 5 is where the A/B/C question is answered by measurement rather than by
prior belief. Step 3's gate is the one to defend hardest: if a zero-learning-rate
fine-tune does not reproduce α exactly, training preprocessing has diverged from
inference and every later number is uninterpretable.

---

## 9. Verdict

### ✅ APPROVE PHASE 0

Phase 0 is well-scoped, non-destructive, and its prerequisites are resolved: the
δ candidate is named with a defined fallback, the sealing procedure is specified,
the frozen baseline is verified and append-only, and no training, threshold,
architecture, dashboard or Android change is involved.

**Approval is conditional on these four items being satisfied inside Phase 0:**

1. **In-the-Wild's licence is confirmed in writing to permit evaluation** for
   this project's context. If it forbids even evaluation, stop and reassess —
   do not silently substitute ASVspoof 5, because that spends the load-bearing
   training corpus.
2. **Speaker-overlap audit between δ and every candidate TRAIN corpus is run and
   recorded** before δ is sealed. VoxCeleb stays excluded regardless.
3. **The frozen AASIST-L is evaluated on δ to establish baseline_δ**, and δ is
   sealed immediately afterwards. Without a δ baseline there is nothing to
   compare against.
4. **Nothing in `evaluation/results/` is modified.** New results go in new
   directories.

**Known unresolved beyond Phase 0 — flagged now, blocking Phase 2, not Phase 0:**

- **ASVspoof 5's licence and accessibility are unverified, and the programme
  depends on it.** With β and γ sealed as tests and MLAAD licence-blocked, it is
  the only identified corpus supplying both classes in a modern domain. If it
  cannot be obtained, the diagnosis-driven training design is not executable as
  written and the plan must be revised rather than downgraded.
- Bona-fide-only corpora remain experimentally unproven and must be ablated, not
  assumed beneficial.

**Unchanged by this review:** Risk Engine weights and thresholds,
`USE_CALIBRATED_SCORE_FOR_FUSION = False`, mock mode, three-stream separation,
the frozen benchmark numbers, dashboard, Android capture, and the standing
conclusion — *"No threshold change is justified by the current evaluation."*
