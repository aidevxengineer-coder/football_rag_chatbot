"""Run the RAG pipeline after the user message has already been persisted."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from services.chat.context_builder import ensure_snapshot, load_chat_with_messages
from services.chat.db import get_session_factory
from services.chat.models import Message
from services.chat.orchestrator_client import run_pipeline_sync

logger = logging.getLogger(__name__)


async def _save_pipeline_outcome(
    db: AsyncSession,
    *,
    chat_id: str,
    content: str,
    pipeline_result: dict,
    fallback_snapshot: str,
    fallback_turn_count: int,
) -> None:
    chat = await load_chat_with_messages(db, chat_id)
    if not chat:
        return

    assistant_msg = Message(
        chat_id=chat.id,
        role="assistant",
        content=content,
        citations_json=json.dumps(pipeline_result.get("citations", [])),
    )
    db.add(assistant_msg)
    chat.updated_at = datetime.now(timezone.utc)

    snap_row = await ensure_snapshot(db, chat.id)
    snap_row.snapshot_text = pipeline_result.get("snapshot", fallback_snapshot)
    snap_row.snapshot_turn_count = pipeline_result.get(
        "snapshot_turn_count", fallback_turn_count
    )
    await db.commit()


async def run_pipeline_for_chat(
    *,
    chat_id: str,
    user_id: str | None,
    query: str,
    web_search_enabled: bool,
) -> None:
    factory = get_session_factory()
    async with factory() as db:
        chat = await load_chat_with_messages(db, chat_id)
        if not chat:
            logger.warning("Pipeline skipped: chat %s not found", chat_id)
            return

        snap = chat.snapshot.snapshot_text if chat.snapshot else ""
        turn_count = chat.snapshot.snapshot_turn_count if chat.snapshot else 0
        history = [
            {"role": m.role, "content": m.content}
            for m in sorted(chat.messages, key=lambda m: m.created_at)
        ]

        pipeline_result: dict = {}
        try:
            pipeline_result = await asyncio.to_thread(
                run_pipeline_sync,
                session_id=chat.id,
                query=query,
                context_messages=history,
                snapshot=snap,
                snapshot_turn_count=turn_count,
                project_id=chat.project_id,
                user_id=chat.user_id or user_id,
                web_search_enabled=web_search_enabled,
            )
            content = pipeline_result["reply"]
        except httpx.HTTPError as exc:
            content = (
                "Analysis pipeline unavailable. Ensure rag-orchestrator is running "
                f"and reachable ({exc})."
            )
            pipeline_result = {
                "tool_notice": content,
                "tool_notice_code": "PIPELINE_UNAVAILABLE",
                "reply": content,
                "snapshot": snap,
                "snapshot_turn_count": turn_count,
                "citations": [],
            }
        except Exception as exc:
            logger.exception("Pipeline failed for chat %s", chat_id)
            content = f"Analysis pipeline failed: {exc}"
            pipeline_result = {
                "tool_notice": content,
                "tool_notice_code": "PIPELINE_FAILED",
                "reply": content,
                "snapshot": snap,
                "snapshot_turn_count": turn_count,
                "citations": [],
            }

        try:
            await _save_pipeline_outcome(
                db,
                chat_id=chat_id,
                content=content,
                pipeline_result=pipeline_result,
                fallback_snapshot=snap,
                fallback_turn_count=turn_count,
            )
        except Exception:
            await db.rollback()
            logger.exception("Failed to persist pipeline result for chat %s", chat_id)
