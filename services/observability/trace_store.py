"""
db_logger.py
============
Normalized SQLite trace logger for the FutBot RAG pipeline.

Schema (normalized):
  pipeline_runs       – one row per /api/chat call
  llm_calls           – one row per invoke_llm call (prompt, response, latency)
  loop_iterations     – one row per rewriter→judge retry cycle
  retrieval_events    – one row per retrieve_node call
  retrieved_chunks    – one row per chunk returned in a retrieval event
  tool_calls          – one row per tool invocation on the TOOL path
"""

import hashlib
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from futbot_common.context import get_correlation_id

from services.observability.config import settings

DB_PATH = settings.db_path


# ---------------------------------------------------------------------------
# Schema Initialization
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Top-level run — one per user message processed through the pipeline
    c.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id          TEXT,
            original_query      TEXT NOT NULL,
            classification      TEXT,           -- SIMPLE | KNOWLEDGE | UNKNOWN
            total_iterations    INTEGER DEFAULT 0,
            final_answer        TEXT,
            reached_max_retries INTEGER DEFAULT 0,  -- boolean (0/1)
            started_at          TEXT NOT NULL,
            finished_at         TEXT,
            duration_ms         INTEGER
        )
    """)

    # 2. Each call to invoke_llm — captures prompt, response, latency
    c.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration       INTEGER DEFAULT 0,  -- which retry loop this belongs to
            step            TEXT NOT NULL,       -- rewriter | orchestrator | drafter | judge | simple_responder
            model_name      TEXT NOT NULL,
            api_url         TEXT,
            prompt          TEXT NOT NULL,
            raw_response    TEXT,               -- before think-tag stripping
            response        TEXT,               -- after stripping
            status_code     INTEGER,
            latency_ms      INTEGER,
            called_at       TEXT NOT NULL
        )
    """)

    # 3. One row per retry loop iteration (rewrite → retrieve → draft → judge)
    c.execute("""
        CREATE TABLE IF NOT EXISTS loop_iterations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration       INTEGER NOT NULL,
            rewritten_query TEXT,
            judge_status    TEXT,               -- PASS | FAIL
            judge_reasoning TEXT,
            created_at      TEXT NOT NULL
        )
    """)

    # 4. One row per retrieve_node call
    c.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_events (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration_id    INTEGER REFERENCES loop_iterations(id),
            iteration       INTEGER DEFAULT 0,
            query_used      TEXT NOT NULL,      -- the rewritten query
            dense_count     INTEGER DEFAULT 0,
            sparse_count    INTEGER DEFAULT 0,
            fused_count     INTEGER DEFAULT 0,
            retrieved_at    TEXT NOT NULL
        )
    """)

    # 5. Tool invocations during TOOL-path pipeline runs
    c.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            iteration       INTEGER DEFAULT 0,
            tool_name       TEXT NOT NULL,
            success         INTEGER DEFAULT 0,
            skipped         INTEGER DEFAULT 0,
            error_message   TEXT,
            latency_ms      INTEGER,
            called_at       TEXT NOT NULL
        )
    """)

    # 6. Normalized individual chunks returned by retrieval
    c.execute("""
        CREATE TABLE IF NOT EXISTS retrieved_chunks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id        INTEGER NOT NULL REFERENCES retrieval_events(id),
            run_id          INTEGER NOT NULL REFERENCES pipeline_runs(id),
            rank            INTEGER NOT NULL,
            chunk_id        TEXT NOT NULL,
            document        TEXT,
            rrf_score       REAL,
            source          TEXT,
            title           TEXT,
            url             TEXT,
            date_published  TEXT
        )
    """)

    conn.commit()
    _migrate_pipeline_runs_schema(conn)
    _migrate_ingestion_events_schema(conn)
    _migrate_ingestion_chunks_schema(conn)
    conn.close()


def _migrate_ingestion_events_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_events (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            filename          TEXT NOT NULL,
            file_type         TEXT NOT NULL,
            status            TEXT NOT NULL,
            chunk_count       INTEGER,
            relevance_verdict TEXT,
            error             TEXT,
            duration_ms       INTEGER,
            images_total      INTEGER,
            images_processed  INTEGER,
            ingested_at       TEXT DEFAULT (datetime('now'))
        )
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(ingestion_events)").fetchall()}
    if "images_total" not in columns:
        conn.execute("ALTER TABLE ingestion_events ADD COLUMN images_total INTEGER")
    if "images_processed" not in columns:
        conn.execute("ALTER TABLE ingestion_events ADD COLUMN images_processed INTEGER")
    if "content_hash" not in columns:
        conn.execute("ALTER TABLE ingestion_events ADD COLUMN content_hash TEXT")
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_ingestion_events_content_hash
           ON ingestion_events(content_hash)
           WHERE content_hash IS NOT NULL AND status IN ('success', 'processing')"""
    )
    conn.commit()


def _migrate_ingestion_chunks_schema(conn: sqlite3.Connection):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_chunks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ingestion_id    INTEGER NOT NULL REFERENCES ingestion_events(id),
            chunk_index     INTEGER NOT NULL,
            chunk_id        TEXT NOT NULL,
            chunk_text      TEXT NOT NULL,
            chunk_type      TEXT,
            section_heading TEXT,
            page_number     INTEGER,
            sheet_name      TEXT,
            token_count     INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_ingestion_chunks_ingestion_id
           ON ingestion_chunks(ingestion_id)"""
    )
    conn.commit()


def _migrate_pipeline_runs_schema(conn: sqlite3.Connection):
    """Add snapshot/tracing columns to existing databases."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(pipeline_runs)").fetchall()}
    if "snapshot_text" not in columns:
        conn.execute("ALTER TABLE pipeline_runs ADD COLUMN snapshot_text TEXT")
    if "snapshot_token_count" not in columns:
        conn.execute("ALTER TABLE pipeline_runs ADD COLUMN snapshot_token_count INTEGER")
    if "correlation_id" not in columns:
        # Links this pipeline run to the OpenTelemetry trace ID / HTTP
        # X-Correlation-ID for the same request (see
        # futbot_common.middleware.CorrelationIdMiddleware). Populated at
        # PipelineRunLogger.__enter__() time via get_correlation_id().
        # Lets you jump: gateway/service logs <-> Jaeger trace <-> this
        # pipeline run's full LLM/retrieval/tool-call detail, all by the
        # same ID.
        conn.execute("ALTER TABLE pipeline_runs ADD COLUMN correlation_id TEXT")


# ---------------------------------------------------------------------------
# Context Manager for Pipeline Runs
# ---------------------------------------------------------------------------

class PipelineRunLogger:
    """
    Tracks a single pipeline_runs row and provides helpers to log each sub-event.
    Designed to be instantiated at the start of run_pipeline() and passed down.

    Thread-safety: a fresh SQLite connection is opened and closed for every
    operation, so this object can be shared across LangGraph worker threads.

    Usage:
        with PipelineRunLogger(session_id=..., original_query=...) as run:
            run.log_llm_call(step="rewriter", ...)
            run.log_retrieval(query_used=..., chunks=...)
            run.finish(classification="KNOWLEDGE", final_answer="...", ...)
    """

    def __init__(self, original_query: str, session_id: str = ""):
        self.original_query = original_query
        self.session_id = session_id
        self.run_id: Optional[int] = None
        self._start_ms = int(time.monotonic() * 1000)

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh thread-local SQLite connection."""
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def __enter__(self):
        # Captured here (not passed in) so every caller gets this for
        # free -- it's whatever correlation ID / trace ID is active on
        # the contextvar for the request this pipeline run belongs to.
        correlation_id = get_correlation_id()
        conn = self._connect()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT INTO pipeline_runs (session_id, original_query, started_at, correlation_id) "
                "VALUES (?, ?, ?, ?)",
                (self.session_id, self.original_query, _now(), correlation_id)
            )
            self.run_id = c.lastrowid
            conn.commit()
        finally:
            conn.close()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False  # do not suppress exceptions

    # ---- LLM call logging -------------------------------------------------

    def log_llm_call(
        self,
        step: str,
        model_name: str,
        prompt: str,
        raw_response: str,
        response: str,
        api_url: str = "",
        status_code: Optional[int] = None,
        latency_ms: Optional[int] = None,
        iteration: int = 0,
    ):
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO llm_calls
                   (run_id, iteration, step, model_name, api_url, prompt, raw_response,
                    response, status_code, latency_ms, called_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    self.run_id, iteration, step, model_name, api_url,
                    prompt, raw_response, response, status_code, latency_ms, _now()
                )
            )
            conn.commit()
        finally:
            conn.close()

    # ---- Retrieval logging ------------------------------------------------

    def log_retrieval(
        self,
        query_used: str,
        fused_chunks: List[Dict[str, Any]],
        dense_count: int = 0,
        sparse_count: int = 0,
        iteration: int = 0,
        iteration_id: Optional[int] = None,
    ) -> int:
        """Inserts a retrieval_events row + individual retrieved_chunks rows."""
        conn = self._connect()
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO retrieval_events
                   (run_id, iteration_id, iteration, query_used,
                    dense_count, sparse_count, fused_count, retrieved_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    self.run_id, iteration_id, iteration, query_used,
                    dense_count, sparse_count, len(fused_chunks), _now()
                )
            )
            event_id = c.lastrowid

            for rank, chunk in enumerate(fused_chunks, start=1):
                meta = chunk.get("metadata", {})
                c.execute(
                    """INSERT INTO retrieved_chunks
                       (event_id, run_id, rank, chunk_id, document, rrf_score,
                        source, title, url, date_published)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        event_id, self.run_id, rank,
                        chunk.get("chunk_id", ""),
                        chunk.get("document", ""),
                        chunk.get("rrf_score"),
                        meta.get("source", chunk.get("source", "")),
                        meta.get("title", chunk.get("title", "")),
                        meta.get("url", chunk.get("url", "")),
                        meta.get("date", chunk.get("date_published", "")),
                    )
                )

            conn.commit()
            return event_id
        finally:
            conn.close()

    # ---- Tool call logging ------------------------------------------------

    def log_tool_call(
        self,
        tool_name: str,
        *,
        success: bool = False,
        skipped: bool = False,
        error_message: str = "",
        latency_ms: Optional[int] = None,
        iteration: int = 0,
    ):
        conn = self._connect()
        try:
            conn.execute(
                """INSERT INTO tool_calls
                   (run_id, iteration, tool_name, success, skipped, error_message,
                    latency_ms, called_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    self.run_id, iteration, tool_name,
                    int(success), int(skipped), error_message or None,
                    latency_ms, _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ---- Loop iteration logging -------------------------------------------

    def log_iteration(
        self,
        iteration: int,
        rewritten_query: str = "",
        judge_status: str = "",
        judge_reasoning: str = "",
    ) -> int:
        """Insert a loop_iterations row."""
        conn = self._connect()
        try:
            c = conn.cursor()
            c.execute(
                """INSERT INTO loop_iterations
                   (run_id, iteration, rewritten_query, judge_status, judge_reasoning, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (self.run_id, iteration, rewritten_query, judge_status, judge_reasoning, _now())
            )
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def update_iteration(
        self,
        iteration_id: int,
        judge_status: str = "",
        judge_reasoning: str = "",
    ):
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE loop_iterations
                   SET judge_status=?, judge_reasoning=?
                   WHERE id=?""",
                (judge_status, judge_reasoning, iteration_id)
            )
            conn.commit()
        finally:
            conn.close()

    # ---- Final run completion ---------------------------------------------

    def finish(
        self,
        classification: str = "UNKNOWN",
        total_iterations: int = 0,
        final_answer: str = "",
        reached_max_retries: bool = False,
        snapshot_text: str = "",
        snapshot_token_count: Optional[int] = None,
    ):
        elapsed = int(time.monotonic() * 1000) - self._start_ms
        conn = self._connect()
        try:
            conn.execute(
                """UPDATE pipeline_runs
                   SET classification=?, total_iterations=?, final_answer=?,
                       reached_max_retries=?, finished_at=?, duration_ms=?,
                       snapshot_text=?, snapshot_token_count=?
                   WHERE id=?""",
                (
                    classification, total_iterations, final_answer,
                    int(reached_max_retries), _now(), elapsed,
                    snapshot_text, snapshot_token_count,
                    self.run_id
                )
            )
            conn.commit()
        finally:
            conn.close()


def get_run_trace(run_id: int) -> dict[str, Any] | None:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """SELECT id, session_id, original_query, classification, total_iterations,
                      final_answer, reached_max_retries, started_at, finished_at, duration_ms,
                      snapshot_text, snapshot_token_count, correlation_id
               FROM pipeline_runs WHERE id = ?""",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        llm_calls = conn.execute(
            """SELECT step, model_name, iteration, latency_ms, called_at
               FROM llm_calls WHERE run_id = ? ORDER BY id""",
            (run_id,),
        ).fetchall()
        iterations = conn.execute(
            """SELECT iteration, rewritten_query, judge_status, judge_reasoning
               FROM loop_iterations WHERE run_id = ? ORDER BY iteration""",
            (run_id,),
        ).fetchall()
        tool_calls = conn.execute(
            """SELECT tool_name, success, skipped, error_message, latency_ms, iteration, called_at
               FROM tool_calls WHERE run_id = ? ORDER BY id""",
            (run_id,),
        ).fetchall()
        return {
            "id": row[0],
            "session_id": row[1],
            "original_query": row[2],
            "classification": row[3],
            "total_iterations": row[4],
            "final_answer": row[5],
            "reached_max_retries": bool(row[6]),
            "started_at": row[7],
            "finished_at": row[8],
            "duration_ms": row[9],
            "snapshot_text": row[10],
            "snapshot_token_count": row[11],
            "correlation_id": row[12],
            "llm_calls": [
                {
                    "step": r[0],
                    "model_name": r[1],
                    "iteration": r[2],
                    "latency_ms": r[3],
                    "called_at": r[4],
                }
                for r in llm_calls
            ],
            "iterations": [
                {
                    "iteration": r[0],
                    "rewritten_query": r[1],
                    "judge_status": r[2],
                    "judge_reasoning": r[3],
                }
                for r in iterations
            ],
            "tool_calls": [
                {
                    "tool_name": r[0],
                    "success": bool(r[1]),
                    "skipped": bool(r[2]),
                    "error_message": r[3],
                    "latency_ms": r[4],
                    "iteration": r[5],
                    "called_at": r[6],
                }
                for r in tool_calls
            ],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Legacy shim — kept so existing tests don't break
# ---------------------------------------------------------------------------

def log_pipeline_trace(
    original_query: str,
    classification: str,
    total_iterations: int,
    final_answer: str,
    loop_traces: list,
    session_id: str = "",
):
    """Thin compatibility wrapper for callers that use the old API."""
    with PipelineRunLogger(original_query=original_query, session_id=session_id) as run:
        for i, trace in enumerate(loop_traces, start=1):
            iter_id = run.log_iteration(
                iteration=i,
                rewritten_query=trace.get("rewritten_query", ""),
                judge_status=trace.get("judge_status", ""),
                judge_reasoning=trace.get("judge_reasoning", ""),
            )
        run.finish(
            classification=classification,
            total_iterations=total_iterations,
            final_answer=final_answer,
        )


# ---------------------------------------------------------------------------
# Ingestion event logging
# ---------------------------------------------------------------------------

def compute_content_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def find_duplicate_ingestion(content_hash: str) -> Optional[Dict[str, Any]]:
    """Return an existing ingestion if the same content is already indexed or in-flight."""
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """SELECT id, filename, status
               FROM ingestion_events
               WHERE content_hash = ? AND status IN ('success', 'processing')
               ORDER BY id DESC
               LIMIT 1""",
            (content_hash,),
        ).fetchone()
        if row is None:
            return None
        return {"id": row[0], "filename": row[1], "status": row[2]}
    finally:
        conn.close()


def create_ingestion_event(
    filename: str,
    file_type: str,
    status: str,
    chunk_count: Optional[int] = None,
    relevance_verdict: Optional[str] = None,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
    images_total: Optional[int] = None,
    images_processed: Optional[int] = None,
    content_hash: Optional[str] = None,
) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.execute(
            """INSERT INTO ingestion_events
               (filename, file_type, status, chunk_count, relevance_verdict, error,
                duration_ms, images_total, images_processed, content_hash)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                filename, file_type, status, chunk_count, relevance_verdict, error,
                duration_ms, images_total, images_processed, content_hash,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    finally:
        conn.close()


def log_ingestion_chunks(
    ingestion_id: int,
    chunk_texts: list[str],
    metadatas: list[dict[str, Any]],
    chunk_ids: list[str],
) -> None:
    if not chunk_texts:
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        rows = []
        for idx, (chunk_id, text, meta) in enumerate(
            zip(chunk_ids, chunk_texts, metadatas)
        ):
            page_number = meta.get("page_number")
            rows.append((
                ingestion_id,
                meta.get("chunk_index", idx),
                chunk_id,
                text,
                meta.get("chunk_type"),
                meta.get("section_heading") or None,
                page_number if page_number is not None and page_number >= 0 else None,
                meta.get("sheet_name"),
                meta.get("token_count"),
            ))
        conn.executemany(
            """INSERT INTO ingestion_chunks
               (ingestion_id, chunk_index, chunk_id, chunk_text, chunk_type,
                section_heading, page_number, sheet_name, token_count)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def get_ingestion_chunks(ingestion_id: int) -> list[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT id, ingestion_id, chunk_index, chunk_id, chunk_text, chunk_type,
                      section_heading, page_number, sheet_name, token_count, created_at
               FROM ingestion_chunks
               WHERE ingestion_id = ?
               ORDER BY chunk_index""",
            (ingestion_id,),
        ).fetchall()
        return [
            {
                "id": row[0],
                "ingestion_id": row[1],
                "chunk_index": row[2],
                "chunk_id": row[3],
                "chunk_text": row[4],
                "chunk_type": row[5],
                "section_heading": row[6],
                "page_number": row[7],
                "sheet_name": row[8],
                "token_count": row[9],
                "created_at": row[10],
            }
            for row in rows
        ]
    finally:
        conn.close()


def update_ingestion_event(event_id: int, **fields):
    allowed = {
        "status", "file_type", "chunk_count", "relevance_verdict",
        "error", "duration_ms", "images_total", "images_processed",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return

    set_clause = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [event_id]
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            f"UPDATE ingestion_events SET {set_clause} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_ingestion_event(event_id: int) -> Optional[Dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute(
            """SELECT id, filename, file_type, status, chunk_count, relevance_verdict,
                      error, duration_ms, images_total, images_processed, ingested_at,
                      content_hash
               FROM ingestion_events WHERE id = ?""",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "filename": row[1],
            "file_type": row[2],
            "status": row[3],
            "chunk_count": row[4],
            "relevance_verdict": row[5],
            "error": row[6],
            "duration_ms": row[7],
            "images_total": row[8],
            "images_processed": row[9],
            "ingested_at": row[10],
            "content_hash": row[11],
        }
    finally:
        conn.close()


def log_ingestion_event(
    filename: str,
    file_type: str,
    status: str,
    chunk_count: Optional[int] = None,
    relevance_verdict: Optional[str] = None,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> int:
    return create_ingestion_event(
        filename=filename,
        file_type=file_type,
        status=status,
        chunk_count=chunk_count,
        relevance_verdict=relevance_verdict,
        error=error,
        duration_ms=duration_ms,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


