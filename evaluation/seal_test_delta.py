#!/usr/bin/env python3
"""
Phase 0, condition 4 — seal TEST δ and make evaluation/results append-only.

Sealing means three concrete things:

  1. The δ archive and every file in the evaluated manifest are hashed, so any
     later change is detectable.
  2. A seal record is written stating provenance, licence, composition, and the
     rule that δ may be opened exactly once more (after training completes).
  3. Existing evaluation results are made read-only. The parent directory stays
     writable so *new* runs can be added — append-only, not frozen-shut.

This does not encrypt or hide δ. It makes silent modification detectable and
makes accidental overwriting of the frozen baseline impossible.

    python evaluation/seal_test_delta.py --delta data/external/InTheWild \
        --results evaluation/results --tag inthewild_delta_baseline
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import stat
import time
from pathlib import Path


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--delta", required=True)
    ap.add_argument("--results", default="evaluation/results")
    ap.add_argument("--tag", default="inthewild_delta_baseline")
    args = ap.parse_args()

    delta_root = Path(args.delta)
    results = Path(args.results)
    run_dir = results / args.tag

    print("hashing δ archive …", flush=True)
    archive = delta_root / "release_in_the_wild.zip"
    archive_sha = sha256_of(archive) if archive.is_file() else None

    manifest = run_dir / "manifest_test.csv"
    rows = list(csv.DictReader(open(manifest))) if manifest.is_file() else []
    print(f"hashing {len(rows)} evaluated δ files …", flush=True)
    file_hashes = {}
    for i, r in enumerate(rows, 1):
        p = Path(r["audio_path"])
        if p.is_file():
            file_hashes[r["audio_path"]] = sha256_of(p)
        if i % 500 == 0:
            print(f"  {i}/{len(rows)}", flush=True)

    # A single digest over the sorted per-file hashes: one value that pins the
    # whole evaluated set.
    joined = "\n".join(f"{k} {v}" for k, v in sorted(file_hashes.items()))
    manifest_digest = hashlib.sha256(joined.encode()).hexdigest()

    seal = {
        "sealed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "role": "TEST δ — sealed unseen-domain corpus",
        "dataset": {
            "name": "In-the-Wild",
            "paper": "Müller et al., Does Audio Deepfake Detection Generalize?, "
                     "Interspeech 2022 (arXiv:2203.16263)",
            "source": "https://huggingface.co/datasets/mueller91/In-The-Wild",
            "licence": "CC-BY-SA-4.0 (verified from the dataset card frontmatter)",
            "gated": False,
        },
        "archive": {"path": str(archive), "sha256": archive_sha,
                    "bytes": archive.stat().st_size if archive.is_file() else None},
        "evaluated_manifest": {
            "path": str(manifest),
            "n_files": len(rows),
            "manifest_digest_sha256": manifest_digest,
        },
        "rules": [
            "δ must not be used for training.",
            "δ must not be used for validation, threshold selection, calibration, "
            "hyperparameter search, early stopping, or checkpoint selection.",
            "δ may be opened exactly once more: after a candidate model has "
            "already passed its acceptance criteria on α, β and γ.",
            "Any change to the files above invalidates the seal and the baseline.",
        ],
        "baseline_measured_with": "frozen AASIST-L, cascade disabled, prep-v1",
    }
    seal_path = results / "TEST_DELTA_SEAL.json"
    seal_path.write_text(json.dumps(seal, indent=2))
    print(f"seal written → {seal_path}")

    # ── Append-only: existing results read-only, parent stays writable ───────
    changed = 0
    for root, dirs, files in os.walk(results):
        for f in files:
            p = Path(root) / f
            mode = p.stat().st_mode
            new = stat.S_IMODE(mode) & ~0o222          # strip all write bits
            if new != stat.S_IMODE(mode):
                p.chmod(new); changed += 1
    for d in sorted([p for p in results.iterdir() if p.is_dir()]):
        d.chmod(0o555)
    results.chmod(0o755)                                # new runs may still be added
    print(f"append-only applied: {changed} files made read-only, "
          f"{len(list(results.iterdir()))} entries; parent remains writable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
