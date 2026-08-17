from typing import Any

from services.retrieval.dense import GLOBAL_PROJECT_KEY
from services.retrieval.bm25 import BM25Store
from services.retrieval.dense import DenseStore
from services.retrieval.rrf import reciprocal_rank_fusion


def citation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    meta = result.get("metadata") or {}
    page_number = meta.get("page_number", -1)
    page = page_number if isinstance(page_number, int) and page_number >= 0 else None
    return {
        "chunk_id": result["chunk_id"],
        "source_file": meta.get("source_file", ""),
        "page": page,
        "section_heading": meta.get("section_heading", ""),
        "document": result.get("document", ""),
        "rrf_score": float(result.get("rrf_score", 0.0)),
    }


class RetrievalEngine:
    def __init__(self, dense: DenseStore, bm25: BM25Store) -> None:
        self.dense = dense
        self.bm25 = bm25

    def index_chunks(
        self,
        *,
        project_id: str | None,
        file_id: str,
        chunk_ids: list[str],
        documents: list[str],
        bm25_documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> int:
        project_ids = [project_id] * len(chunk_ids)
        enriched = []
        for meta in metadatas:
            row = dict(meta)
            row["project_id"] = project_id
            row["file_id"] = file_id
            enriched.append(row)

        self.dense.add_chunks(chunk_ids, documents, project_ids, enriched)
        self.bm25.add_chunks(chunk_ids, bm25_documents, project_ids, enriched)
        return len(chunk_ids)

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        project_id: str | None = None,
        project_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        scopes = project_ids
        if scopes is None:
            scopes = [project_id] if project_id is not None else [None]

        dense_hits: list[dict[str, Any]] = []
        sparse_hits: list[dict[str, Any]] = []
        for scope in scopes:
            dense_pid = None if scope == GLOBAL_PROJECT_KEY else scope
            bm25_pid = None if scope == GLOBAL_PROJECT_KEY else scope
            dense_hits.extend(
                self.dense.query(query, top_k=top_k * 3, project_id=dense_pid)
            )
            try:
                sparse_hits.extend(
                    self.bm25.search(query, top_k=top_k * 3, project_id=bm25_pid)
                )
            except RuntimeError:
                pass

        fused = reciprocal_rank_fusion(dense_hits, sparse_hits, top_k=top_k)
        return [citation_from_result(r) for r in fused]

    def delete_project_index(self, project_id: str) -> int:
        dense_removed = self.dense.delete_project(project_id)
        bm25_removed = self.bm25.delete_project(project_id)
        return max(dense_removed, bm25_removed)
