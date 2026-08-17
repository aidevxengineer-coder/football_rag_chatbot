import pytest


@pytest.mark.asyncio
async def test_create_anon_chat(chat_client):
    response = await chat_client.post("/chats", json={"title": "Anon"})
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["user_id"] is None
    assert data["title"] == "Anon"
    assert "context_usage" in data
    assert data["context_usage"]["limit_tokens"] == 8192


@pytest.mark.asyncio
async def test_create_chat_requires_auth_for_project(chat_client):
    response = await chat_client.post(
        "/chats", json={"title": "Proj chat", "project_id": "p1"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_authenticated_chat_crud(chat_client):
    headers = {"X-User-ID": "user-abc"}

    create = await chat_client.post(
        "/chats", json={"title": "My chat"}, headers=headers
    )
    assert create.status_code == 201
    chat_id = create.json()["data"]["id"]
    assert create.json()["data"]["user_id"] == "user-abc"

    get_resp = await chat_client.get(f"/chats/{chat_id}", headers=headers)
    assert get_resp.status_code == 200

    listed = await chat_client.get("/chats", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    deleted = await chat_client.delete(f"/chats/{chat_id}", headers=headers)
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_list_chats_requires_auth(chat_client):
    response = await chat_client.get("/chats")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_post_message_returns_context_usage(chat_client):
    create = await chat_client.post("/chats", json={"title": "T"})
    chat_id = create.json()["data"]["id"]

    response = await chat_client.post(
        f"/chats/{chat_id}/messages",
        json={"role": "user", "content": "Hello football world"},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["message"]["content"] == "Hello football world"
    assert body["context_usage"]["used_tokens"] > 0
    assert "breakdown" in body["context_usage"]


@pytest.mark.asyncio
async def test_export_markdown(chat_client):
    headers = {"X-User-ID": "user-export"}
    create = await chat_client.post(
        "/chats", json={"title": "Export me"}, headers=headers
    )
    chat_id = create.json()["data"]["id"]
    await chat_client.post(
        f"/chats/{chat_id}/messages",
        json={"role": "user", "content": "test"},
        headers=headers,
    )

    response = await chat_client.get(
        f"/chats/{chat_id}/export?format=markdown", headers=headers
    )
    assert response.status_code == 200
    assert "Export me" in response.text
    assert "**User**" in response.text


@pytest.mark.asyncio
async def test_other_user_cannot_access_private_chat(chat_client):
    create = await chat_client.post(
        "/chats", json={"title": "Private"}, headers={"X-User-ID": "owner"}
    )
    chat_id = create.json()["data"]["id"]

    response = await chat_client.get(
        f"/chats/{chat_id}", headers={"X-User-ID": "intruder"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_merge_anon_chat(chat_client):
    create = await chat_client.post("/chats", json={"title": "Anon merge"})
    chat_id = create.json()["data"]["id"]
    assert create.json()["data"]["user_id"] is None

    # Logged-in user cannot read anon chat until merge
    blocked = await chat_client.get(
        f"/chats/{chat_id}", headers={"X-User-ID": "user-merge"}
    )
    assert blocked.status_code == 403

    merged = await chat_client.post(
        "/chats/merge",
        json={"chat_id": chat_id},
        headers={"X-User-ID": "user-merge"},
    )
    assert merged.status_code == 200
    assert merged.json()["data"]["user_id"] == "user-merge"

    # Idempotent
    again = await chat_client.post(
        "/chats/merge",
        json={"chat_id": chat_id},
        headers={"X-User-ID": "user-merge"},
    )
    assert again.status_code == 200
    assert again.json()["data"]["user_id"] == "user-merge"

    ok = await chat_client.get(
        f"/chats/{chat_id}", headers={"X-User-ID": "user-merge"}
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_merge_requires_auth(chat_client):
    create = await chat_client.post("/chats", json={"title": "Anon"})
    chat_id = create.json()["data"]["id"]
    response = await chat_client.post("/chats/merge", json={"chat_id": chat_id})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_merge_rejects_other_users_chat(chat_client):
    create = await chat_client.post(
        "/chats", json={"title": "Owned"}, headers={"X-User-ID": "owner"}
    )
    chat_id = create.json()["data"]["id"]
    response = await chat_client.post(
        "/chats/merge",
        json={"chat_id": chat_id},
        headers={"X-User-ID": "intruder"},
    )
    assert response.status_code == 403
