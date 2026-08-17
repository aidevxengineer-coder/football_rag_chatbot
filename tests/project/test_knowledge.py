import pytest


@pytest.mark.asyncio
async def test_knowledge_requires_auth(project_client):
    response = await project_client.get("/knowledge/stats")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_knowledge_stats_empty(project_client):
    headers = {"X-User-ID": "kb-user"}
    response = await project_client.get("/knowledge/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"chunks": 0, "files": 0, "memory_tokens": 0}


@pytest.mark.asyncio
async def test_knowledge_upload_list_and_status(project_client, mocker):
    mock_post = mocker.patch("services.project.ingestion_trigger.httpx.post")
    mock_response = mocker.Mock()
    mock_response.raise_for_status = mocker.Mock()
    mock_post.return_value = mock_response

    headers = {"X-User-ID": "kb-user"}
    upload = await project_client.post(
        "/knowledge/files",
        files={"file": ("tactics.txt", b"press high and trap", "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 201
    body = upload.json()["data"]
    assert body["filename"] == "tactics.txt"
    assert body["status"] == "pending"
    file_id = body["id"]

    listed = await project_client.get("/knowledge/files", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    stats = await project_client.get("/knowledge/stats", headers=headers)
    assert stats.json()["data"]["files"] == 1
    assert stats.json()["data"]["chunks"] == 0

    # Ingest callback
    patch = await project_client.patch(
        f"/knowledge/files/{file_id}/status",
        json={
            "status": "ingested",
            "chunks_indexed": 12,
            "tokens_indexed": 840,
        },
    )
    assert patch.status_code == 200
    assert patch.json()["data"]["status"] == "ingested"
    assert patch.json()["data"]["chunks_indexed"] == 12

    stats2 = await project_client.get("/knowledge/stats", headers=headers)
    assert stats2.json()["data"] == {
        "chunks": 12,
        "files": 1,
        "memory_tokens": 840,
    }

    mock_post.assert_called_once()
    payload = mock_post.call_args.kwargs["json"]
    assert payload["scope"] == "user_kb"
    assert payload["project_id"] == "user_kb:kb-user"


@pytest.mark.asyncio
async def test_knowledge_isolated_per_user(project_client, mocker):
    mocker.patch(
        "services.project.ingestion_trigger.httpx.post",
        return_value=mocker.Mock(raise_for_status=mocker.Mock()),
    )
    await project_client.post(
        "/knowledge/files",
        files={"file": ("a.txt", b"alpha", "text/plain")},
        headers={"X-User-ID": "user-a"},
    )
    listed_b = await project_client.get(
        "/knowledge/files", headers={"X-User-ID": "user-b"}
    )
    assert listed_b.json()["data"] == []
