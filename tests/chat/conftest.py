import pytest
from httpx import ASGITransport, AsyncClient

from services.chat.app import create_app
from services.chat.db import init_db


@pytest.fixture
async def chat_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setattr(
        "services.chat.pipeline_runner.run_pipeline_sync",
        lambda **kwargs: {
            "reply": "Pipeline complete.",
            "snapshot": "{}",
            "snapshot_turn_count": 0,
            "citations": [],
            "run_id": None,
        },
    )
    await init_db("sqlite+aiosqlite:///:memory:")
    app = create_app(with_lifespan=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def auth_headers(user_id: str = "user-1") -> dict[str, str]:
    return {"X-User-ID": user_id}
