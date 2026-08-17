import os
import time

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import Histogram

from futbot_common.responses import DataResponse
from services.retrieval.config import settings
from services.retrieval.deps import get_engine
from services.retrieval.engine import RetrievalEngine
from services.retrieval.schemas import (
    DeleteIndexResponse,
    IndexChunksRequest,
    IndexChunksResponse,
    RetrieveRequest,
    RetrieveResponse,
    RetrievedChunk,
)

router = APIRouter(tags=["retrieve"])

# How long a retrieval takes and how many chunks it returns -- generic
# HTTP metrics (from futbot_common.setup_metrics) already cover request
# latency for this route, but not "was this an empty/near-empty result",
# which is the retrieval-specific signal worth alerting on.
RETRIEVAL_DURATION_SECONDS = Histogram(
    "futbot_retrieval_duration_seconds",
    "Time spent in the retrieval engine per /retrieve call.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
RETRIEVAL_CHUNKS_RETURNED = Histogram(
    "futbot_retrieval_chunks_returned",
    "Number of chunks returned per /retrieve call.",
    buckets=(0, 1, 2, 5, 10, 20, 50),
)


def _chunk_metadata(chunk) -> dict:
    meta = {
        "source_file": chunk.source_file,
        "section_heading": chunk.section_heading,
        "chunk_type": chunk.chunk_type,
        "chunk_index": chunk.chunk_index,
        "token_count": chunk.token_count,
        "page_number": chunk.page if chunk.page is not None else -1,
    }
    if chunk.sheet_name:
        meta["sheet_name"] = chunk.sheet_name
    return meta


@router.post("/retrieve", response_model=DataResponse[RetrieveResponse])
def retrieve(
    body: RetrieveRequest,
    engine: RetrievalEngine = Depends(get_engine),
) -> DataResponse[RetrieveResponse]:
    scopes = body.project_ids
    if scopes is None and body.project_id is not None:
        scopes = [body.project_id]
    t0 = time.monotonic()
    hits = engine.retrieve(
        body.query,
        top_k=body.top_k,
        project_id=body.project_id,
        project_ids=scopes,
    )
    RETRIEVAL_DURATION_SECONDS.observe(time.monotonic() - t0)
    RETRIEVAL_CHUNKS_RETURNED.observe(len(hits))
    return DataResponse(
        data=RetrieveResponse(chunks=[RetrievedChunk(**h) for h in hits])
    )


@router.post("/index/chunks", response_model=DataResponse[IndexChunksResponse])
def index_chunks(
    body: IndexChunksRequest,
    engine: RetrievalEngine = Depends(get_engine),
) -> DataResponse[IndexChunksResponse]:
    chunk_ids: list[str] = []
    documents: list[str] = []
    bm25_documents: list[str] = []
    metadatas: list[dict] = []

    for chunk in body.chunks:
        chunk_ids.append(chunk.chunk_id)
        documents.append(chunk.text)
        bm25_documents.append(chunk.bm25_text or chunk.text)
        metadatas.append(_chunk_metadata(chunk))

    indexed = engine.index_chunks(
        project_id=body.project_id,
        file_id=body.file_id,
        chunk_ids=chunk_ids,
        documents=documents,
        bm25_documents=bm25_documents,
        metadatas=metadatas,
    )
    os.makedirs(settings.data_dir, exist_ok=True)
    engine.bm25.save(settings.bm25_path)
    return DataResponse(data=IndexChunksResponse(indexed=indexed))


@router.delete("/index/{project_id}", response_model=DataResponse[DeleteIndexResponse])
def delete_project_index(
    project_id: str,
    engine: RetrievalEngine = Depends(get_engine),
) -> DataResponse[DeleteIndexResponse]:
    if project_id == "__global__":
        raise HTTPException(status_code=400, detail="Cannot delete global knowledge base.")
    removed = engine.delete_project_index(project_id)
    engine.bm25.save(settings.bm25_path)
    return DataResponse(data=DeleteIndexResponse(removed=removed))
