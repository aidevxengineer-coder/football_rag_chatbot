import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, TypedDict

import httpx
from langgraph.graph import StateGraph, END

from services.llm_gateway.components import (
    DecisionJudge,
    DraftGenerator,
    Orchestrator,
    QueryRewriter,
    SnapshotCompressor,
    ToolPlanner,
)
from services.llm_gateway.provider import MODEL_GENERATOR, invoke_llm
from services.llm_gateway.prompt_loader import get_prompt_parts
from services.chat.config import settings as chat_settings
from services.chat.conversation import ConversationContext
from services.observability.trace_store import PipelineRunLogger
from services.rag_orchestrator.config import settings
from services.rag_orchestrator import tool_client
from services.rag_orchestrator.pipeline_events import emit_event

from services.rag_orchestrator.responses import normalize_kb_miss_response
from services.rag_orchestrator.retrieval_scope import resolve_retrieval_project_ids

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------
class GraphState(TypedDict, total=False):
    query: str
    session_id: str
    run_logger: Any

    all_messages: List[Dict[str, str]]
    snapshot: str
    snapshot_turn_count: int
    context_messages: List[Dict[str, str]]

    classification: str
    rewritten_query: str
    retrieved_chunks: List[Dict[str, Any]]

    draft_answer: str
    judge_status: str
    judge_reasoning: str
    retry_count: int
    reached_max_retries: bool
    loop_traces: List[Dict[str, Any]]

    project_id: Optional[str]
    user_id: Optional[str]

    # Internal iteration DB ID (for linking retrieval back to the iteration row)
    current_iteration_id: Optional[int]

    web_search_enabled: bool
    tool_plan: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    tool_errors: List[str]
    tool_notice: Optional[str]
    tool_notice_code: Optional[str]
    web_search_skipped: bool

    final_answer: str


def _session_id(state: GraphState) -> str:
    return state.get("session_id", "")


def _iteration(state: GraphState) -> int:
    return state.get("retry_count", 0) + 1


def _emit_stage(state: GraphState, stage: str, status: str, details: Optional[Dict[str, Any]] = None) -> None:
    sid = _session_id(state)
    if not sid:
        return
    payload: Dict[str, Any] = {
        "type": "stage_update",
        "stage": stage,
        "status": status,
        "iteration": _iteration(state),
    }
    if details is not None:
        payload["details"] = details
    emit_event(sid, payload)


def _chunk_previews(chunks: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, str]]:
    previews = []
    for c in chunks[:limit]:
        meta = c.get("metadata", {}) if isinstance(c.get("metadata"), dict) else {}
        doc = c.get("document", "") or ""
        previews.append({
            "chunk_id": str(c.get("chunk_id", "unknown")),
            "title": str(meta.get("title", c.get("title", ""))),
            "snippet": doc[:240] + ("…" if len(doc) > 240 else ""),
        })
    return previews


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def compressor_node(state: GraphState) -> GraphState:
    _emit_stage(state, "collecting_context", "active")
    run_logger = state.get("run_logger")

    ctx = ConversationContext.from_graph_fields(
        session_id=state.get("session_id", ""),
        messages=state.get("all_messages", []),
        snapshot=state.get("snapshot", ""),
        snapshot_turn_count=state.get("snapshot_turn_count", 0),
    )

    ctx.maintain_snapshot(SnapshotCompressor(), run_logger=run_logger)

    result = ctx.to_graph_fields()
    _emit_stage(state, "collecting_context", "complete", {
        "snapshot": result.get("snapshot", "{}"),
        "snapshot_turn_count": result.get("snapshot_turn_count", 0),
        "hot_message_count": len(result.get("context_messages", [])),
    })
    return result


def rewrite_node(state: GraphState) -> GraphState:
    _emit_stage(state, "rewriting", "active", {
        "snapshot": state.get("snapshot") or "{}",
    })
    run_logger = state.get("run_logger")
    retry_count = state.get("retry_count", 0)
    iteration = retry_count + 1  # 1-indexed

    rewriter = QueryRewriter()
    query = state.get("query", "")
    context = state.get("context_messages", [])
    if not context:
        all_messages = state.get("all_messages", [])
        hot_window = chat_settings.hot_context_window
        context = all_messages[-hot_window:] if hot_window > 0 else all_messages
    snapshot = state.get("snapshot") or "{}"
    judge_feedback = ""
    if retry_count > 0:
        judge_feedback = state.get("judge_reasoning", "") or ""
    rewritten = rewriter.rewrite(
        query,
        context,
        snapshot=snapshot,
        judge_feedback=judge_feedback,
        run_logger=run_logger,
        iteration=iteration,
    )

    # Log the start of this loop iteration
    iteration_id = None
    if run_logger is not None:
        try:
            iteration_id = run_logger.log_iteration(
                iteration=iteration,
                rewritten_query=rewritten,
            )
        except Exception as e:
            logger.warning(f"Failed to log iteration: {e}")

    traces = state.get("loop_traces", [])
    traces.append({"rewritten_query": rewritten})

    _emit_stage(state, "rewriting", "complete", {
        "rewritten_query": rewritten,
        "snapshot": snapshot,
    })

    return {
        "rewritten_query": rewritten,
        "loop_traces": traces,
        "current_iteration_id": iteration_id,
    }

def orchestrator_node(state: GraphState) -> GraphState:
    _emit_stage(state, "orchestrating", "active")
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1

    classifier = Orchestrator()
    classification = classifier.classify(
        state.get("rewritten_query", state.get("query", "")),
        run_logger=run_logger,
        iteration=iteration,
    )
    updates: Dict[str, Any] = {"classification": classification}
    if classification == "TOOL" and not tool_client.mcp_tools_available():
        classification = "KNOWLEDGE"
        updates["classification"] = classification
        updates["tool_notice"] = tool_client.MCP_UNAVAILABLE_NOTICE
        updates["tool_notice_code"] = "MCP_UNAVAILABLE"
    _emit_stage(state, "orchestrating", "complete", {
        "classification": classification,
        "rewritten_query": state.get("rewritten_query", ""),
    })
    return updates

def simple_responder_node(state: GraphState) -> GraphState:
    _emit_stage(state, "responding", "active")
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1

    system_prompt, user_template = get_prompt_parts("SIMPLE_RESPONDER")
    user_content = user_template.format(query=state.get("rewritten_query", state.get("query", "")))
    answer = invoke_llm(
        user_content,
        model_name=MODEL_GENERATOR,
        step="simple_responder",
        run_logger=run_logger,
        iteration=iteration,
        system_prompt=system_prompt,
    )

    if not (answer or "").strip():
        answer = (
            "I couldn't generate a response. Check LLM_PROVIDER and API keys, "
            "then try again."
        )
    _emit_stage(state, "responding", "complete", {"response": answer})
    return {"final_answer": answer}

def _fetch_retrieval_chunks(state: GraphState) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
    run_logger = state.get("run_logger")
    query = (state.get("rewritten_query") or state.get("query") or "").strip()
    iteration = state.get("retry_count", 0) + 1
    iteration_id = state.get("current_iteration_id")
    chunks: list[Dict[str, Any]] = []

    if not query:
        logger.warning("Retrieval skipped: empty query after rewrite")
        return chunks, list(state.get("loop_traces", []))

    try:
        project_ids = resolve_retrieval_project_ids(
            project_id=state.get("project_id"),
            user_id=state.get("user_id"),
        )
        payload: dict[str, Any] = {
            "query": query,
            "top_k": settings.retrieval_top_k,
            "project_ids": project_ids,
        }
        response = httpx.post(
            f"{settings.retrieval_service_url.rstrip('/')}/retrieve",
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        chunks = response.json()["data"]["chunks"]
    except Exception as e:
        logger.error(f"Retrieval error: {e}")

    if run_logger is not None:
        try:
            run_logger.log_retrieval(
                query_used=query,
                fused_chunks=chunks,
                dense_count=0,
                sparse_count=0,
                iteration=iteration,
                iteration_id=iteration_id,
            )
        except Exception as e:
            logger.warning(f"Failed to log retrieval: {e}")

    traces = list(state.get("loop_traces", []))
    if traces:
        traces[-1]["retrieved_chunk_ids"] = [c.get("chunk_id", "unknown") for c in chunks]
    return chunks, traces


def _planner_catalog() -> str:
    catalog = tool_client.fetch_tool_catalog()
    filtered = [t for t in catalog if t.get("name") != "markdown_to_pdf"]
    return json.dumps(filtered, indent=2)


def _run_tools_branch(state: GraphState) -> Dict[str, Any]:
    _emit_stage(state, "tool_planning", "active")
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1
    query = state.get("rewritten_query", state.get("query", ""))
    web_search_enabled = bool(state.get("web_search_enabled"))

    planner = ToolPlanner()
    plan = planner.plan(query, _planner_catalog(), run_logger=run_logger, iteration=iteration)
    _emit_stage(state, "tool_planning", "complete", {"planned_tools": [p.get("tool") for p in plan]})

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    web_search_skipped = False
    session_id = state.get("session_id", "")
    run_id = run_logger.run_id if run_logger is not None else None

    for item in plan:
        tool_name = str(item.get("tool", ""))
        arguments = item.get("arguments") if isinstance(item.get("arguments"), dict) else {}
        stage = f"tool:{tool_name}"
        _emit_stage(state, stage, "active", {"tool": tool_name})

        if tool_name == tool_client.WEB_SEARCH_TOOL and not web_search_enabled:
            web_search_skipped = True
            if run_logger is not None:
                run_logger.log_tool_call(
                    tool_name, skipped=True, iteration=iteration,
                )
            _emit_stage(state, stage, "complete", {"skipped": True})
            continue

        started = time.monotonic()
        try:
            payload = tool_client.execute_tool(
                tool=tool_name,
                arguments=arguments,
                web_search_enabled=web_search_enabled,
                session_id=session_id,
                run_id=run_id,
            )
            latency_ms = int((time.monotonic() - started) * 1000)
            if payload.get("skipped"):
                if tool_name == tool_client.WEB_SEARCH_TOOL:
                    web_search_skipped = True
                if run_logger is not None:
                    run_logger.log_tool_call(
                        tool_name, skipped=True, iteration=iteration, latency_ms=latency_ms,
                    )
                _emit_stage(state, stage, "complete", {"skipped": True})
                continue
            if payload.get("success"):
                results.append({"tool": tool_name, "result": payload.get("result")})
                if run_logger is not None:
                    run_logger.log_tool_call(
                        tool_name, success=True, iteration=iteration, latency_ms=latency_ms,
                    )
                _emit_stage(state, stage, "complete", {"success": True})
            else:
                msg = payload.get("error_message") or "tool failed"
                errors.append(f"{tool_name}: {msg}")
                if run_logger is not None:
                    run_logger.log_tool_call(
                        tool_name,
                        success=False,
                        error_message=msg,
                        iteration=iteration,
                        latency_ms=latency_ms,
                    )
                _emit_stage(state, stage, "complete", {"success": False, "error": msg})
        except Exception as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            errors.append(f"{tool_name}: {exc}")
            if run_logger is not None:
                run_logger.log_tool_call(
                    tool_name,
                    success=False,
                    error_message=str(exc),
                    iteration=iteration,
                    latency_ms=latency_ms,
                )
            _emit_stage(state, stage, "complete", {"success": False, "error": str(exc)})

    updates: Dict[str, Any] = {
        "tool_plan": plan,
        "tool_results": results,
        "tool_errors": errors,
        "web_search_skipped": web_search_skipped,
    }
    if web_search_skipped:
        updates["tool_notice"] = tool_client.WEB_SEARCH_SKIPPED_NOTICE
        updates["tool_notice_code"] = "WEB_SEARCH_SKIPPED"
    return updates


def external_context_node(state: GraphState) -> GraphState:
    with ThreadPoolExecutor(max_workers=2) as pool:
        tools_future = pool.submit(_run_tools_branch, state)
        retrieve_future = pool.submit(_fetch_retrieval_chunks, state)
        tool_updates = tools_future.result()
        chunks, traces = retrieve_future.result()

    _emit_stage(state, "retrieving", "active", {"query": state.get("rewritten_query", "")})
    _emit_stage(state, "retrieving", "complete", {
        "query": state.get("rewritten_query", ""),
        "chunk_count": len(chunks),
        "chunks": _chunk_previews(chunks),
    })
    return {
        **tool_updates,
        "retrieved_chunks": chunks,
        "loop_traces": traces,
    }


def retrieve_node(state: GraphState) -> GraphState:
    _emit_stage(state, "retrieving", "active", {
        "query": state.get("rewritten_query", ""),
    })
    chunks, traces = _fetch_retrieval_chunks(state)
    _emit_stage(state, "retrieving", "complete", {
        "query": state.get("rewritten_query", ""),
        "chunk_count": len(chunks),
        "chunks": _chunk_previews(chunks),
    })
    return {"retrieved_chunks": chunks, "loop_traces": traces}

def draft_node(state: GraphState) -> GraphState:
    _emit_stage(state, "drafting", "active")
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1

    generator = DraftGenerator()
    draft = generator.generate(
        state.get("rewritten_query", ""),
        state.get("retrieved_chunks", []),
        tool_results=state.get("tool_results", []),
        run_logger=run_logger,
        iteration=iteration,
    )
    draft = normalize_kb_miss_response(
        draft,
        web_search_enabled=bool(state.get("web_search_enabled")),
        chunks=state.get("retrieved_chunks", []),
        tool_results=state.get("tool_results", []),
    )
    _emit_stage(state, "drafting", "complete", {"draft_answer": draft})
    return {"draft_answer": draft}

def judge_node(state: GraphState) -> GraphState:
    _emit_stage(state, "judging", "active")
    run_logger = state.get("run_logger")
    iteration = state.get("retry_count", 0) + 1
    iteration_id = state.get("current_iteration_id")

    judge = DecisionJudge()
    result = judge.evaluate(
        state.get("rewritten_query", ""),
        state.get("draft_answer", ""),
        state.get("retrieved_chunks", []),
        tool_results=state.get("tool_results", []),
        run_logger=run_logger,
        iteration=iteration,
    )

    current_retries = state.get("retry_count", 0)
    traces = state.get("loop_traces", [])

    status = result.get("status", "FAIL")
    reasoning = result.get("reasoning", "")

    if traces:
        traces[-1]["judge_status"] = status
        traces[-1]["judge_reasoning"] = reasoning

    # Update iteration row with judge outcome
    if run_logger is not None and iteration_id is not None:
        try:
            run_logger.update_iteration(
                iteration_id=iteration_id,
                judge_status=status,
                judge_reasoning=reasoning,
            )
        except Exception as e:
            logger.warning(f"Failed to update iteration: {e}")

    reached_max = (status == "FAIL" and current_retries >= 2)
    will_retry = status == "FAIL" and current_retries < 2

    _emit_stage(state, "judging", "complete", {
        "judge_status": status,
        "judge_reasoning": reasoning,
        "retry_count": current_retries + 1,
        "will_retry": will_retry,
        "reached_max_retries": reached_max,
        "loop_traces": traces,
    })

    return {
        "judge_status": status,
        "judge_reasoning": reasoning,
        "retry_count": current_retries + 1,
        "loop_traces": traces,
        "final_answer": state.get("draft_answer", ""),
        "reached_max_retries": reached_max
    }

# ---------------------------------------------------------------------------
# Conditional Edges
# ---------------------------------------------------------------------------
def route_after_orchestrator(state: GraphState) -> str:
    if state.get("classification") == "SIMPLE":
        return "simple"
    if state.get("classification") == "TOOL":
        return "external"
    return "knowledge"

def route_after_judge(state: GraphState) -> str:
    status = state.get("judge_status", "FAIL")
    retries = state.get("retry_count", 0)

    if status == "PASS":
        return "pass"
    elif retries >= 3:
        return "max_retries"
    else:
        return "retry"


# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------
def build_graph():
    workflow = StateGraph(GraphState)

    # Add Nodes
    workflow.add_node("compressor", compressor_node)
    workflow.add_node("rewriter", rewrite_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("simple_responder", simple_responder_node)
    workflow.add_node("external_context", external_context_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("drafter", draft_node)
    workflow.add_node("judge", judge_node)

    # Entry point: eager snapshot maintenance before rewrite
    workflow.set_entry_point("compressor")

    # Edges
    workflow.add_edge("compressor", "rewriter")
    workflow.add_edge("rewriter", "orchestrator")

    workflow.add_conditional_edges(
        "orchestrator",
        route_after_orchestrator,
        {
            "simple": "simple_responder",
            "knowledge": "retriever",
            "external": "external_context",
        }
    )

    workflow.add_edge("simple_responder", END)
    workflow.add_edge("external_context", "drafter")

    workflow.add_edge("retriever", "drafter")
    workflow.add_edge("drafter", "judge")

    workflow.add_conditional_edges(
        "judge",
        route_after_judge,
        {
            "pass": END,
            "max_retries": END,
            "retry": "rewriter"  # Loop back to rewrite (or retrieve) if failed
        }
    )

    # Compile
    return workflow.compile()


# ---------------------------------------------------------------------------
# Execution Helper
# ---------------------------------------------------------------------------
def _build_citations(chunks: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    citations = []
    for chunk in chunks:
        meta = chunk.get("metadata", {}) if isinstance(chunk.get("metadata"), dict) else {}
        doc = chunk.get("document", "") or ""
        citations.append(
            {
                "chunk_id": str(chunk.get("chunk_id", "unknown")),
                "title": str(meta.get("title", chunk.get("title", ""))),
                "snippet": doc[:240] + ("…" if len(doc) > 240 else ""),
            }
        )
    return citations


def run_pipeline(
    query: str,
    context_messages: Optional[List[Dict[str, str]]] = None,
    session_id: str = "",
    snapshot: str = "",
    snapshot_turn_count: int = 0,
    project_id: str | None = None,
    user_id: str | None = None,
    web_search_enabled: bool = False,
) -> dict[str, Any]:
    """Run the full RAG pipeline."""
    if context_messages is None:
        context_messages = []

    app = build_graph()

    with PipelineRunLogger(original_query=query, session_id=session_id) as run_logger:
        initial_state: GraphState = {
            "query": query,
            "all_messages": context_messages,
            "snapshot": snapshot,
            "snapshot_turn_count": snapshot_turn_count,
            "context_messages": [],
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "run_logger": run_logger,
            "retry_count": 0,
            "loop_traces": [],
            "current_iteration_id": None,
            "web_search_enabled": web_search_enabled,
            "tool_plan": [],
            "tool_results": [],
            "tool_errors": [],
            "tool_notice": None,
            "tool_notice_code": None,
            "web_search_skipped": False,
        }

        result = app.invoke(initial_state)

        answer = result.get("final_answer", "Error: No answer generated.")
        result_snapshot = result.get("snapshot", snapshot)
        result_turn_count = result.get("snapshot_turn_count", snapshot_turn_count)

        if result.get("reached_max_retries"):
            answer += "\n\nWARNING: No decisive answer was found in the available sources. This result should be independently verified."

        snapshot_token_count = len(result_snapshot.split()) if result_snapshot else 0

        try:
            run_logger.finish(
                classification=result.get("classification", "UNKNOWN"),
                total_iterations=result.get("retry_count", 0),
                final_answer=answer,
                reached_max_retries=bool(result.get("reached_max_retries")),
                snapshot_text=result_snapshot,
                snapshot_token_count=snapshot_token_count,
            )
        except Exception as e:
            logger.error(f"Failed to finalize run log: {e}")

        if session_id:
            complete_event: Dict[str, Any] = {
                "type": "pipeline_complete",
                "reply": answer,
                "classification": result.get("classification", "UNKNOWN"),
                "total_iterations": result.get("retry_count", 0),
                "loop_traces": result.get("loop_traces", []),
                "reached_max_retries": bool(result.get("reached_max_retries")),
                "snapshot": result_snapshot,
            }
            if result.get("tool_notice"):
                complete_event["tool_notice"] = result.get("tool_notice")
                complete_event["tool_notice_code"] = result.get("tool_notice_code")
            emit_event(session_id, complete_event)
            if result.get("tool_notice"):
                emit_event(
                    session_id,
                    {
                        "type": "tool_notice",
                        "code": result.get("tool_notice_code"),
                        "message": result.get("tool_notice"),
                    },
                )

        return {
            "reply": answer,
            "snapshot": result_snapshot,
            "snapshot_turn_count": result_turn_count,
            "citations": _build_citations(result.get("retrieved_chunks", [])),
            "run_id": run_logger.run_id,
            "classification": result.get("classification", "UNKNOWN"),
            "reached_max_retries": bool(result.get("reached_max_retries")),
            "tool_results": result.get("tool_results", []),
            "tool_errors": result.get("tool_errors", []),
            "tool_notice": result.get("tool_notice"),
            "tool_notice_code": result.get("tool_notice_code"),
            "web_search_skipped": bool(result.get("web_search_skipped")),
        }
