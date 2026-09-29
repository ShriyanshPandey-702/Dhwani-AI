# Dhwani AI — Phase 1: Controlled AASIST-L Fine-Tuning

**Status of the frozen baseline: untouched.** The original AASIST-L checkpoint
(`sha256 814331d0…ce27a`) is never written to. Every Phase 1 model is a separate
file under `experiments/phase1_aasist/checkpoints/`, and no production
configuration points at one.

---

## 1. Objective

Not "raise ASVspoof accuracy". The question is narrower and harder:

> Can controlled fine-tuning of AASIST-L improve **generalization** without
> destroying its existing in-domain spoof-detection capability?

### A prediction registered before training

This must be stated up front so the result cannot be re-framed afterwards.

**The only TRAIN-ALLOWED corpus available locally is ASVspoof 2019 LA train
(A01–A06) — exactly the data AASIST-L's authors already trained on.** Schemes
A/B1/B2/C therefore add **no new domain information**. On the evidence from
Phase 0 (the failure is bona-fide domain shift), the expected outcome is that
none of the four schemes materially improves out-of-domain performance.

That makes Phase 1 primarily a **controlled negative experiment** plus
infrastructure. It is still worth running, because it establishes:

* a reproducible, leakage-proof training pipeline (reusable when a legally
  clear multi-domain corpus arrives);
* the catastrophic-forgetting behaviour of each freezing scheme;
* whether the architecture's built-in `Freq_aug` — the one lever here that
  actually adds signal diversity — moves out-of-domain numbers at all.

A negative result is reported as a negative result.

---

## 2. Dataset provenance and classification

Every dataset physically present on this machine, classified:

| Dataset | On disk | Licence | Classification | Reason |
|---|---|---|---|---|
| **ASVspoof 2019 LA train** | 25,380 flac | ODC-BY (`LICENSE.txt` in tree) | **TRAIN-ALLOWED** | Open licence, attribution only |
| **ASVspoof 2019 LA dev** | 24,986 flac | ODC-BY | **VALIDATION-ONLY** | Speaker-disjoint from train |
| ASVspoof 2019 LA eval | 71,933 flac | ODC-BY | **TEST-ONLY** (α) | Frozen benchmark |
| MLAAD-tiny subset | 10,913 wav | **CC BY-NC** | **EXCLUDED from training** (β) | Licence names training explicitly; also a test set |
| WaveFake subset | 1,057 wav | CC-BY-SA-4.0 | **TEST-ONLY** (γ) | Frozen benchmark |
| LJSpeech-1.1 | 11,573 wav | Public domain | **EXCLUDED** | It *is* γ's bona-fide half — training on it would leak into γ |
| In-the-Wild | 31,779 wav | CC-BY-SA-4.0 | **TEST-ONLY, SEALED** (δ) | Phase 0 seal; opened once, never tuned on |

Nothing was downloaded for Phase 1. ASVspoof 5 was **not** downloaded and is not
used (future work).

### Train / validation split

| | Split | Content |
|---|---|---|
| TRAIN | ASVspoof 2019 LA **train** | A01–A06, 20 speakers |
| VALIDATION | ASVspoof 2019 LA **dev** | A01–A06, 20 speakers |

Measured disjointness: **0 shared files, 0 shared speakers** (asserted in
`tests/test_phase1_training.py` and re-checked at the start of every run, which
aborts on any overlap).

`training/data.py` raises on any split other than `train`/`dev`, so a test
corpus cannot be loaded by the training package even by mistake.

---

## 3. Class balancing — and why this option

Measured imbalance in ASVspoof 2019 LA train: **8.84 : 1** spoof-heavy
(22,800 spoof / 2,580 bona fide).

| Option | Assessment |
|---|---|
| Raw distribution | Rejected — 88% of gradient signal comes from one class |
| Class-weighted loss | Viable, but introduces a weighting hyperparameter that would become a second experimental variable |
| **1:1 balanced subset** | **Chosen** |
| Combination | Rejected — unnecessary complexity for a controlled comparison |

**Chosen: 1:1 balanced subset**, keeping **every** bona-fide example (2,580) and
drawing an equal number of spoof examples stratified evenly across A01–A06.

Reasoning: the minority class carries the bona-fide information that Phase 0
identified as the failure axis, so discarding none of it matters; equal class
weight is achieved without inventing a loss-scaling constant; and holding the
loss function fixed keeps *which layers are trainable* the only intended
variable (§8 of the brief). Attack stratification prevents a single attack type
from dominating the spoof side.

Result: **5,160 training samples/epoch** (2,580 + 2,580), validated on
**2,000 dev samples** (1,000 + 1,000), balanced the same way.

---

## 4. Preprocessing

Imported from the inference path so training and inference cannot drift:

| | |
|---|---|
| Sample rate | 16 kHz mono |
| Window | 64,600 samples (4.0375 s) |
| Length policy | tile if short, centre-crop if long |
| Normalisation | none beyond float32 `[-1, 1]` |
| Version | `prep-v1` |

`tests/test_phase1_training.py` asserts `training.data.fit_length` is
byte-identical to `AASISTDetector._fit_length` across short, exact and long
inputs.

### The label-convention bug (caught before the real runs)

AASIST's released checkpoints use **output index 1 = bona fide**. The dataset
labels are `0 = bona fide, 1 = spoof`. Training targets must therefore be
**inverted** into the model's convention.

The first smoke run showed training loss ≈ **12** on data the model classifies
perfectly (validation EER 0.000) — the signature of maximally-wrong targets.
With `to_model_target()` applied, loss dropped to **0.86** immediately and to
**0.005** on the full run. Without this fix, fine-tuning would have taught the
exact inverse of the pretrained behaviour and every "catastrophic forgetting"
number would have been an artefact. The mapping is now asserted by a test.

---

## 5. Model and freezing schemes

AASIST-L, **85,306** parameters. Counts verified against the implementation, not
taken from documentation:

| Scheme | Trainable | % | Frozen BN modules | What moves |
|---|---|---|---|---|
| **A** | **322** | 0.38% | 18 | `out_layer` only |
| **B1** | **34,514** | 40.46% | 11 | GAT + pooling + head; encoder frozen |
| **B2** | **66,234** | 77.64% | 3 | encoder blocks 2–5 + GAT + head |
| **C** | **85,306** | 100.00% | 0 | everything |

Two implementation facts that shaped this table:

* **`conv_time` (the sinc front-end) has zero trainable parameters** — the
  band-pass filters are computed in `__init__` and are not `nn.Parameter`s. So
  "freeze the front-end" is not a meaningful scheme and is deliberately not
  offered. Asserted by test.
* **`requires_grad = False` does not freeze BatchNorm.** A BN module in
  `train()` keeps updating `running_mean`/`running_var` regardless. Frozen BN
  modules are therefore forced into `eval()` at the start of every epoch by
  `set_train_mode()`. Two tests prove this: frozen BN stats do **not** move
  across forward passes, and — as a control — unfrozen BN in Scheme C **does**.

### An upstream defect, documented and deliberately not fixed

In the vendored `Residual_block.forward`:

```python
if not self.first:
    out = self.bn1(x)
    out = self.selu(out)
else:
    out = x
out = self.conv1(x)      # ← consumes x, not out
```

`bn1` is computed and discarded. It is dead code in upstream AASIST. The
consequence is that **10 parameters (224 values, 0.26%) can never receive
gradient** in any scheme — `encoder.{1..5}.0.bn1.{weight,bias}`. Scheme C's
"100% trainable" is really 99.74% effective.

This is **not fixed**: the brief forbids architecture changes, the released
checkpoints were trained with this same dead path, and repairing it would make
the frozen baseline and the fine-tuned models architecturally incomparable.

---

## 6. Hyperparameters

Held identical across A/B1/B2/C so the only intended variable is which layers
train.

| | |
|---|---|
| Optimiser | AdamW |
| Learning rate | **1e-5**, same for every scheme |
| Weight decay | 1e-4 |
| Batch size | 8 |
| Epochs | 3 (pilot) |
| Gradient clipping | norm 1.0 |
| Loss | `CrossEntropyLoss`, unweighted (data is already 1:1) |
| Seed | 1337 |
| Device | MPS (Apple M4) |

A single learning rate is used deliberately. Giving Scheme A a larger LR because
it has fewer parameters would have introduced a second variable and made the
comparison uninterpretable — a pilot at lr 1e-3 on the 322-param head was run
and discarded for exactly this reason.

**MPS is numerically equivalent to CPU here**: on the frozen checkpoint, MPS and
CPU produced bit-identical outputs (max abs diff 0.000e+00), so training on MPS
and evaluating on CPU is sound. Training on MPS measured **5.86 samples/s**
versus **0.53 samples/s** on CPU — an 11× difference that made Phase 1 feasible
on this machine at all.

---

## 7. Checkpoint selection rule — fixed before results

Recorded in `training/train.py` and in every run's JSON:

1. **Primary** — lowest validation EER.
2. **Tie-break** — if two checkpoints are within **0.005** absolute EER, prefer
   the lower **FAR** at the validation EER threshold (a security system should
   prefer admitting fewer spoofs).
3. **Guard** — a checkpoint with validation **FRR > 0.20** is ineligible, unless
   no checkpoint qualifies, in which case the violation is recorded.

Validation uses ASVspoof dev only. No test set participates in selection.

---

## 8. Leakage controls

| Control | Mechanism |
|---|---|
| Test corpora unreachable from training | `load_items` raises for any split ≠ train/dev; tested |
| Train/dev file overlap | asserted 0 at run start; run aborts otherwise |
| Train/dev speaker overlap | asserted 0 by test |
| No test paths in training data | tested against `InTheWild`, `MLAAD`, `WaveFake`, `LJSpeech`, `_eval` |
| δ never used for tuning | δ is not importable by `training/`; it is scored once by `eval_checkpoint.py` after selection is complete |
| Thresholds | imported from the ASVspoof **dev** sweep; never re-fitted on any test set |

---

## 9. Reproducibility

```bash
# one scheme
python training/train.py --scheme C --seed 1337 --epochs 3 \
    --batch-size 8 --lr 1e-5 --weight-decay 1e-4 --workers 6 --val-per-class 1000

# evaluate a checkpoint on the frozen test sets
python training/eval_checkpoint.py \
    --checkpoint experiments/phase1_aasist/checkpoints/<tag>.pth --tag <tag>

# build the scorecard
python training/scorecard.py
```

Every run writes a JSON record containing: model version, scheme and exact
trainable-parameter count, selection rule, full epoch history, hyperparameters,
class balance, train/validation speaker lists, preprocessing version, checkpoint
SHA-256, base checkpoint SHA-256, environment, duration and timestamp.

Artifacts:

```
experiments/phase1_aasist/
  baseline/frozen_baseline_record.json   frozen checkpoint + benchmark record
  scheme_{A,B1,B2,C}/*.json              per-run records
  checkpoints/*.pth                      research checkpoints (never production)
  logs/*.log                             full training logs
  reports/scorecard.md                   generalization scorecard
evaluation/results/phase1_*.json         machine-readable test results
```

---

## 10. Results

Seed 1337, 3 epochs, balanced 5,160-sample training set, validated on 2,000 dev
samples. All test numbers measured on the **identical frozen manifests** with
`prep-v1` and cascade disabled.

### 10.1 Validation — the only basis for model selection

| Model | trainable | best epoch | val EER | val AUC | val FAR | val FRR | train time |
|---|---|---|---|---|---|---|---|
| *(pretrained, epoch 0)* | — | — | **0.0060** | 0.9993 | 0.0060 | 0.0060 | — |
| Scheme A | 322 | 1 | **0.0060** | 0.9993 | 0.0060 | 0.0060 | 14.0 min |
| Scheme B1 | 34,514 | 1 | 0.0070 | 0.9995 | 0.0070 | 0.0070 | 21.9 min |
| Scheme B2 | 66,234 | 1 | 0.0070 | 0.9995 | 0.0070 | 0.0070 | 29.5 min |
| Scheme C | 85,306 | 1 | 0.0070 | 0.9996 | 0.0070 | 0.0070 | 48.3 min |

Two things stand out. **No scheme improved validation EER over the untouched
pretrained model**, and **every scheme selected epoch 1** — further training
never helped. Validation cannot separate these models: the spread (0.0060 vs
0.0070) is one misclassified sample in 2,000.

Applying the pre-registered rule (§7) to validation only — primary EER, tie
within 0.005 broken by lower FAR — the winner is **Scheme A**, which is
functionally the frozen baseline. The rule, honestly applied, says *change
nothing*.

### 10.2 Generalization scorecard

| Model | α ASVspoof AUC | α EER | β MLAAD AUC | β EER | γ WaveFake AUC | γ EER | δ In-the-Wild AUC | δ EER |
|---|---|---|---|---|---|---|---|---|
| **frozen AASIST-L** | 0.9987 | 1.07% | 0.6055 | 43.40% | 0.5970 | 41.60% | **0.6739** | 38.40% |
| Scheme A | 0.9987 | 1.07% | 0.6056 | 43.40% | 0.5972 | 41.60% | 0.6736 | 38.40% |
| Scheme B1 | 0.9985 | 1.27% | 0.6179 | 42.77% | 0.6284 | 41.92% | 0.6530 | 39.07% |
| Scheme B2 | 0.9992 | 1.07% | 0.6208 | 42.14% | 0.6284 | 41.12% | 0.6347 | 40.73% |
| Scheme C | 0.9992 | 1.13% | **0.6263** | 41.33% | **0.6348** | 41.44% | 0.6432 | 40.20% |

### 10.3 The central finding

Ordered by trainable capacity (A → B1 → B2 → C), the out-of-domain sets move in
**opposite directions**:

| Trainable | β MLAAD ΔAUC | γ WaveFake ΔAUC | **δ In-the-Wild ΔAUC** |
|---|---|---|---|
| 322 (A) | +0.0001 | +0.0002 | −0.0003 |
| 34,514 (B1) | +0.0123 | +0.0314 | **−0.0209** |
| 66,234 (B2) | +0.0153 | +0.0314 | **−0.0392** |
| 85,306 (C) | +0.0208 | +0.0378 | **−0.0307** |

**More fine-tuning on ASVspoof makes the model better on corpora that resemble
ASVspoof synthesis (β, γ) and worse on genuinely real-world audio (δ).** The
effect scales with how much of the network is allowed to move: Scheme A, which
changes almost nothing, moves nothing.

This is a sharper statement of the Phase 0 diagnosis. Training on ASVspoof does
not add domain coverage — it *deepens domain specialisation*. β (TTS-corpus
audio) and γ (vocoded LJSpeech) are laboratory synthesis, closer to ASVspoof's
own construction; δ is found real-world speech. Optimising harder on the
training domain pulls the model further from δ.

The security-relevant direction confirms it: on δ, Scheme C's **FAR rises by
+0.1053** at the matched operating point — the model admits ten percentage
points more spoofs on real-world audio than the frozen baseline does.

**δ earned its seal here.** Judged on β and γ alone, every scheme from B1 up
would look like an improvement and Scheme C would look like the winner. The
sealed fourth corpus is the only thing that reveals the trade.

### 10.4 Catastrophic forgetting: did not occur

| Model | α ΔAUC | α ΔEER |
|---|---|---|
| Scheme A | +0.0000 | +0.0000 |
| Scheme B1 | −0.0002 | +0.0020 |
| Scheme B2 | +0.0005 | +0.0000 |
| Scheme C | +0.0005 | +0.0007 |

In-domain capability was **preserved in every scheme**, including full
fine-tuning. α ROC-AUC stayed within ±0.0005 of 0.9987 and EER within
+0.20 pp of 1.07%. At lr 1e-5 for 3 epochs, with frozen-BN handling where the
scheme requires it, catastrophic forgetting is not the binding constraint here.
That is a genuine and reusable result: the pipeline can fine-tune this model
without destroying it. The problem is that there is nothing useful to fine-tune
it *on*.

### 10.5 Acceptance criteria — not met

Phase 0 §13 required **β ≥ 0.75 AND γ ≥ 0.75 AND δ improved**, with α retained.

| Criterion | Required | Best achieved | Verdict |
|---|---|---|---|
| β AUC | ≥ 0.75 | 0.6263 (C) | ✗ |
| γ AUC | ≥ 0.75 | 0.6348 (C) | ✗ |
| δ AUC | > 0.6739 | 0.6736 (A) | ✗ — every scheme ≤ baseline |
| α AUC | ≥ 0.99 | 0.9992 | ✓ |
| α EER | ≤ 2.0% | 1.07% | ✓ |

**No scheme qualifies.** The in-domain guard is satisfied by all of them; no
scheme comes close on the out-of-domain requirements, and none improves δ.

### 10.6 Streaming compatibility

Both the selected model (A) and the maximally-changed model (C) are drop-in
replacements — same 16 kHz / 64,600-sample window, same 4038 ms / 1000 ms
streaming contract, same two-logit output schema, loading with `strict=True`.

| | Scheme A | Scheme C | frozen baseline |
|---|---|---|---|
| inference p50 | 273.8 ms | 259.0 ms | ~455.7 ms |
| inference p95 | 437.4 ms | 299.2 ms | ~805.1 ms |
| cold start | 4.34 s | 4.30 s | ≈4.5 s |
| steady state | 0.3–1.3 s | 0.26–1.26 s | ≈0.4–1.4 s |

Latency is dominated by the 4038 ms window accumulation in every case and is
never zero. Network transport was not measured.

---

## 11. Limitations

1. **The training corpus adds no new domain information.** It is the data the
   model was already trained on. This bounds what Phase 1 can possibly show
   (§1).
2. **One seed (1337).** Multi-seed runs were out of budget on this hardware; a
   difference smaller than seed variance cannot be distinguished from noise, and
   none is claimed.
3. **Three epochs, pilot scale.** Not a converged training run.
4. **No channel/noise augmentation arm.** Only the architecture's built-in
   `Freq_aug` was available without introducing new dependencies, and training
   on `evaluation/robustness/transforms.py` conditions would contaminate the
   robustness benchmark that uses those same conditions.
5. **δ has no generator labels**, so it measures domain transfer, not
   unseen-generator performance.
6. Nothing here says anything about telephony, Indian-English, or live calls.
