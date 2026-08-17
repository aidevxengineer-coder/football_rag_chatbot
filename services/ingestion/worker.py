import logging
import time

from prometheus_client import Counter, Histogram

from services.ingestion.jobs import get_job_store
from services.ingestion.processor import process_file_bytes
from services.ingestion.project_client import update_file_status
from services.ingestion.storage import fetch_object_bytes
from services.ingestion.errors import FootballRelevanceError

logger = logging.getLogger(__name__)

# One job = one uploaded file being chunked/embedded/indexed. "status"
# distinguishes normal failures (file rejected as off-topic) from
# unexpected ones (a bug/outage), since those call for different alerts.
INGESTION_JOBS_TOTAL = Counter(
    "futbot_ingestion_jobs_total",
    "Total ingestion jobs processed, by outcome.",
    ["status"],
)
INGESTION_JOB_DURATION_SECONDS = Histogram(
    "futbot_ingestion_job_duration_seconds",
    "Time to process one ingestion job (fetch + chunk + embed + index).",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)


def run_project_file_job(job_id: str) -> None:
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        return

    scope = getattr(job, "scope", "project") or "project"
    store.mark_processing(job_id)
    update_file_status(
        project_id=job.project_id,
        file_id=job.file_id,
        status="processing",
        scope=scope,
    )

    t0 = time.monotonic()
    try:
        file_bytes = fetch_object_bytes(job.storage_key)
        result = process_file_bytes(
            project_id=job.project_id,
            file_id=job.file_id,
            filename=job.filename,
            file_bytes=file_bytes,
        )
        store.mark_completed(job_id, chunks_indexed=result["chunks_indexed"])
        update_file_status(
            project_id=job.project_id,
            file_id=job.file_id,
            status="ingested",
            scope=scope,
            chunks_indexed=result["chunks_indexed"],
            tokens_indexed=result.get("tokens_indexed", 0),
        )
        INGESTION_JOBS_TOTAL.labels(status="completed").inc()
    except FootballRelevanceError as exc:
        store.mark_failed(job_id, str(exc))
        update_file_status(
            project_id=job.project_id,
            file_id=job.file_id,
            status="failed",
            error_message=str(exc),
            scope=scope,
        )
        INGESTION_JOBS_TOTAL.labels(status="rejected").inc()
    except Exception as exc:
        logger.exception("Ingest job %s failed", job_id)
        store.mark_failed(job_id, str(exc))
        update_file_status(
            project_id=job.project_id,
            file_id=job.file_id,
            status="failed",
            error_message=str(exc),
            scope=scope,
        )
        INGESTION_JOBS_TOTAL.labels(status="error").inc()
    finally:
        INGESTION_JOB_DURATION_SECONDS.observe(time.monotonic() - t0)
