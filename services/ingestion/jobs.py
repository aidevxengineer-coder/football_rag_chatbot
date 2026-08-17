import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class IngestJob:
    id: str
    project_id: str
    file_id: str
    filename: str
    storage_key: str
    content_hash: str = ""
    scope: str = "project"
    status: str = "pending"
    chunks_indexed: int = 0
    error_message: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, IngestJob] = {}

    def create(self, **kwargs: Any) -> IngestJob:
        job = IngestJob(id=str(uuid.uuid4()), **kwargs)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> IngestJob | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs: Any) -> None:
        job = self._jobs[job_id]
        for key, value in kwargs.items():
            setattr(job, key, value)

    def mark_processing(self, job_id: str) -> None:
        self.update(job_id, status="processing")

    def mark_completed(self, job_id: str, *, chunks_indexed: int) -> None:
        self.update(job_id, status="completed", chunks_indexed=chunks_indexed)

    def mark_failed(self, job_id: str, error_message: str) -> None:
        self.update(job_id, status="failed", error_message=error_message)


_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _store
    if _store is None:
        _store = JobStore()
    return _store


def reset_job_store() -> None:
    global _store
    _store = JobStore()
