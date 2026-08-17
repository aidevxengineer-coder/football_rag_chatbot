import pytest
from httpx import ASGITransport, AsyncClient

from services.auth.app import create_app


@pytest.mark.asyncio
async def test_register_requires_first_name(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "securepass123"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_returns_pending_verification(auth_client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "user@example.com",
            "password": "securepass123",
            "first_name": "Ada",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["data"]["status"] == "pending_verification"
    assert body["data"]["first_name"] == "Ada"
    assert "verification_token" in body["data"]
    assert body["data"]["verification_email_sent"] is False
    assert body["data"]["dev_verification_code"] is not None
    assert len(body["data"]["dev_verification_code"]) == 6
