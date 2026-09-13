# Vendored third-party code

## AASIST (`aasist_model.py`)

Source: https://github.com/clovaai/aasist — file `models/AASIST.py`
Copyright (c) 2021-present NAVER Corp.
Licence: MIT (full text in `LICENSE.aasist`)

Paper: Jung et al., "AASIST: Audio Anti-Spoofing using Integrated
Spectro-Temporal Graph Attention Networks", ICASSP 2022.

The architecture file is vendored **unmodified** apart from this header, so the
released checkpoints load without a state-dict shim. Pretrained weights are not
redistributed in this repository; they are downloaded at setup time by
`scripts/fetch_models.py`.
