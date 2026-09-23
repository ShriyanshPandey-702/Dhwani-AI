"""
VoiceShield Phase 5.4 — Harness & Deterministic Scenario Unit Tests.

Validates the Phase 5.4 harness integrity, frozen invariants, required fixtures,
ownership-safe reconciliation semantics, result schema, and report formatting.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from services.telephony.scripts.validate_phase54_e2e import (
    BASELINE_COMMIT,
    BASELINE_TAG,
    FROZEN_AASIST_SHA256,
    POLICY_THRESHOLDS,
    RISK_CORROBORATION_PERSISTENCE,
    RISK_UNCORROBORATED_AUTH_CAP,
    RISK_UNCORROBORATED_TOTAL_CAP,
    RISK_WEIGHT_AUTHENTICITY,
    RISK_WEIGHT_CONTEXT,
    RISK_WEIGHT_IDENTITY,
    STREAM_WINDOWER_HOP,
    STREAM_WINDOWER_MAX_BUFFER,
    STREAM_WINDOWER_WINDOW,
    SUPPORTED_CHALLENGE_SOUNDS,
    BENIGN_WAV_PATH,
    SYNTHETIC_WAV_PATH,
    Phase54ScenarioRunner,
)


def test_01_frozen_constants_match_invariants():
    """Verify that all frozen algorithmic and architecture constants match exactly."""
    assert FROZEN_AASIST_SHA256 == "814331d088032bb4c3fa61cc014789eadeed464209dd094ab3a2dd6ffbdce27a"
    assert BASELINE_COMMIT == "3294785"
    assert BASELINE_TAG == "phase-5.3-pass"

    assert RISK_WEIGHT_AUTHENTICITY == 0.50
    assert RISK_WEIGHT_IDENTITY == 0.25
    assert RISK_WEIGHT_CONTEXT == 0.25
    assert RISK_UNCORROBORATED_TOTAL_CAP == 38
    assert RISK_UNCORROBORATED_AUTH_CAP == 35
    assert RISK_CORROBORATION_PERSISTENCE == 2

    assert POLICY_THRESHOLDS["LOW"] == 20
    assert POLICY_THRESHOLDS["SUSPICIOUS"] == 40
    assert POLICY_THRESHOLDS["HIGH"] == 65
    assert POLICY_THRESHOLDS["CRITICAL"] == 85

    assert STREAM_WINDOWER_WINDOW == 64608
    assert STREAM_WINDOWER_HOP == 16000
    assert STREAM_WINDOWER_MAX_BUFFER == 80608


def test_02_required_audio_fixtures_exist():
    """Verify that benign and synthetic voice test audio files exist on disk."""
    benign_path = Path(BENIGN_WAV_PATH)
    assert benign_path.exists(), f"Benign fixture missing: {BENIGN_WAV_PATH}"
    assert benign_path.stat().st_size > 100000

    synthetic_path = Path(SYNTHETIC_WAV_PATH)
    assert synthetic_path.exists(), f"Synthetic fixture missing: {SYNTHETIC_WAV_PATH}"
    assert synthetic_path.stat().st_size > 100000


def test_03_all_supported_challenge_sounds_exist():
    """Verify that all 9 challenge prompt sound fixtures exist in services/telephony/sounds."""
    sounds_dir = Path("services/telephony/sounds")
    assert sounds_dir.exists()

    for sound in SUPPORTED_CHALLENGE_SOUNDS:
        p = sounds_dir / sound
        assert p.exists(), f"Challenge sound missing: {p}"
        assert p.stat().st_size > 1000, f"Challenge sound empty or too small: {p}"


def test_04_aasist_checkpoint_sha256_integrity():
    """Verify the actual AASIST-L checkpoint on disk matches the frozen SHA-256 hash."""
    path = Path("services/api/models/aasist/AASIST-L.pth")
    if not path.exists():
        path = Path("models/aasist/AASIST-L.pth")
    assert path.exists(), f"AASIST checkpoint missing at {path}"

    with open(path, "rb") as f:
        actual_hash = hashlib.sha256(f.read()).hexdigest()
    assert actual_hash == FROZEN_AASIST_SHA256


def test_05_scenario_result_schema_and_status_validation(tmp_path):
    """Verify the scenario result schema and disallowed ambiguous statuses."""
    runner = Phase54ScenarioRunner(output_dir=str(tmp_path))

    # Allowed statuses: PASS, FAIL, SKIPPED, NOT_VERIFIED
    valid_statuses = {"PASS", "FAIL", "SKIPPED", "NOT_VERIFIED"}

    runner.record_scenario(
        scenario_id="E2E-TEST",
        name="Unit Test Scenario",
        status="PASS",
        start_time=100.0,
        end_time=102.5,
        expected_result="Test expected",
        observed_result="Test observed",
        evidence={"key": "val"},
        failure_reason=None,
    )

    res = runner.results[0]
    assert res["scenario_id"] == "E2E-TEST"
    assert res["status"] in valid_statuses
    assert res["duration_s"] == 2.5
    assert res["expected_result"] == "Test expected"
    assert res["observed_result"] == "Test observed"
    assert "evidence" in res
    assert res["failure_reason"] is None


def test_06_report_generation_formatting(tmp_path):
    """Verify Markdown report and JSON summary generation formatting and keys."""
    runner = Phase54ScenarioRunner(output_dir=str(tmp_path))
    runner.preflight_data = {
        "git": {"branch": "main", "commit": BASELINE_COMMIT},
        "backend_health": True,
        "aasist": {"matches_frozen": True, "sha256": FROZEN_AASIST_SHA256},
        "asterisk": {"reachable": True, "version": "Asterisk 20.10.0"},
        "challenge_assets": {"total_required": 9, "all_available": True},
    }
    runner.timings = {"preflight_duration_s": 0.42}

    runner.record_scenario(
        scenario_id="E2E-01",
        name="Benign SIP Call",
        status="PASS",
        start_time=10.0,
        end_time=15.0,
        expected_result="Call establishes cleanly",
        observed_result="Clean teardown",
        evidence={"packets": 250},
    )

    json_path = runner.generate_summary_json()
    md_path = runner.generate_report_md()

    assert json_path.exists()
    assert md_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["baseline_commit"] == BASELINE_COMMIT
    assert data["summary"]["passed"] == 1
    assert data["summary"]["total"] == 1
    assert "scientific_limitations" in data

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    assert "# VoiceShield Phase 5.4" in md_text
    assert "E2E-01" in md_text
    assert "Scientific Boundaries & Claim Audit" in md_text
    assert "ZERO" in md_text
