"""Shared pytest configuration for the VoiceShield backend test suite."""

import os
import sys
from pathlib import Path

# Make `app` and `main` importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Make the repo-root `evaluation` package importable for the eval harness tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

# Deterministic secret so JWT tests do not depend on the developer's .env.
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-production")
os.environ.setdefault("APP_ENV", "test")
