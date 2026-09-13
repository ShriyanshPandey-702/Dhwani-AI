# Phase 1 Generalization Scorecard

All rows measured on the identical frozen manifests, cascade disabled,
`prep-v1` preprocessing. EER is each set's own EER (reference only).

| Model | ASVspoof α AUC | ASVspoof α EER | MLAAD-tiny β AUC | MLAAD-tiny β EER | WaveFake γ AUC | WaveFake γ EER | In-the-Wild δ AUC | In-the-Wild δ EER |
|---|---|---|---|---|---|---|---|---|
| frozen_aasist_l_baseline | 0.9987 | 1.07% | 0.6055 | 43.40% | 0.5970 | 41.60% | 0.6739 | 38.40% |
| aasist-l-phase1-A-seed1337 | 0.9987 | 1.07% | 0.6056 | 43.40% | 0.5972 | 41.60% | 0.6736 | 38.40% |
| aasist-l-phase1-B1-seed1337 | 0.9985 | 1.27% | 0.6179 | 42.77% | 0.6284 | 41.92% | 0.6530 | 39.07% |
| aasist-l-phase1-B2-seed1337 | 0.9992 | 1.07% | 0.6208 | 42.14% | 0.6284 | 41.12% | 0.6347 | 40.73% |
| aasist-l-phase1-C-seed1337 | 0.9992 | 1.13% | 0.6263 | 41.33% | 0.6348 | 41.44% | 0.6432 | 40.20% |

## Catastrophic-forgetting deltas vs frozen AASIST-L

| Model | Set | ΔAUC | ΔEER | ΔFAR | ΔFRR |
|---|---|---|---|---|---|
| aasist-l-phase1-A-seed1337 | ASVspoof α | +0.0000 | +0.0000 | -0.1227 | +0.0087 |
| aasist-l-phase1-A-seed1337 | MLAAD-tiny β | +0.0001 | +0.0000 | +0.0189 | -0.0357 |
| aasist-l-phase1-A-seed1337 | WaveFake γ | +0.0002 | +0.0000 | -0.0128 | +0.0160 |
| aasist-l-phase1-A-seed1337 | In-the-Wild δ | -0.0003 | +0.0000 | +0.0873 | -0.0940 |
| aasist-l-phase1-B1-seed1337 | ASVspoof α | -0.0002 | +0.0020 | -0.1207 | +0.0107 |
| aasist-l-phase1-B1-seed1337 | MLAAD-tiny β | +0.0123 | -0.0063 | +0.0126 | -0.0459 |
| aasist-l-phase1-B1-seed1337 | WaveFake γ | +0.0314 | +0.0032 | -0.0096 | +0.0192 |
| aasist-l-phase1-B1-seed1337 | In-the-Wild δ | -0.0209 | +0.0067 | +0.0940 | -0.0873 |
| aasist-l-phase1-B2-seed1337 | ASVspoof α | +0.0005 | +0.0000 | -0.1227 | +0.0087 |
| aasist-l-phase1-B2-seed1337 | MLAAD-tiny β | +0.0153 | -0.0126 | +0.0063 | -0.0510 |
| aasist-l-phase1-B2-seed1337 | WaveFake γ | +0.0314 | -0.0048 | -0.0176 | +0.0112 |
| aasist-l-phase1-B2-seed1337 | In-the-Wild δ | -0.0392 | +0.0233 | +0.1107 | -0.0707 |
| aasist-l-phase1-C-seed1337 | ASVspoof α | +0.0005 | +0.0007 | -0.1220 | +0.0087 |
| aasist-l-phase1-C-seed1337 | MLAAD-tiny β | +0.0208 | -0.0207 | +0.0000 | -0.0561 |
| aasist-l-phase1-C-seed1337 | WaveFake γ | +0.0378 | -0.0016 | -0.0144 | +0.0144 |
| aasist-l-phase1-C-seed1337 | In-the-Wild δ | -0.0307 | +0.0180 | +0.1053 | -0.0760 |
