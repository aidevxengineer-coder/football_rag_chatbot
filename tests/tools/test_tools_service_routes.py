import pytest
from httpx import ASGITransport, AsyncClient

from services.tools.app import create_app
from services.tools.registry import register_tool, reset_registry_for_tests
from services.tools.builtins.web_search import register_web_search
from services.tools.schemas import ToolDefinition


@pytest.fixture
def tools_client():
    reset_registry_for_tests()
    register_web_search()
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_list_tools(tools_client):
    async with tools_client as client:
        response = await client.get("/tools")
    assert response.status_code == 200
    names = [t["name"] for t in response.json()["data"]]
    assert "web_search" in names
    assert "markdown_to_pdf" not in names


@pytest.mark.asyncio
async def test_execute_web_search_mocked(tools_client, mocker):
    mocker.patch(
        "services.tools.builtins.web_search.search_web",
        return_value={"snippets": ["a"], "sources": [], "provider": "tavily"},
    )
    async with tools_client as client:
        response = await client.post(
            "/tools/execute",
            json={"tool": "web_search", "arguments": {"query": "test"}, "web_search_enabled": True},
        )
    assert response.status_code == 200
    assert response.json()["data"]["success"] is True


@pytest.mark.asyncio
async def test_live_events_normalizes_livescore_data(tools_client):
    class FakeLiveScores:
        name = "mcp:livescore:get_live_scores"

        def definition(self):
            return ToolDefinition(name=self.name, description="Live scores", source="mcp")

        def execute(self, arguments):
            return {
                "response": {
                    "live": [
                        {
                            "id": "match-1",
                            "league": {"name": "Premier League"},
                            "home": {"name": "Arsenal"},
                            "away": {"name": "Liverpool"},
                            "status": {
                                "name": "Second half",
                                "scoreStr": "2 - 1",
                                "liveTime": {"short": "67'"},
                            },
                        }
                    ]
                }
            }

    register_tool(FakeLiveScores())
    async with tools_client as client:
        response = await client.get("/tools/live-events")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider"] == "LiveScore MCP"
    assert data["events"] == [
        {
            "id": "match-1",
            "competition": "Premier League",
            "home_team": "Arsenal",
            "away_team": "Liverpool",
            "home_score": 2,
            "away_score": 1,
            "status": "Second half",
            "minute": "67'",
            "started_at": None,
        }
    ]


@pytest.mark.asyncio
async def test_live_events_gracefully_handles_no_provider(tools_client):
    async with tools_client as client:
        response = await client.get("/tools/live-events")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["events"] == []
    assert data["provider"] is None
    assert data["message"] == "No live-score provider is configured."
