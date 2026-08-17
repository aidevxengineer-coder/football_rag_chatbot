import logging

import httpx

from services.project.config import settings

logger = logging.getLogger(__name__)


def enqueue_ingestion(
    *,
    project_id: str,
    file_id: str,
    filename: str,
    storage_key: str,
    content_hash: str = "",
    scope: str = "project",
) -> None:
    url = f"{settings.ingestion_service_url.rstrip('/')}/ingest/jobs"
    try:
        response = httpx.post(
            url,
            json={
                "project_id": project_id,
                "file_id": file_id,
                "filename": filename,
                "storage_key": storage_key,
                "content_hash": content_hash,
                "scope": scope,
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to enqueue ingestion for file %s: %s", file_id, exc)
