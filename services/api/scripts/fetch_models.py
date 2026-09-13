#!/usr/bin/env python3
"""
Download the model checkpoints VoiceShield's real_ml pipeline needs.

Checkpoints are NOT committed to this repository. Each download is verified
against a recorded SHA-256 so a corrupted or substituted file is refused rather
than silently used for inference.

    python scripts/fetch_models.py            # fetch everything
    python scripts/fetch_models.py --list     # show what is needed / present

Licences are the upstream projects'; see docs/models.md.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "models"

AASIST_BASE = "https://github.com/clovaai/aasist/raw/main/models/weights"

ASSETS = [
    {
        "name": "AASIST",
        "purpose": "voice authenticity (heavy cascade tier)",
        "url": f"{AASIST_BASE}/AASIST.pth",
        "path": MODEL_DIR / "aasist" / "AASIST.pth",
        "sha256": "51d2d9cf0738172f61e2a384ec50a54a55363240f67c971ed55a92435bc1a1c0",
        "licence": "MIT (NAVER Corp)",
    },
    {
        "name": "AASIST-L",
        "purpose": "voice authenticity (light cascade tier, default)",
        "url": f"{AASIST_BASE}/AASIST-L.pth",
        "path": MODEL_DIR / "aasist" / "AASIST-L.pth",
        "sha256": "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a",
        "licence": "MIT (NAVER Corp)",
    },
]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(asset: dict) -> bool:
    path: Path = asset["path"]
    if path.is_file() and sha256_of(path) == asset["sha256"]:
        print(f"  ✓ {asset['name']:<12} already present and verified")
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  ↓ {asset['name']:<12} {asset['url']}")
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        urllib.request.urlretrieve(asset["url"], tmp)
    except Exception as e:
        print(f"    FAILED: {e}")
        tmp.unlink(missing_ok=True)
        return False

    actual = sha256_of(tmp)
    if actual != asset["sha256"]:
        print(f"    CHECKSUM MISMATCH\n      expected {asset['sha256']}\n      actual   {actual}")
        tmp.unlink(missing_ok=True)
        return False

    tmp.replace(path)
    size_mb = path.stat().st_size / 1e6
    print(f"    verified, {size_mb:.2f} MB, licence: {asset['licence']}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="report status only")
    args = parser.parse_args()

    if args.list:
        print("VoiceShield model checkpoints:")
        for a in ASSETS:
            present = a["path"].is_file()
            mark = "present" if present else "MISSING"
            print(f"  [{mark:>7}] {a['name']:<12} {a['purpose']}  ({a['licence']})")
        return 0

    print("Fetching VoiceShield model checkpoints...")
    ok = all([fetch(a) for a in ASSETS])
    print("\nAll checkpoints ready." if ok
          else "\nSome checkpoints are missing — real_ml will fall back and say so.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
