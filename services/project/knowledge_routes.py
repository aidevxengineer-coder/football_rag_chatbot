"""User-scoped Ball Knowledge APIs (account RAG — not league/project)."""

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from futbot_common.errors import AuthError
from futbot_common.responses import DataResponse
from services.project.db import get_db
from services.project.deps import content_hash, require_user_id
from services.project.ingestion_trigger import enqueue_ingestion
from services.project.models import UserKnowledgeFile
from services.project.schemas import (
    KnowledgeFileResponse,
    KnowledgeStatsResponse,
    UpdateKnowledgeFileStatusRequest,
)
from services.project.storage import get_storage

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


def user_kb_project_id(user_id: str) -> str:
    """Synthetic project_id used when indexing account KB chunks."""
    return f"user_kb:{user_id}"


def _file_response(row: UserKnowledgeFile) -> KnowledgeFileResponse:
    return KnowledgeFileResponse(
        id=row.id,
        filename=row.filename,
        content_hash=row.content_hash,
        status=row.status,
        error_message=row.error_message,
        chunks_indexed=row.chunks_indexed,
        tokens_indexed=row.tokens_indexed,
        created_at=row.created_at,
    )


@router.get("/stats", response_model=DataResponse[KnowledgeStatsResponse])
async def knowledge_stats(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_user_id),
):
    result = await db.execute(
        select(
            func.count(UserKnowledgeFile.id),
            func.coalesce(func.sum(UserKnowledgeFile.chunks_indexed), 0),
            func.coalesce(func.sum(UserKnowledgeFile.tokens_indexed), 0),
        ).where(UserKnowledgeFile.user_id == user_id)
    )
    files, chunks, tokens = result.one()
    return DataResponse(
        data=KnowledgeStatsResponse(
            files=int(files or 0),
            chunks=int(chunks or 0),
            memory_tokens=int(tokens or 0),
        )
    )


@router.get("/files", response_model=DataResponse[list[KnowledgeFileResponse]])
async def list_knowledge_files(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_user_id),
):
    result = await db.execute(
        select(UserKnowledgeFile)
        .where(UserKnowledgeFile.user_id == user_id)
        .order_by(UserKnowledgeFile.created_at.desc())
    )
    rows = result.scalars().all()
    return DataResponse(data=[_file_response(r) for r in rows])


@router.post("/files", response_model=DataResponse[KnowledgeFileResponse], status_code=201)
async def upload_knowledge_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(require_user_id),
):
    data = await file.read()
    if not data:
        raise AuthError("VALIDATION_ERROR", "Empty file.", 400)
    digest = content_hash(data)
    filename = file.filename or "upload"
    storage_key = f"knowledge/{user_id}/{digest}/{filename}"
    storage = get_storage()
    storage.put(storage_key, data, file.content_type or "application/octet-stream")

    row = UserKnowledgeFile(
        user_id=user_id,
        filename=filename,
        content_hash=digest,
        storage_key=storage_key,
        status="pending",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    background_tasks.add_task(
        enqueue_ingestion,
        project_id=user_kb_project_id(user_id),
        file_id=row.id,
        filename=row.filename,
        storage_key=row.storage_key,
        content_hash=row.content_hash,
        scope="user_kb",
    )
    return DataResponse(data=_file_response(row))


@router.patch(
    "/files/{file_id}/status",
    response_model=DataResponse[KnowledgeFileResponse],
)
async def update_knowledge_file_status(
    file_id: str,
    body: UpdateKnowledgeFileStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """Internal callback from ingestion worker (no user header required)."""
    result = await db.execute(
        select(UserKnowledgeFile).where(UserKnowledgeFile.id == file_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise AuthError("NOT_FOUND", "File not found.", 404)

    row.status = body.status
    row.error_message = body.error_message
    if body.chunks_indexed is not None:
        row.chunks_indexed = body.chunks_indexed
    if body.tokens_indexed is not None:
        row.tokens_indexed = body.tokens_indexed
    await db.commit()
    await db.refresh(row)
    return DataResponse(data=_file_response(row))
