from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from futbot_common.responses import DataResponse
from services.ingestion.jobs import JobStore, get_job_store
from services.ingestion.schemas import CreateJobRequest, JobResponse
from services.ingestion.worker import run_project_file_job

router = APIRouter(tags=["ingest"])


def run_job(job_id: str, background_tasks: BackgroundTasks) -> None:
    background_tasks.add_task(run_project_file_job, job_id)


@router.post("/ingest/jobs", response_model=DataResponse[JobResponse], status_code=202)
def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    store: JobStore = Depends(get_job_store),
) -> DataResponse[JobResponse]:
    job = store.create(
        project_id=body.project_id,
        file_id=body.file_id,
        filename=body.filename,
        storage_key=body.storage_key,
        content_hash=body.content_hash,
        scope=body.scope,
    )
    run_job(job.id, background_tasks)
    return DataResponse(
        data=JobResponse(
            id=job.id,
            project_id=job.project_id,
            file_id=job.file_id,
            filename=job.filename,
            status=job.status,
            chunks_indexed=job.chunks_indexed,
            error_message=job.error_message,
        )
    )


@router.get("/ingest/jobs/{job_id}", response_model=DataResponse[JobResponse])
def get_job(job_id: str, store: JobStore = Depends(get_job_store)) -> DataResponse[JobResponse]:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return DataResponse(
        data=JobResponse(
            id=job.id,
            project_id=job.project_id,
            file_id=job.file_id,
            filename=job.filename,
            status=job.status,
            chunks_indexed=job.chunks_indexed,
            error_message=job.error_message,
        )
    )
