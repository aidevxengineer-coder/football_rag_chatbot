import httpx

from services.ingestion.config import settings


def update_file_status(
    *,
    project_id: str,
    file_id: str,
    status: str,
    error_message: str | None = None,
    scope: str = "project",
    chunks_indexed: int | None = None,
    tokens_indexed: int | None = None,
) -> None:
    base = settings.project_service_url.rstrip("/")
    if scope == "user_kb":
        url = f"{base}/knowledge/files/{file_id}/status"
        payload: dict = {"status": status, "error_message": error_message}
        if chunks_indexed is not None:
            payload["chunks_indexed"] = chunks_indexed
        if tokens_indexed is not None:
            payload["tokens_indexed"] = tokens_indexed
    else:
        url = f"{base}/projects/{project_id}/files/{file_id}/status"
        payload = {"status": status, "error_message": error_message}

    response = httpx.patch(url, json=payload, timeout=10.0)
    response.raise_for_status()
