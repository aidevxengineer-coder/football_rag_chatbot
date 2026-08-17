import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from futbot_common.exception_handlers import register_exception_handlers


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("trace this failure")

    return TestClient(app, raise_server_exceptions=False)


def test_dev_mode_returns_structured_internal_error(client):
    response = client.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "trace this failure" in body["error"]["message"]
    assert body["error"]["details"][0]["type"] == "RuntimeError"
    assert any("trace this failure" in line for line in body["error"]["details"][0]["traceback"])
