import pytest


@pytest.mark.asyncio
async def test_post_user_message_triggers_rag(chat_client, mocker):
    mocker.patch(
        "services.chat.pipeline_runner.run_pipeline_sync",
        return_value={
            "reply": "They won 2-1.",
            "snapshot": "{}",
            "snapshot_turn_count": 0,
            "citations": [],
            "run_id": 7,
            "classification": "KNOWLEDGE",
            "reached_max_retries": False,
        },
    )

    create = await chat_client.post("/chats", json={"title": "RAG test"})
    chat_id = create.json()["data"]["id"]

    response = await chat_client.post(
        f"/chats/{chat_id}/messages",
        json={"role": "user", "content": "Score?", "web_search_enabled": True},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["message"]["role"] == "user"
    assert body["assistant_message"] is None
    assert body["tool_notice_code"] == "PIPELINE_RUNNING"

    messages = await chat_client.get(f"/chats/{chat_id}/messages")
    assert messages.status_code == 200
    stored = messages.json()["data"]["messages"]
    assert any(m["role"] == "assistant" and m["content"] == "They won 2-1." for m in stored)
