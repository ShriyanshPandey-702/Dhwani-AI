# PHASE 5.3-B EXPANDED VOIP ROBUSTNESS REPORT

## 1. Environment
- commit: 49d66cc
- tag: phase-5.2-pass
- Python: 3.10.0
- Asterisk version: 20.20.1
- AASIST checkpoint hash: 814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a
- backend pipeline mode: real_ml
- model versions: AASIST-L (real_ml), ECAPA-TDNN (real_ml), Whisper base.en (real_ml)

## 2. Benchmark Scope
- 4 sources:
  - BF_1: `data/external/LJSpeech-1.1/wavs/LJ007-0005.wav` (Bona-fide studio speech)
  - BF_2: `data/external/LJSpeech-1.1/wavs/LJ001-0001.wav` (Bona-fide studio speech)
  - SP_1: `data/external/WaveFake/calib/parallel_wavegan/LJ013-0118.wav` (ParallelWaveGAN vocoder)
  - SP_2: `data/external/WaveFake/test/waveglow/LJ016-0338.wav` (WaveGlow vocoder)
- 19 conditions: clean, noise_white_20db, noise_white_10db, noise_white_5db, noise_white_0db, noise_pink_10db, noise_babble_10db, resample_8k, lowpass_4k, lowpass_3k4, telephone_band, mu_law, telephone_chain, gain_minus_20db, gain_plus_6db, clipping, reverb_300ms, packet_loss_2pct, packet_loss_5pct
- 76 calls: 4 sources × 19 conditions = 76 live calls
- seeds: deterministic, base seed 1337 (range: 1337 to 1412)

## 3. Overall Execution
- attempted: 76
- completed: 76
- failed: 0
- valid ML calls: 75/76
- missing ML evidence calls: 1/76
- total valid AASIST windows: 465
- total missing AASIST windows: 1216

The benchmark confirms that AASIST-L produced real-ML authenticity outputs through the live VoIP pipeline under the tested conditions. However, because the selected bona-fide and spoof samples produced similarly high AASIST scores in this benchmark, these 76 calls should not be interpreted as evidence of class-discriminative spoof-detection accuracy. The benchmark primarily evaluates end-to-end VoIP robustness, evidence availability, RTP integrity, latency, and policy stability under controlled transmission impairments.

## 4. Bona-fide Results

| Condition | Calls | AASIST | ΔAASIST | Risk | ΔRisk | Flip Rate | Missing Evidence |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| clean | 2 | 0.9995 | +0.0000 | 10.96 | +0.00 | 0.0% | 0/2 |
| noise_white_20db | 2 | 0.9975 | -0.0019 | 11.57 | +0.60 | 0.0% | 0/2 |
| noise_white_10db | 2 | 0.9997 | +0.0002 | 11.57 | +0.60 | 0.0% | 0/2 |
| noise_white_5db | 2 | 1.0000 | +0.0004 | 11.57 | +0.60 | 0.0% | 0/2 |
| noise_white_0db | 2 | 1.0000 | +0.0005 | 11.57 | +0.60 | 0.0% | 0/2 |
| noise_pink_10db | 2 | 0.9998 | +0.0003 | 11.57 | +0.60 | 0.0% | 0/2 |
| noise_babble_10db | 2 | 0.9990 | -0.0006 | 11.57 | +0.60 | 0.0% | 0/2 |
| resample_8k | 2 | 0.9990 | -0.0004 | 10.36 | -0.60 | 0.0% | 0/2 |
| lowpass_4k | 2 | 0.9960 | -0.0034 | 10.36 | -0.60 | 0.0% | 0/2 |
| lowpass_3k4 | 2 | 0.9987 | -0.0008 | 10.36 | -0.60 | 0.0% | 0/2 |
| telephone_band | 2 | 0.9990 | -0.0006 | 10.36 | -0.60 | 0.0% | 0/2 |
| mu_law | 2 | 0.9994 | -0.0001 | 10.96 | +0.00 | 0.0% | 0/2 |
| telephone_chain | 2 | 0.9990 | -0.0004 | 10.36 | -0.60 | 0.0% | 0/2 |
| gain_minus_20db | 2 | 0.4254 | -0.5741 | 5.28 | -5.68 | 0.0% | 0/2 |
| gain_plus_6db | 2 | 0.9999 | +0.0004 | 10.96 | +0.00 | 0.0% | 0/2 |
| clipping | 2 | 0.9995 | +0.0000 | 10.96 | +0.00 | 0.0% | 0/2 |
| reverb_300ms | 2 | 1.0000 | +0.0005 | 10.96 | +0.00 | 0.0% | 0/2 |
| packet_loss_2pct | 2 | 0.9995 | +0.0000 | 10.96 | +0.00 | 0.0% | 0/2 |
| packet_loss_5pct | 2 | 0.9996 | +0.0002 | 9.71 | -1.26 | 0.0% | 0/2 |

## 5. Spoof Results

| Condition | Calls | AASIST | ΔAASIST | Risk | ΔRisk | Flip Rate | Missing Evidence |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| clean | 2 | 0.9984 | +0.0000 | 10.36 | +0.00 | 0.0% | 0/2 |
| noise_white_20db | 2 | 0.9966 | -0.0019 | 11.57 | +1.21 | 0.0% | 0/2 |
| noise_white_10db | 2 | 0.9993 | +0.0009 | 11.57 | +1.21 | 0.0% | 0/2 |
| noise_white_5db | 2 | 0.9998 | +0.0014 | 11.57 | +1.21 | 0.0% | 0/2 |
| noise_white_0db | 2 | 0.9999 | +0.0015 | 11.57 | +1.21 | 0.0% | 0/2 |
| noise_pink_10db | 2 | 0.9992 | +0.0009 | 11.57 | +1.21 | 0.0% | 0/2 |
| noise_babble_10db | 2 | 0.9989 | +0.0004 | 11.57 | +1.21 | 0.0% | 0/2 |
| resample_8k | 2 | 0.9976 | -0.0008 | 9.71 | -0.66 | 0.0% | 0/2 |
| lowpass_4k | 2 | 0.9973 | -0.0010 | 9.71 | -0.66 | 0.0% | 0/2 |
| lowpass_3k4 | 2 | 0.9976 | -0.0008 | 9.05 | -1.31 | 0.0% | 0/2 |
| telephone_band | 2 | 0.9990 | +0.0005 | 9.05 | -1.31 | 0.0% | 0/2 |
| mu_law | 2 | 0.9985 | +0.0001 | 10.36 | +0.00 | 0.0% | 0/2 |
| telephone_chain | 2 | 0.9990 | +0.0006 | 9.05 | -1.31 | 0.0% | 0/2 |
| gain_minus_20db* | 2 | 0.2495 | -0.7505 | 0.67 | -9.70 | 0.0% | 1/2 |
| gain_plus_6db | 2 | 0.9999 | +0.0015 | 10.96 | +0.60 | 0.0% | 0/2 |
| clipping | 2 | 0.9985 | +0.0001 | 10.36 | +0.00 | 0.0% | 0/2 |
| reverb_300ms | 2 | 1.0000 | +0.0016 | 10.36 | +0.00 | 0.0% | 0/2 |
| packet_loss_2pct | 2 | 0.9974 | -0.0010 | 10.31 | -0.05 | 0.0% | 0/2 |
| packet_loss_5pct | 2 | 0.9994 | +0.0010 | 9.71 | -0.66 | 0.0% | 0/2 |

\* Note on `gain_minus_20db`: The reported AASIST and ΔAASIST values represent the single valid call (SP_2). SP_1 had valid AASIST windows = 0, AASIST = null, authenticity evidence = missing, and risk state = insufficient_evidence; null was strictly preserved and excluded from arithmetic averaging.

## 6. RTP Robustness

| Condition | Generated | Dropped | Transmitted | Received | Gaps | Loss % |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| clean | 1200 | 0 | 1200 | 1190 | 0 | 0.0% |
| noise_white_20db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| noise_white_10db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| noise_white_5db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| noise_white_0db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| noise_pink_10db | 1200 | 0 | 1200 | 1189 | 0 | 0.0% |
| noise_babble_10db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| resample_8k | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| lowpass_4k | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| lowpass_3k4 | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| telephone_band | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| mu_law | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| telephone_chain | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| gain_minus_20db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| gain_plus_6db | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| clipping | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| reverb_300ms | 1200 | 0 | 1200 | 1192 | 0 | 0.0% |
| packet_loss_2pct | 1200 | 24 | 1176 | 1168 | 0 | 2.0% |
| packet_loss_5pct | 1200 | 67 | 1133 | 1126 | 0 | 5.6% |
| **TOTAL** | **22,800** | **91** | **22,709** | **22,553** | **0** | — |

- Total packets generated = 22,800
- Total intentionally dropped = 91 (controlled UAC injection)
- Total packets transmitted = 22,709
- Total packets received = 22,553
- Total invalid packets = 0
- Total sequence gaps = 0

## 7. Latency

| Condition | First ML | Policy Latency | Total Duration |
| :--- | :---: | :---: | :---: |
| clean | 0.403s | 0.403s | 7.322s |
| noise_white_20db | 0.378s | 0.378s | 7.311s |
| noise_white_10db | 0.382s | 0.382s | 7.315s |
| noise_white_5db | 0.381s | 0.381s | 7.316s |
| noise_white_0db | 0.382s | 0.382s | 7.318s |
| noise_pink_10db | 0.395s | 0.395s | 7.310s |
| noise_babble_10db | 0.380s | 0.380s | 7.311s |
| resample_8k | 0.385s | 0.385s | 7.320s |
| lowpass_4k | 0.391s | 0.391s | 7.324s |
| lowpass_3k4 | 0.399s | 0.399s | 7.324s |
| telephone_band | 0.396s | 0.396s | 7.322s |
| mu_law | 0.387s | 0.387s | 7.339s |
| telephone_chain | 0.387s | 0.387s | 7.316s |
| gain_minus_20db | 0.391s | 0.391s | 7.321s |
| gain_plus_6db | 0.381s | 0.381s | 7.312s |
| clipping | 0.391s | 0.391s | 7.323s |
| reverb_300ms | 0.383s | 0.383s | 7.308s |
| packet_loss_2pct | 0.386s | 0.386s | 7.318s |
| packet_loss_5pct | 0.411s | 0.411s | 7.321s |

## 8. Decision Changes and Policy Interpretation

Pipeline decision flow strictly distinguishes three stages:
$$\text{AASIST raw output} \to \text{composite risk} \to \text{security policy decision}$$

In this benchmark, every call resulted in a policy decision of `ALLOW`. This occurred because the Risk Engine's uncorroborated corroboration policy intentionally caps isolated authenticity evidence below the suspicious threshold (score 38 < 40) when identity and context corroboration are absent (un-enrolled test caller with benign speech content).

Zero policy decision flips demonstrate decision stability under the tested transmission impairments in this uncorroborated benchmark configuration; they do not establish spoof-classification accuracy.

## 9. Critical Conditions

### Condition: `gain_minus_20db`
- **Bona-fide**: Mean AASIST = 0.4254 (BF_1: 0.0275, BF_2: 0.8233), ΔAASIST = -0.5741, Mean Risk = 5.28, Flips = 0
- **Spoof**: 
  - SP_1: valid AASIST windows = 0, AASIST = null, authenticity evidence = missing, risk state = insufficient_evidence (null preserved, not zero)
  - SP_2: valid AASIST windows = 2, AASIST = 0.2495, ΔAASIST = -0.7505, Mean Risk = 1.33, Final Risk = 12, risk state = insufficient_evidence
  - Spoof aggregate (valid calls only): Mean AASIST = 0.2495, ΔAASIST = -0.7505, Mean Risk = 0.67, Flips = 0
- **RTP Telemetry**: Generated = 1200, Dropped = 0, Gaps = 0

### Condition: `noise_white_0db`
- **Bona-fide**: Mean AASIST = 1.0, ΔAASIST = +0.0005, Mean Risk = 11.57, Flips = 0
- **Spoof**: Mean AASIST = 0.9999, ΔAASIST = +0.0015, Mean Risk = 11.57, Flips = 0
- **RTP Telemetry**: Generated = 1200, Dropped = 0, Gaps = 0

### Condition: `telephone_chain`
- **Bona-fide**: Mean AASIST = 0.999, ΔAASIST = -0.0004, Mean Risk = 10.36, Flips = 0
- **Spoof**: Mean AASIST = 0.999, ΔAASIST = +0.0006, Mean Risk = 9.05, Flips = 0
- **RTP Telemetry**: Generated = 1200, Dropped = 0, Gaps = 0

### Condition: `reverb_300ms`
- **Bona-fide**: Mean AASIST = 1.0, ΔAASIST = +0.0005, Mean Risk = 10.96, Flips = 0
- **Spoof**: Mean AASIST = 1.0, ΔAASIST = +0.0016, Mean Risk = 10.36, Flips = 0
- **RTP Telemetry**: Generated = 1200, Dropped = 0, Gaps = 0

### Condition: `packet_loss_5pct`
- **Bona-fide**: Mean AASIST = 0.9996, ΔAASIST = +0.0002, Mean Risk = 9.71, Flips = 0
- **Spoof**: Mean AASIST = 0.9994, ΔAASIST = +0.0010, Mean Risk = 9.71, Flips = 0
- **RTP Telemetry**: Generated = 1200, Dropped = 67, Gaps = 0

## 10. Comparison With Phase 1.8

> [!NOTE]
> The earlier Phase 1.8 results are **HISTORICAL OFFLINE/DIRECT PIPELINE** measurements.
> The current Phase 5.3 results are **PHASE 5.3 LIVE VOIP** measurements through Asterisk, SIP/RTP, and WebSocket pipeline.
> These datasets are fundamentally distinct and must not be merged.

| Metric | Phase 1.8 (HISTORICAL OFFLINE/DIRECT) | Phase 5.3-B (PHASE 5.3 LIVE VOIP) |
| :--- | :---: | :---: |
| Pipeline Architecture | Direct Python In-Memory | Live Asterisk + Gateway + WS |
| Transport / Codec | None (Raw Audio) | SIP/TCP + RTP/PCMU (G.711u) |
| Matrix Size | 400 offline runs | 76 live calls |
| Valid AASIST Evidence Rate | 100% | 98.7% |

## 11. Test Results
- harness tests: 9/9 PASSED (`test_voip_robustness.py`)
- full telephony tests: 64/64 PASSED (`services/telephony/tests/`)
- diff check: clean (`git diff --check` passed)
- frozen-core audit: frozen core unmodified (`services/api/app/*`, `audio_gateway.py` untouched)
- Asterisk cleanup: 0 active channels, 0 active bridges, 0 orphaned resources

## 12. Scientific Limitations
1. **Sample Size**: 76 calls across 4 canonical audio sources provides controlled sensitivity testing, not universal statistical proof across diverse demographic cohorts.
2. **Synthetic Approximations**: Controlled noise, filtering, and companding approximate channel conditions but do not capture live GSM/cellular fading, dynamic codecs (Opus/AMR), or acoustic environments.
3. **Vocoder Generalization**: The spoof corpus tests WaveFake vocoders (ParallelWaveGAN and WaveGlow). Generalization to novel diffusion or zero-shot voice cloning architectures cannot be claimed.
4. **No Claim of Perfection**: Antispoofing detection is probabilistic; no claims of 100% accuracy or universal robustness are made.
5. **Class-Discriminative Scope**: The benchmark does not measure class-discriminative spoof detection accuracy (AUC/EER), as bona-fide and spoof test samples yielded similarly high AASIST scores; it validates pipeline execution and robustness against transmission impairments.

## 13. Phase 5.3-B Classification

**Classification**: `VALID EXPANDED VOIP ROBUSTNESS EVIDENCE — WITH MODEL-DISCRIMINATION LIMITATION`

The evidence supports:
- live SIP/RTP pipeline robustness
- deterministic degradation testing
- RTP accounting
- ML evidence availability
- latency
- policy stability
- cleanup/resource correctness

It does NOT establish universal or class-discriminative spoof detection accuracy.

## 14. Recommendation

State minimum next technical action based strictly on measured evidence:
1. Present the Phase 5.3-B Expanded VoIP Robustness Evaluation report for user review.
2. Maintain frozen production core intact.
3. Await explicit user authorization before tagging or advancing to Phase 5.4.
