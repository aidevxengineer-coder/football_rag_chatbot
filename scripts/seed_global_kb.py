#!/usr/bin/env python3
"""Seed final-articles.csv into the global knowledge base (__global__)."""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path
from typing import Iterator

# Allow `python scripts/seed_global_kb.py` without manual PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import httpx

from services.ingestion.chunking.text_chunker import chunk_prose
from services.retrieval.indexer import chunked_to_index_payload
from services.retrieval.schemas import ChunkInput

logger = logging.getLogger(__name__)

GLOBAL_PROJECT_KEY = "__global__"

GLOBAL_FILE_ID = "final-articles-v1"
DEFAULT_CSV = "final-articles.csv"
PROBE_QUERY = "Premier League football"


def _article_body(title: str, content: str) -> str:
    title = (title or "").strip()
    content = (content or "").strip()
    if title and content:
        return f"# {title}\n\n{content}"
    return title or content


def _iter_articles(csv_path: str) -> Iterator[tuple[int, dict[str, str]]]:
    with open(csv_path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader):
            yield index, row


def _is_seeded(retrieval_url: str) -> bool:
    try:
        response = httpx.post(
            f"{retrieval_url.rstrip('/')}/retrieve",
            json={
                "query": PROBE_QUERY,
                "top_k": 1,
                "project_ids": [GLOBAL_PROJECT_KEY],
            },
            timeout=30.0,
        )
        response.raise_for_status()
        chunks = response.json().get("data", {}).get("chunks") or []
        return len(chunks) > 0
    except httpx.HTTPError as exc:
        logger.warning("Could not probe global KB: %s", exc)
        return False


def _wait_for_retrieval(client: httpx.Client, retrieval_url: str, *, timeout_s: int = 300) -> None:
    deadline = time.perf_counter() + timeout_s
    while time.perf_counter() < deadline:
        try:
            response = client.get(f"{retrieval_url.rstrip('/')}/health", timeout=15.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            logger.info("Waiting for retrieval service: %s", exc)
        time.sleep(5)
    raise TimeoutError(f"Retrieval service not healthy after {timeout_s}s")


def _post_batch(
    client: httpx.Client,
    retrieval_url: str,
    batch: list[ChunkInput],
    *,
    max_attempts: int = 5,
) -> int:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.post(
                f"{retrieval_url.rstrip('/')}/index/chunks",
                json={
                    "project_id": GLOBAL_PROJECT_KEY,
                    "file_id": GLOBAL_FILE_ID,
                    "chunks": [chunk.model_dump() for chunk in batch],
                },
                timeout=180.0,
            )
            response.raise_for_status()
            return int(response.json()["data"]["indexed"])
        except httpx.HTTPError as exc:
            last_error = exc
            wait = min(30, 2**attempt)
            logger.warning(
                "Index batch failed (attempt %s/%s): %s; retrying in %ss",
                attempt,
                max_attempts,
                exc,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"Failed to index batch after {max_attempts} attempts") from last_error


def seed_global_kb(
    csv_path: str,
    *,
    retrieval_url: str,
    batch_size: int = 16,
    limit: int | None = None,
    start_row: int = 0,
    force: bool = False,
) -> int:
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(csv_path)

    if not force and _is_seeded(retrieval_url):
        logger.info("Global KB already seeded; use --force to re-index")
        return 0

    indexed = 0
    articles = 0
    pending: list[ChunkInput] = []
    started = time.perf_counter()

    with httpx.Client() as client:
        _wait_for_retrieval(client, retrieval_url)

        for row_index, row in _iter_articles(csv_path):
            if row_index < start_row:
                continue
            if limit is not None and articles >= limit:
                break

            title = (row.get("title") or "").strip()
            content = (row.get("content") or "").strip()
            link = (row.get("link") or "").strip()
            if not title and not content:
                continue

            body = _article_body(title, content)
            source_file = link or title[:120] or f"article-{row_index}"
            chunks = chunk_prose(
                body,
                source_file=source_file,
                chunk_type="article",
                section_heading=title[:240],
            )
            if not chunks:
                continue

            texts, bm25_texts, _metas, chunk_ids = chunked_to_index_payload(
                chunks,
                source_file=source_file,
                extra_metadata={
                    "url": link,
                    "title": title,
                    "source": (row.get("source") or "goal.com").strip(),
                    "date": (row.get("publish-time") or "").strip(),
                },
                id_prefix=f"global_art_{row_index}",
            )

            for chunk_id, text, bm25_text, chunk in zip(
                chunk_ids, texts, bm25_texts, chunks, strict=True
            ):
                pending.append(
                    ChunkInput(
                        chunk_id=chunk_id,
                        text=text,
                        bm25_text=bm25_text,
                        source_file=source_file,
                        section_heading=title[:240],
                        chunk_type="article",
                        chunk_index=chunk.chunk_index,
                        token_count=chunk.token_count,
                    )
                )
                if len(pending) >= batch_size:
                    indexed += _post_batch(client, retrieval_url, pending)
                    pending.clear()
                    time.sleep(0.25)

            articles += 1
            if articles % 250 == 0:
                elapsed = time.perf_counter() - started
                logger.info(
                    "Indexed %s chunks from %s articles (%.1fs)",
                    indexed,
                    articles,
                    elapsed,
                )

        if pending:
            indexed += _post_batch(client, retrieval_url, pending)

    elapsed = time.perf_counter() - started
    logger.info(
        "Finished: %s chunks from %s articles in %.1fs",
        indexed,
        articles,
        elapsed,
    )
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        default=os.getenv("GLOBAL_KB_CSV", DEFAULT_CSV),
        help="Path to final-articles.csv",
    )
    parser.add_argument(
        "--retrieval-url",
        default=os.getenv("RETRIEVAL_SERVICE_URL", "http://localhost:8085"),
        help="Retrieval service base URL",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=None, help="Max articles (dev)")
    parser.add_argument("--start-row", type=int, default=0, help="Resume from CSV row index")
    parser.add_argument("--force", action="store_true", help="Re-index even if seeded")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        count = seed_global_kb(
            args.csv,
            retrieval_url=args.retrieval_url,
            batch_size=max(1, args.batch_size),
            limit=args.limit,
            start_row=max(0, args.start_row),
            force=args.force,
        )
    except Exception as exc:
        logger.error("%s", exc)
        return 1

    if count == 0 and not args.force:
        return 0
    logger.info("Global knowledge base ready (%s chunks)", count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
