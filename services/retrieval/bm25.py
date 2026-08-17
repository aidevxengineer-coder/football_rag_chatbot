import logging
import os
import pickle
from typing import Any, Optional

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class BM25Store:
    """Sparse index with per-chunk project_id metadata for scoped search."""

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunk_ids: list[str] = []
        self._corpus: list[str] = []
        self._project_ids: list[str | None] = []
        self._metadatas: list[dict[str, Any]] = []

    def is_loaded(self) -> bool:
        return self._bm25 is not None

    @property
    def corpus(self) -> list[str]:
        return self._corpus

    @property
    def chunk_ids(self) -> list[str]:
        return self._chunk_ids

    def add_chunks(
        self,
        chunk_ids: list[str],
        corpus: list[str],
        project_ids: list[str | None],
        metadatas: list[dict[str, Any]],
    ) -> None:
        self._corpus.extend(corpus)
        self._chunk_ids.extend(chunk_ids)
        self._project_ids.extend(project_ids)
        self._metadatas.extend(metadatas)
        tokenized = [doc.lower().split() for doc in self._corpus]
        self._bm25 = BM25Okapi(tokenized)

    def _scoped_indices(self, project_id: str | None) -> list[int]:
        if project_id is None:
            return [i for i, pid in enumerate(self._project_ids) if pid is None]
        return [i for i, pid in enumerate(self._project_ids) if pid == project_id]

    def search(self, query: str, top_k: int = 5, project_id: str | None = None) -> list[dict[str, Any]]:
        if self._bm25 is None:
            raise RuntimeError("BM25 index has not been built.")

        indices = self._scoped_indices(project_id)
        if not indices:
            return []

        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)
        ranked = sorted(
            ((idx, scores[idx]) for idx in indices),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        results: list[dict[str, Any]] = []
        for idx, score in ranked:
            meta = dict(self._metadatas[idx])
            results.append(
                {
                    "chunk_id": self._chunk_ids[idx],
                    "document": self._corpus[idx],
                    "score": float(score),
                    "metadata": meta,
                }
            )
        return results

    def delete_project(self, project_id: str) -> int:
        keep = [i for i, pid in enumerate(self._project_ids) if pid != project_id]
        removed = len(self._project_ids) - len(keep)
        if removed == 0:
            return 0
        self._corpus = [self._corpus[i] for i in keep]
        self._chunk_ids = [self._chunk_ids[i] for i in keep]
        self._project_ids = [self._project_ids[i] for i in keep]
        self._metadatas = [self._metadatas[i] for i in keep]
        if self._corpus:
            tokenized = [doc.lower().split() for doc in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None
        return removed

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp_path = f"{path}.tmp"
        payload = {
            "bm25": self._bm25,
            "chunk_ids": self._chunk_ids,
            "corpus": self._corpus,
            "project_ids": self._project_ids,
            "metadatas": self._metadatas,
        }
        with open(tmp_path, "wb") as f:
            pickle.dump(payload, f)
        os.replace(tmp_path, path)

    def load(self, path: str) -> bool:
        if not os.path.exists(path):
            return False
        try:
            with open(path, "rb") as f:
                data = pickle.load(f)
        except (EOFError, pickle.UnpicklingError, KeyError, ValueError) as exc:
            logger.warning("Corrupt BM25 index at %s (%s); starting fresh", path, exc)
            return False
        self._bm25 = data["bm25"]
        self._chunk_ids = data["chunk_ids"]
        self._corpus = data["corpus"]
        self._project_ids = data.get("project_ids", [None] * len(data["chunk_ids"]))
        self._metadatas = data.get("metadatas", [{} for _ in data["chunk_ids"]])
        return True

    @property
    def metadatas(self) -> list[dict[str, Any]]:
        return self._metadatas

    def import_legacy(
        self,
        chunk_ids: list[str],
        corpus: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        project_ids = [m.get("project_id") for m in metadatas]
        self._corpus = list(corpus)
        self._chunk_ids = list(chunk_ids)
        self._project_ids = project_ids
        self._metadatas = list(metadatas)
        if self._corpus:
            tokenized = [doc.lower().split() for doc in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
