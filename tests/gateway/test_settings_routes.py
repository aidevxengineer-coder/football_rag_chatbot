from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from futbot_common.jwt_tokens import create_token
from services.gateway.app import create_app
from services.gateway.config import settings


def auth_headers() -> dict[str, str]:
    token = create_token(
        subject="settings-user",
        secret=settings.jwt_secret,
        token_type="access",
        expires_delta=timedelta(minutes=5),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def env_path(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text(
        "# keep this comment\n"
        "JWT_SECRET=do-not-expose\n"
        "GROQ_API_KEY=old-groq\n"
        "TAVILY_API_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "env_file", path)
    monkeypatch.setattr(
        settings, "jwt_secret", "test-secret-at-least-thirty-two-bytes"
    )
    return path


@pytest.fixture
def gateway_client(env_path):
    app = create_app()
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_settings_require_login(gateway_client):
    async with gateway_client as client:
        response = await client.get("/settings/api-keys")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_get_returns_only_allowlisted_keys(gateway_client):
    async with gateway_client as client:
        response = await client.get("/settings/api-keys", headers=auth_headers())
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["GROQ_API_KEY"] == "old-groq"
    assert data["TAVILY_API_KEY"] == ""
    assert data["SERPER_API_KEY"] == ""
    assert "JWT_SECRET" not in data
    assert len(data) == 6


@pytest.mark.asyncio
async def test_put_merges_without_overwriting_other_env_values(gateway_client, env_path):
    async with gateway_client as client:
        response = await client.put(
            "/settings/api-keys",
            headers=auth_headers(),
            json={
                "GROQ_API_KEY": "new-groq",
                "SERPER_API_KEY": "serper-secret",
            },
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["GROQ_API_KEY"] == "new-groq"
    assert data["SERPER_API_KEY"] == "serper-secret"

    content = env_path.read_text(encoding="utf-8")
    assert "# keep this comment" in content
    assert "JWT_SECRET=do-not-expose" in content
    assert "GROQ_API_KEY=new-groq" in content
    assert "SERPER_API_KEY=serper-secret" in content


@pytest.mark.asyncio
async def test_put_rejects_unknown_or_multiline_values(gateway_client):
    async with gateway_client as client:
        unknown = await client.put(
            "/settings/api-keys",
            headers=auth_headers(),
            json={"JWT_SECRET": "nope"},
        )
        multiline = await client.put(
            "/settings/api-keys",
            headers=auth_headers(),
            json={"GROQ_API_KEY": "first\nINJECTED=value"},
        )
    assert unknown.status_code == 422
    assert multiline.status_code == 422
