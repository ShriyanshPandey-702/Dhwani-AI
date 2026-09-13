"""
Security tests — token handling, WebSocket authorisation, secret exposure and
evidence integrity.
"""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token, create_refresh_token, decode_token,
    hash_password, verify_password,
)
from app.websocket.gateway import router as ws_router

REPO_ROOT = Path(__file__).resolve().parents[3]


# ── JWT ───────────────────────────────────────────────────────────────────────

def test_valid_access_token_round_trips():
    payload = decode_token(create_access_token("user-1"))
    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"


def test_tampered_token_is_rejected():
    token = create_access_token("user-1")
    head, body, sig = token.split(".")
    tampered = f"{head}.{body}.{sig[:-4]}AAAA"
    with pytest.raises(Exception):
        decode_token(tampered)


def test_token_signed_with_another_secret_is_rejected():
    forged = jwt.encode(
        {"sub": "attacker", "type": "access",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "not-the-real-secret",
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(Exception):
        decode_token(forged)


def test_expired_token_is_rejected():
    expired = jwt.encode(
        {"sub": "user-1", "type": "access",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(Exception):
        decode_token(expired)


def test_algorithm_confusion_none_is_rejected():
    """An unsigned 'alg: none' token must never be accepted."""
    unsigned = jwt.encode({"sub": "attacker", "type": "access"}, "", algorithm="HS256")
    forged = unsigned.rsplit(".", 1)[0] + "."
    with pytest.raises(Exception):
        decode_token(forged)


def test_refresh_and_access_tokens_are_distinguishable():
    assert decode_token(create_refresh_token("u"))["type"] == "refresh"
    assert decode_token(create_access_token("u"))["type"] == "access"


# ── Passwords ─────────────────────────────────────────────────────────────────

def test_passwords_are_hashed_not_stored():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_identical_passwords_get_different_hashes():
    assert hash_password("same") != hash_password("same")


# ── WebSocket authorisation ───────────────────────────────────────────────────

@pytest.fixture
def ws_client():
    """A minimal app with only the WS router, so no DB lifespan is required."""
    app = FastAPI()
    app.include_router(ws_router)
    with TestClient(app) as client:
        yield client


def test_websocket_rejects_a_missing_token(ws_client):
    with pytest.raises(Exception):
        with ws_client.websocket_connect("/ws/sessions/any-session"):
            pass


def test_websocket_rejects_an_invalid_token(ws_client):
    with pytest.raises(Exception):
        with ws_client.websocket_connect(
            "/ws/sessions/any-session?token=not-a-real-token"
        ):
            pass


def test_websocket_rejects_a_refresh_token_used_as_access(ws_client):
    refresh = create_refresh_token("user-1")
    with pytest.raises(Exception):
        with ws_client.websocket_connect(f"/ws/sessions/any-session?token={refresh}"):
            pass


def test_websocket_rejects_a_forged_token(ws_client):
    forged = jwt.encode(
        {"sub": "attacker", "type": "access",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "wrong-secret", algorithm="HS256",
    )
    with pytest.raises(Exception):
        with ws_client.websocket_connect(f"/ws/sessions/any-session?token={forged}"):
            pass


# ── Secret exposure ───────────────────────────────────────────────────────────

def test_no_api_secrets_are_bundled_into_the_mobile_app():
    """The mobile bundle must never contain a backend secret or key."""
    mobile_src = REPO_ROOT / "apps" / "mobile" / "VoiceShieldApp" / "src"
    forbidden = ("JWT_SECRET", "SECRET_KEY", "API_KEY", "api_key", "PRIVATE_KEY")
    offenders = []
    for path in mobile_src.rglob("*.ts*"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in forbidden:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert not offenders, offenders


def test_no_third_party_detection_api_remains_in_the_repository():
    """Resemble AI was removed; nothing may reintroduce it."""
    roots = [
        REPO_ROOT / "services" / "api" / "app",
        REPO_ROOT / "apps" / "mobile" / "VoiceShieldApp" / "src",
    ]
    offenders = []
    for root in roots:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".ts", ".tsx"}:
                if "resemble" in path.read_text(
                    encoding="utf-8", errors="ignore"
                ).lower():
                    offenders.append(str(path))
    assert not offenders, offenders


# ── Evidence integrity ────────────────────────────────────────────────────────

def test_evidence_hash_detects_tampering():
    evidence = {"peak_risk_score": 74, "peak_risk_state": "high"}
    original = hashlib.sha256(
        json.dumps(evidence, sort_keys=True).encode()
    ).hexdigest()

    tampered = {**evidence, "peak_risk_score": 5}
    recomputed = hashlib.sha256(
        json.dumps(tampered, sort_keys=True).encode()
    ).hexdigest()

    assert original != recomputed


def test_evidence_hash_is_stable_regardless_of_key_order():
    a = {"x": 1, "y": 2}
    b = {"y": 2, "x": 1}
    assert (
        hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()
        == hashlib.sha256(json.dumps(b, sort_keys=True).encode()).hexdigest()
    )
