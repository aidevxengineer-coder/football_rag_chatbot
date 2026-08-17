import pytest
from httpx import ASGITransport, AsyncClient

from services.gateway.app import create_app


@pytest.fixture
def gateway_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("ANON_MESSAGE_LIMIT", "10")
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_list_chats_requires_login_at_gateway(gateway_client, monkeypatch):
    import fakeredis.aioredis
    from services.gateway import middleware as gw_mw

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(gw_mw, "_redis", fake)

    async with gateway_client as client:
        response = await client.get("/chats")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_gateway_root_is_api_only(gateway_client):
    async with gateway_client as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["service"] == "gateway"
    assert response.json()["docs"] == "/docs"


@pytest.mark.asyncio
async def test_gateway_does_not_serve_legacy_static_assets(gateway_client):
    async with gateway_client as client:
        response = await client.get("/static/app.js")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
