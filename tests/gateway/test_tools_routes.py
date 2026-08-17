import pytest
from httpx import ASGITransport, AsyncClient

from services.gateway.app import create_app


@pytest.fixture
def gateway_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_tools_execute_stays_501_on_gateway(gateway_client):
    async with gateway_client as client:
        response = await client.post(
            "/tools/execute",
            json={"tool": "web_search", "arguments": {"query": "x"}},
        )
    assert response.status_code == 501


@pytest.mark.asyncio
async def test_live_events_route_is_publicly_proxied(gateway_client, mocker):
    class FakeResponse:
        status_code = 200
        content = b'{"data":{"events":[],"provider":null,"updated_at":"2026-07-19T00:00:00Z","message":"No live matches"}}'
        headers = {"content-type": "application/json"}

        async def aclose(self):
            return None

    request = mocker.AsyncMock(return_value=FakeResponse())
    mocker.patch(
        "services.gateway.app._get_client",
        return_value=mocker.Mock(request=request),
    )

    async with gateway_client as client:
        response = await client.get("/tools/live-events")

    assert response.status_code == 200
    assert response.json()["data"]["events"] == []
    assert request.await_args.args[0] == "GET"
    assert request.await_args.args[1].endswith("/tools/live-events")
