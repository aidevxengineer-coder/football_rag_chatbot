import os
import tempfile
import time

from services.ingestion.chunking.smart_chunker import SmartChunker
from services.ingestion.errors import (
    EmptyFileError,
    FootballRelevanceError,
    IngestionProviderError,
    UnsupportedFormatError,
)
from services.ingestion.extractors.registry import extract_file, get_file_type, get_relevance_sample
from services.ingestion.relevance import enforce_football_relevance
from services.ingestion.retrieval_client import index_chunks
from services.llm_gateway.config import settings as llm_settings
from services.retrieval.indexer import chunked_to_index_payload

_CHUNKER = SmartChunker()


def process_file_bytes(
    *,
    project_id: str,
    file_id: str,
    filename: str,
    file_bytes: bytes,
) -> dict:
    if llm_settings.llm_provider != "groq":
        raise IngestionProviderError()

    if not file_bytes:
        raise EmptyFileError(filename)

    suffix = os.path.splitext(filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        return _process_path(
            project_id=project_id,
            file_id=file_id,
            filename=filename,
            path=tmp_path,
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _process_path(*, project_id: str, file_id: str, filename: str, path: str) -> dict:
    started = time.monotonic()
    try:
        blocks, file_type = extract_file(path, filename)
    except UnsupportedFormatError:
        raise

    if not blocks:
        raise EmptyFileError(filename)

    sample = get_relevance_sample(path, filename, blocks)
    verdict = enforce_football_relevance(sample, filename)
    chunks = _CHUNKER.chunk_blocks(blocks)
    chunk_texts, bm25_texts, metadatas, chunk_ids = chunked_to_index_payload(
        chunks,
        source_file=filename,
    )

    payload_chunks = []
    for chunk_id, text, bm25_text, meta in zip(
        chunk_ids, chunk_texts, bm25_texts, metadatas, strict=True
    ):
        page = meta.get("page_number")
        payload_chunks.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "bm25_text": bm25_text,
                "source_file": meta.get("source_file", filename),
                "section_heading": meta.get("section_heading", ""),
                "page": page if isinstance(page, int) and page >= 0 else None,
                "chunk_type": meta.get("chunk_type", "text"),
                "chunk_index": meta.get("chunk_index", 0),
                "token_count": meta.get("token_count", 0),
            }
        )

    indexed = index_chunks(
        project_id=project_id,
        file_id=file_id,
        chunks=payload_chunks,
    )
    tokens_indexed = sum(int(c.get("token_count") or 0) for c in payload_chunks)
    duration_ms = int((time.monotonic() - started) * 1000)
    return {
        "status": "success",
        "filename": filename,
        "file_type": file_type,
        "chunks_indexed": indexed,
        "tokens_indexed": tokens_indexed,
        "relevance_verdict": verdict,
        "duration_ms": duration_ms,
    }
