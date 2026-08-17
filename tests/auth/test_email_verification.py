import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient) -> tuple[str, str]:
    response = await client.post(
        "/auth/register",
        json={
            "email": "ada@example.com",
            "password": "securepass123",
            "first_name": "Ada",
        },
    )
    assert response.status_code == 201
    data = response.json()["data"]
    return data["verification_token"], data["email"]


@pytest.mark.asyncio
async def test_email_verification_issues_tokens(auth_client, monkeypatch):
    monkeypatch.setattr(
        "services.auth.email_verification.secrets.randbelow",
        lambda _: 123456,
    )
    verification_token, _email = await _register(auth_client)

    verify = await auth_client.post(
        "/auth/verify-email",
        headers={"Authorization": f"Bearer {verification_token}"},
        json={"code": "123456"},
    )
    assert verify.status_code == 200
    tokens = verify.json()["data"]
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_login_password_only_after_verification(auth_client, monkeypatch):
    monkeypatch.setattr(
        "services.auth.email_verification.secrets.randbelow",
        lambda _: 654321,
    )
    verification_token, email = await _register(auth_client)
    await auth_client.post(
        "/auth/verify-email",
        headers={"Authorization": f"Bearer {verification_token}"},
        json={"code": "654321"},
    )

    login = await auth_client.post(
        "/auth/login",
        json={"email": email, "password": "securepass123"},
    )
    assert login.status_code == 200
    data = login.json()["data"]
    assert "access_token" in data
    assert "refresh_token" in data
