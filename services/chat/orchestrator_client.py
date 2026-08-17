import httpx

from services.chat.config import settings


def run_pipeline_sync(
    *,
    session_id: str,
    query: str,
    context_messages: list[dict[str, str]],
    snapshot: str,
    snapshot_turn_count: int,
    project_id: str | None,
    user_id: str | None = None,
    web_search_enabled: bool = False,
) -> dict:
    url = f"{settings.orchestrator_service_url.rstrip('/')}/pipeline/run"
    response = httpx.post(
        url,
        json={
            "session_id": session_id,
            "query": query,
            "context_messages": context_messages,
            "snapshot": snapshot,
            "snapshot_turn_count": snapshot_turn_count,
            "project_id": project_id,
            "user_id": user_id,
            "web_search_enabled": web_search_enabled,
        },
        timeout=300.0,
    )
    response.raise_for_status()
    return response.json()["data"]


def export_markdown_to_pdf(markdown: str, *, title: str) -> bytes:
    import base64

    url = f"{settings.tools_service_url.rstrip('/')}/tools/execute"
    response = httpx.post(
        url,
        json={
            "tool": "markdown_to_pdf",
            "arguments": {"markdown": markdown, "title": title},
            "web_search_enabled": False,
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()["data"]
    if not data.get("success"):
        raise RuntimeError(data.get("error_message") or "PDF export failed")
    pdf_b64 = data["result"]["pdf_base64"]
    return base64.b64decode(pdf_b64)
