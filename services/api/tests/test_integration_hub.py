"""
Test Integration Hub Endpoints — System Capabilities, Integration Status & Webhooks
"""

import pytest
from httpx import AsyncClient, ASGITransport
from main import app


@pytest.mark.asyncio
async def test_get_capabilities():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/system/capabilities")
        assert res.status_code == 200
        data = res.json()
        assert data["telephony"]["cellular_metadata"] == "available"
        assert data["telephony"]["cellular_audio"] == "unsupported"
        assert data["telephony"]["voip_media"] == "available"
        assert data["api"]["rest"] == "available"
        assert data["api"]["websocket"] == "available"


@pytest.mark.asyncio
async def test_get_privacy():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/system/privacy")
        assert res.status_code == 200
        data = res.json()
        assert data["raw_audio_retained"] is False
        assert data["features_logged_only"] is True


@pytest.mark.asyncio
async def test_get_policy():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/system/policy")
        assert res.status_code == 200
        data = res.json()
        assert "thresholds" in data
        assert "weights" in data


@pytest.mark.asyncio
async def test_get_integration_status():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/system/integration/status")
        assert res.status_code == 200
        data = res.json()
        assert data["overall_status"] == "OPERATIONAL"
        assert data["subsystems"]["rest_api"]["status"] == "AVAILABLE"
        assert data["subsystems"]["websocket_stream"]["status"] == "AVAILABLE"
        assert data["subsystems"]["grpc_service"]["status"] == "INTEGRATION_READY"
        assert data["telephony_gateway"]["asterisk_sip_ari"] == "AVAILABLE"


@pytest.mark.asyncio
async def test_test_webhook():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post(
            "/system/webhooks/test",
            json={
                "event_type": "risk_update",
                "session_id": "test-session-123",
                "risk_score": 85,
                "risk_state": "CRITICAL",
                "decision": "BLOCK",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["event"] == "risk_update"
        assert "hmac_sha256_signature" in data
        assert data["payload"]["decision"] == "BLOCK"
