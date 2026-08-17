# IMPLEMENTATION_PLAN: Snapshot Context Maintenance

**Feature:** Enhancement 1 — Snapshot Context Maintenance (`ENHANCEMENTS.md` L18–122)
**Target Codebase:** Pitchside `src/`
**Methodology:** Test-Driven Development (TDD) — tests written before implementation for each unit

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture Decisions (Resolved)](#2-architecture-decisions-resolved)
3. [File Change Map](#3-file-change-map)
4. [Implementation Phases](#4-implementation-phases)
   - [Phase 1: ConversationContext Extension](#phase-1-conversationcontext-extension)
   - [Phase 2: Database Migration](#phase-2-database-migration)
   - [Phase 3: Prompts](#phase-3-prompts)
   - [Phase 4: SnapshotCompressor (LLM Component)](#phase-4-snapshotcompressor-llm-component)
   - [Phase 5: GraphState Extension](#phase-5-graphstate-extension)
   - [Phase 6: LangGraph Node — snapshot_node](#phase-6-langgraph-node--snapshot_node)
   - [Phase 7: Graph Wiring](#phase-7-graph-wiring)
   - [Phase 8: QueryRewriter Update](#phase-8-queryrewriter-update)
   - [Phase 9: api.py Integration](#phase-9-apipy-integration)
   - [Phase 10: DB Logging](#phase-10-db-logging)
5. [Token Counting Utility](#5-token-counting-utility)
6. [Environment Variables](#6-environment-variables)
7. [TDD Test Plan](#7-tdd-test-plan)
8. [Dependency Audit](#8-dependency-audit)
9. [Rollout Checklist](#9-rollout-checklist)

---

## 1. Overview

The current `QueryRewriter` only sees the last 10 messages from `session.get_context_messages()`. Any earlier conversation history is silently dropped, creating a hard amnesia boundary. This is especially problematic in long football analysis sessions where users reference entities from earlier in the conversation.

This feature introduces a **two-tier memory model**:

- **Hot Context:** The last `HOT_CONTEXT_WINDOW` (default: 10) messages, passed verbatim to the `QueryRewriter` — unchanged from today.
- **Cold Context (Snapshot):** All messages older than the hot window are compressed by an LLM call into dense factual prose and stored as `snapshot` on `ConversationContext`. The snapshot is passed alongside hot context to the `QueryRewriter`.

Compression is **eager**: it runs synchronously at the start of every pipeline invocation (in a dedicated LangGraph node before `rewriter`) so the snapshot is always current. No deferred updates, no dirty flags.

---

## 2. Architecture Decisions (Resolved)

| Question | Decision |
|---|---|
| Compression model (step key) | Reuse `"orchestrator"` step key → `openai/gpt-oss-20b` via `GROQ_MODEL_MAP` |
| Compressor placement in graph | Separate LangGraph node (`snapshot_node`) inserted before `rewriter` |
| Where snapshot lives (session-side) | `ConversationContext` gains `snapshot: str` and `snapshot_turn_count: int` fields |
| Where snapshot lives (graph-side) | `GraphState` gains `snapshot` and `snapshot_turn_count` fields |
| How snapshot reaches `run_pipeline()` | Passed as explicit parameters alongside `context_messages`; stored in `GraphState` |
| Compression prompt location | `prompts.txt` as `[SNAPSHOT_COMPRESSOR_SYSTEM]` / `[SNAPSHOT_COMPRESSOR_USER]` |
| Rewriter prompt update | Existing `[REWRITER_SYSTEM]` / `[REWRITER_USER]` blocks updated in place |
| DB migration | `ALTER TABLE pipeline_runs ADD COLUMN snapshot_text TEXT` in `init_db()` via try/except |
| DB columns added | `snapshot_text TEXT` only (not `snapshot_token_count`) |
| Token counting | `tiktoken` (already a transitive dep via `langchain_text_splitters`) |
| 429 handling | Exponential backoff already implemented in `_call_groq()` — no new logic needed |
| Fallback on compressor failure | None — exception propagates; backoff in `_call_groq()` handles transient failures |
| Testing methodology | TDD — each unit has tests written before implementation |

---

## 3. File Change Map

```
src/
├── context.py          MODIFY  — add snapshot, snapshot_turn_count fields
├── prompts.txt         MODIFY  — add SNAPSHOT_COMPRESSOR_SYSTEM/USER; update REWRITER_USER
├── llm_components.py   MODIFY  — add SnapshotCompressor class
├── graph.py            MODIFY  — add snapshot_node, extend GraphState, rewire entry point
├── db_logger.py        MODIFY  — ALTER TABLE migration + log snapshot_text in finish()
├── api.py              MODIFY  — pass snapshot + snapshot_turn_count into run_pipeline()

tests/                  CREATE (new directory)
├── test_context.py
├── test_snapshot_compressor.py
├── test_snapshot_node.py
├── test_db_logger.py
└── test_api_integration.py
```

No new Python packages required.

---

## 4. Implementation Phases

---

### Phase 1: ConversationContext Extension

**File:** `src/context.py`

**What changes:**

`ConversationContext` gains two new fields: `snapshot` (the compressed prose summary) and `snapshot_turn_count` (how many messages from the full history were included in the last compression, used to detect whether new messages have aged out since the last run).

The existing `rolling_summary` field is a dead stub — it is removed and replaced by `snapshot` to avoid confusion. The `add_message()` return value (the aged-out message) is left in place; it is no longer used by the compressor directly (the compressor re-derives aged messages from `self.messages[:-HOT_CONTEXT_WINDOW]`), but removing it would be a separate cleanup.

**Exact diff:**

```python
# BEFORE
class ConversationContext(BaseModel):
    session_id: str
    messages: List[Message] = Field(default_factory=list)
    rolling_summary: str = ""
    message_count: int = 0

# AFTER
class ConversationContext(BaseModel):
    session_id: str
    messages: List[Message] = Field(default_factory=list)
    snapshot: str = ""
    snapshot_turn_count: int = 0
    message_count: int = 0
```

`get_context_messages()` is unchanged. `add_message()` is unchanged.

---

### Phase 2: Database Migration

**File:** `src/db_logger.py`

**What changes:**

`init_db()` is called on module import and runs `CREATE TABLE IF NOT EXISTS` for all tables. We need to add `snapshot_text TEXT` to `pipeline_runs`. Because the table may already exist in production (no column yet), we use `ALTER TABLE` wrapped in a try/except on `OperationalError` — SQLite raises this if the column already exists, so this is idempotent.

**Add inside `init_db()` after the `pipeline_runs` CREATE block:**

```python
# Migration: add snapshot_text column if not present
try:
    conn.execute("ALTER TABLE pipeline_runs ADD COLUMN snapshot_text TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass  # Column already exists — safe to ignore
```

**Update `PipelineRunLogger.finish()` signature:**

```python
def finish(
    self,
    classification: str = "UNKNOWN",
    total_iterations: int = 0,
    final_answer: str = "",
    reached_max_retries: bool = False,
    snapshot_text: str = "",          # NEW
):
    elapsed = int(time.monotonic() * 1000) - self._start_ms
    conn = self._connect()
    try:
        conn.execute(
            """UPDATE pipeline_runs
               SET classification=?, total_iterations=?, final_answer=?,
                   reached_max_retries=?, finished_at=?, duration_ms=?,
                   snapshot_text=?
               WHERE id=?""",
            (
                classification, total_iterations, final_answer,
                int(reached_max_retries), _now(), elapsed,
                snapshot_text,
                self.run_id
            )
        )
        conn.commit()
    finally:
        conn.close()
```

---

### Phase 3: Prompts

**File:** `src/prompts.txt`

#### 3a. Add Snapshot Compressor prompts (append to end of file)

```
[SNAPSHOT_COMPRESSOR_SYSTEM]
You are a memory compressor for a football-focused conversational assistant.
Your job is to maintain a running factual summary of conversation history that has
scrolled out of the active context window.

[SNAPSHOT_COMPRESSOR_USER]
EXISTING SUMMARY (may be empty on first compression):
{existing_snapshot}

NEW MESSAGES TO INCORPORATE:
{newly_aged_messages}

Update the summary to incorporate the new messages. The summary must:
- Be written in dense, factual prose. No bullet points.
- Preserve all specific football entities mentioned: player names, clubs, seasons,
  statistics, formations, match results, and any user preferences or hypotheses.
- Discard pleasantries, filler, and meta-commentary about the conversation itself.
- Target length: {snapshot_max_tokens} tokens maximum. Be ruthlessly concise.

Return only the updated summary. No preamble.
```

#### 3b. Update existing REWRITER_USER block in place

Add a `{snapshot}` section at the top of the user template, before `Conversation History`:

```
[REWRITER_USER]
[CONVERSATION SNAPSHOT]
{snapshot}

[RECENT MESSAGES]
{history_text}

[CURRENT QUERY]
{query}

Rewrite the current query into a fully self-contained, standalone question that
incorporates all relevant context from both the snapshot and recent messages.
Return only the rewritten query. No explanation.
```

Note: `{snapshot}` will be an empty string when no snapshot exists yet, which is valid.

---

### Phase 4: SnapshotCompressor (LLM Component)

**File:** `src/llm_components.py`

**What changes:**

Add a `SnapshotCompressor` class. It follows the same pattern as `QueryRewriter`, `Orchestrator`, etc.

Key decisions reflected in the implementation:
- Uses `step="orchestrator"` so `GROQ_MODEL_MAP` routes it to `openai/gpt-oss-20b`.
- Reads `HOT_CONTEXT_WINDOW` and `SNAPSHOT_MAX_TOKENS` from environment.
- Derives `aged_messages` as `messages[:-HOT_CONTEXT_WINDOW]`. If there are fewer messages than `HOT_CONTEXT_WINDOW`, `aged_messages` is empty and compression is skipped.
- Detects whether re-compression is needed by comparing `len(aged_messages)` to `snapshot_turn_count`.
- Formats `newly_aged_messages` as `role: content` lines (same format as `history_for_llm` in the rewriter).

**Add at the top of `llm_components.py` (with other imports):**

```python
import tiktoken
```

**Add token counting helper (private, near `_strip_think_tags`):**

```python
_TIKTOKEN_ENCODING = None

def _count_tokens(text: str) -> int:
    """Approximate token count using tiktoken cl100k_base encoding."""
    global _TIKTOKEN_ENCODING
    if _TIKTOKEN_ENCODING is None:
        _TIKTOKEN_ENCODING = tiktoken.get_encoding("cl100k_base")
    return len(_TIKTOKEN_ENCODING.encode(text))
```

**Add environment variable reads (near other env vars at top of module):**

```python
HOT_CONTEXT_WINDOW = int(os.environ.get("HOT_CONTEXT_WINDOW", "10"))
SNAPSHOT_MAX_TOKENS = int(os.environ.get("SNAPSHOT_MAX_TOKENS", "300"))
```

**Add SnapshotCompressor class (after the existing `QueryRewriter` class):**

```python
class SnapshotCompressor:
    """
    Maintains a running compressed summary (snapshot) of conversation history
    that has aged out of the hot context window.

    Compression is triggered only when new messages have aged out since the last
    compression, determined by comparing len(aged_messages) to snapshot_turn_count.

    Returns (new_snapshot: str, new_snapshot_turn_count: int).
    If no compression is needed, returns the existing values unchanged.
    """

    def compress(
        self,
        messages: List[Dict[str, str]],
        existing_snapshot: str,
        snapshot_turn_count: int,
        run_logger=None,
        iteration: int = 0,
    ) -> tuple[str, int]:
        aged_messages = messages[:-HOT_CONTEXT_WINDOW] if len(messages) > HOT_CONTEXT_WINDOW else []

        if not aged_messages:
            # Not enough messages to have any aged out — nothing to compress
            return existing_snapshot, snapshot_turn_count

        if len(aged_messages) == snapshot_turn_count:
            # Snapshot already covers all aged messages — skip
            return existing_snapshot, snapshot_turn_count

        # New messages have aged out since last compression — re-compress
        newly_aged = aged_messages[snapshot_turn_count:]  # only the new ones
        newly_aged_text = "\n".join(
            [f"{m['role']}: {m['content']}" for m in newly_aged]
        )

        system_prompt, user_template = get_prompt_parts("SNAPSHOT_COMPRESSOR")
        user_content = user_template.format(
            existing_snapshot=existing_snapshot,
            newly_aged_messages=newly_aged_text,
            snapshot_max_tokens=SNAPSHOT_MAX_TOKENS,
        )

        new_snapshot = invoke_llm(
            user_content,
            model_name=MODEL_ORCHESTRATOR,   # unused in Groq path; step drives model selection
            step="orchestrator",             # routes to openai/gpt-oss-20b via GROQ_MODEL_MAP
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )

        return new_snapshot, len(aged_messages)
```

---

### Phase 5: GraphState Extension

**File:** `src/graph.py`

**What changes:**

Two new fields added to `GraphState`:

```python
class GraphState(TypedDict, total=False):
    # ... existing fields ...

    # Snapshot context (two-tier memory)
    snapshot: str           # NEW — compressed summary of messages older than hot window
    snapshot_turn_count: int  # NEW — number of aged messages covered by current snapshot
```

---

### Phase 6: LangGraph Node — `snapshot_node`

**File:** `src/graph.py`

**What changes:**

Add a new node function. It reads the `snapshot` and `snapshot_turn_count` from `GraphState` (passed in by `api.py` via `run_pipeline()`), calls `SnapshotCompressor.compress()`, and writes the updated values back to state. The rewriter node then reads `snapshot` from state.

```python
def snapshot_node(state: GraphState) -> GraphState:
    """
    Eagerly compresses aged conversation history into the snapshot before
    every pipeline invocation. No-ops if the snapshot is already current.
    """
    run_logger = state.get("run_logger")

    compressor = SnapshotCompressor()
    new_snapshot, new_count = compressor.compress(
        messages=state.get("context_messages", []),
        existing_snapshot=state.get("snapshot", ""),
        snapshot_turn_count=state.get("snapshot_turn_count", 0),
        run_logger=run_logger,
        iteration=0,  # pre-loop; not part of a retry iteration
    )

    return {
        "snapshot": new_snapshot,
        "snapshot_turn_count": new_count,
    }
```

**Update `rewrite_node` to pass snapshot to the rewriter:**

```python
def rewrite_node(state: GraphState) -> GraphState:
    run_logger = state.get("run_logger")
    retry_count = state.get("retry_count", 0)
    iteration = retry_count + 1

    rewriter = QueryRewriter()
    query = state.get("query", "")
    context = state.get("context_messages", [])
    snapshot = state.get("snapshot", "")          # NEW

    rewritten = rewriter.rewrite(
        query, context, snapshot=snapshot,         # NEW — pass snapshot
        run_logger=run_logger, iteration=iteration
    )
    # ... rest unchanged ...
```

---

### Phase 7: Graph Wiring

**File:** `src/graph.py` — `build_graph()`

**What changes:**

Insert `snapshot_node` as the new entry point. The chain becomes:

```
snapshot_node → rewriter → orchestrator → ...
```

```python
def build_graph():
    workflow = StateGraph(GraphState)

    # Add Nodes
    workflow.add_node("snapshot", snapshot_node)   # NEW
    workflow.add_node("rewriter", rewrite_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("simple_responder", simple_responder_node)
    workflow.add_node("retriever", retrieve_node)
    workflow.add_node("drafter", draft_node)
    workflow.add_node("judge", judge_node)

    # Entry point is now snapshot_node
    workflow.set_entry_point("snapshot")           # CHANGED from "rewriter"

    # Snapshot always flows into rewriter
    workflow.add_edge("snapshot", "rewriter")      # NEW

    # All other edges unchanged
    workflow.add_edge("rewriter", "orchestrator")
    # ... rest unchanged ...

    # IMPORTANT: On retry, judge loops back to rewriter (NOT snapshot)
    # The snapshot is already current; re-compressing on retries is unnecessary
    # and would waste TPM budget.
    workflow.add_conditional_edges(
        "judge",
        route_after_judge,
        {
            "pass": END,
            "max_retries": END,
            "retry": "rewriter"   # unchanged — skips snapshot on retry loops
        }
    )

    return workflow.compile()
```

**Why retry loops bypass `snapshot_node`:** Compression is per-request, not per-retry. The snapshot was already updated at the start of this request. Re-running the compressor on retries would make a redundant LLM call with identical input and waste ~800 tokens of TPM budget.

---

### Phase 8: QueryRewriter Update

**File:** `src/llm_components.py` — `QueryRewriter.rewrite()`

**What changes:**

Accept `snapshot: str = ""` parameter and include it in the prompt formatting. Because the `[REWRITER_USER]` template now has `{snapshot}` as a placeholder, this is passed through to `user_template.format(...)`.

```python
class QueryRewriter:
    def rewrite(
        self,
        query: str,
        context_messages: List[Dict[str, str]],
        snapshot: str = "",           # NEW
        run_logger=None,
        iteration: int = 0,
    ) -> str:
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in context_messages])
        system_prompt, user_template = get_prompt_parts("REWRITER")
        user_content = user_template.format(
            snapshot=snapshot,         # NEW
            history_text=history_text,
            query=query,
        )
        return invoke_llm(
            user_content,
            model_name=MODEL_GENERATOR,
            step="rewriter",
            run_logger=run_logger,
            iteration=iteration,
            system_prompt=system_prompt,
        )
```

---

### Phase 9: api.py Integration

**File:** `src/api.py`

**What changes:**

Three things:

1. After `session.add_message(user_msg)`, read `session.snapshot` and `session.snapshot_turn_count` and pass them into `run_pipeline()`.
2. After `run_pipeline()` returns, write the updated snapshot values back to the session object.
3. Extend `run_pipeline()` signature in `graph.py` to accept and propagate these values.

**`run_pipeline()` signature update** (`graph.py`):

```python
def run_pipeline(
    query: str,
    context_messages: Optional[List[Dict[str, str]]] = None,
    session_id: str = "",
    snapshot: str = "",                # NEW
    snapshot_turn_count: int = 0,      # NEW
) -> tuple[str, str, int]:             # returns (answer, new_snapshot, new_snapshot_turn_count)
```

**Return value change:** `run_pipeline()` currently returns `str`. It now returns a 3-tuple `(answer, new_snapshot, new_snapshot_turn_count)` so the caller can persist the updated snapshot back to `ConversationContext`.

**`initial_state` in `run_pipeline()`:**

```python
initial_state: GraphState = {
    "query": query,
    "context_messages": context_messages,
    "session_id": session_id,
    "run_logger": run_logger,
    "retry_count": 0,
    "loop_traces": [],
    "current_iteration_id": None,
    "snapshot": snapshot,                  # NEW
    "snapshot_turn_count": snapshot_turn_count,  # NEW
}
```

**After `app.invoke(initial_state)`:**

```python
new_snapshot = result.get("snapshot", snapshot)
new_snapshot_turn_count = result.get("snapshot_turn_count", snapshot_turn_count)
```

**Return at end of `run_pipeline()`:**

```python
return answer, new_snapshot, new_snapshot_turn_count
```

**`/api/chat` handler update:**

```python
@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    session = get_session(request.session_id)

    user_msg = Message(role="user", content=request.message, timestamp=datetime.now(timezone.utc))
    session.add_message(user_msg)

    context_msgs = session.get_context_messages()
    history_for_llm = [m.model_dump() for m in context_msgs[:-1]]

    try:
        reply, new_snapshot, new_count = run_pipeline(      # CHANGED — unpack 3-tuple
            query=request.message,
            context_messages=history_for_llm,
            session_id=request.session_id,
            snapshot=session.snapshot,                       # NEW
            snapshot_turn_count=session.snapshot_turn_count, # NEW
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Persist updated snapshot back to session
    session.snapshot = new_snapshot                          # NEW
    session.snapshot_turn_count = new_count                 # NEW

    bot_msg = Message(role="assistant", content=reply, timestamp=datetime.now(timezone.utc))
    session.add_message(bot_msg)

    return ChatResponse(reply=reply)
```

**Note on `history_for_llm`:** The existing code builds this as `context_msgs[:-1]` to exclude the just-added user message. This is intentional and unchanged — the snapshot compressor sees the full `context_messages` list (which includes the just-added message indirectly through the session object), but the rewriter's `history_text` excludes it to avoid duplication with the `{query}` field in the prompt.

---

### Phase 10: DB Logging

**File:** `src/graph.py` — `run_pipeline()`

**What changes:**

Pass `snapshot_text` to `run_logger.finish()`:

```python
run_logger.finish(
    classification=result.get("classification", "UNKNOWN"),
    total_iterations=result.get("retry_count", 0),
    final_answer=answer,
    reached_max_retries=bool(result.get("reached_max_retries")),
    snapshot_text=result.get("snapshot", ""),    # NEW
)
```

---

## 5. Token Counting Utility

Token counting is used in two places:

1. **`SnapshotCompressor`:** The `{snapshot_max_tokens}` value is injected into the prompt as an instruction to the model. The model is responsible for honoring it — we do not truncate the output ourselves. This is intentional: the model's self-truncation is "soft" and may occasionally exceed the cap slightly, which is acceptable.

2. **`db_logger.py` (optional instrumentation):** If you later want to log `snapshot_token_count`, use `_count_tokens(snapshot_text)` before calling `finish()`. This column is not being added in this implementation (decision: `snapshot_text` only), so no action needed now.

The `_count_tokens()` helper uses `tiktoken`'s `cl100k_base` encoding (GPT-3.5/4 tokenizer), which is a reasonable approximation for Qwen and GPT-OSS models. It is lazy-initialized on first call to avoid import-time overhead.

---

## 6. Environment Variables

Both new variables should be added to `.env.example` and documented:

| Variable | Default | Description |
|---|---|---|
| `HOT_CONTEXT_WINDOW` | `10` | Number of most recent messages passed verbatim to the QueryRewriter |
| `SNAPSHOT_MAX_TOKENS` | `300` | Target maximum token length instructed to the compression model |

These are read at module import time in `llm_components.py` and do not require a server restart to change — but since they are read once, a restart is needed for changes to take effect at runtime.

---

## 7. TDD Test Plan

All tests are written **before** the implementation code for each phase. Tests live in `tests/`.

### `tests/test_context.py` — Phase 1

```
test_snapshot_fields_default_empty
    ConversationContext() has snapshot="" and snapshot_turn_count=0

test_snapshot_persists_assignment
    Assign snapshot and snapshot_turn_count; assert they round-trip correctly

test_existing_fields_unchanged
    session_id, messages, message_count, add_message(), get_context_messages()
    all behave identically to pre-feature baseline
```

### `tests/test_snapshot_compressor.py` — Phase 4

Mock `invoke_llm` throughout to avoid real API calls.

```
test_no_compression_fewer_than_window
    messages has 5 items, HOT_CONTEXT_WINDOW=10
    compress() returns (existing_snapshot, 0) unchanged
    invoke_llm NOT called

test_no_compression_when_current
    messages has 15 items, snapshot_turn_count=5 (5 aged out, snapshot already covers them)
    compress() returns unchanged
    invoke_llm NOT called

test_compression_triggered_when_new_aged_out
    messages has 15 items, snapshot_turn_count=3
    aged_messages = messages[:5]; newly_aged = messages[3:5]
    invoke_llm IS called once with step="orchestrator"
    returns (mocked_new_snapshot, 5)

test_newly_aged_messages_formatted_correctly
    Verify the user_content passed to invoke_llm contains "role: content" lines
    for only the newly aged messages (not already-summarized ones)

test_existing_snapshot_passed_to_prompt
    Verify existing_snapshot is present in the formatted user_content

test_snapshot_max_tokens_injected
    Verify snapshot_max_tokens appears in formatted user_content

test_compression_on_first_ever_call
    messages has 12 items, snapshot_turn_count=0, existing_snapshot=""
    All 2 aged messages (indices 0 and 1) are passed as newly_aged
    Returns (new_snapshot, 2)
```

### `tests/test_snapshot_node.py` — Phase 6

Mock `SnapshotCompressor.compress` throughout.

```
test_snapshot_node_updates_state
    GraphState with context_messages (15), snapshot="old", snapshot_turn_count=3
    compress() mocked to return ("new_snapshot", 5)
    snapshot_node() returns state with snapshot="new_snapshot", snapshot_turn_count=5

test_snapshot_node_no_op_when_current
    compress() returns unchanged values
    snapshot_node() returns same snapshot and count

test_snapshot_node_is_entry_point
    build_graph() entry node is "snapshot" (not "rewriter")
    Edge "snapshot" → "rewriter" exists

test_retry_loop_does_not_revisit_snapshot
    Verify "retry" conditional edge maps to "rewriter", not "snapshot"
```

### `tests/test_db_logger.py` — Phase 2

Use a temp in-memory or temp-file SQLite database.

```
test_snapshot_text_column_exists_after_init_db
    Call init_db() on fresh DB
    PRAGMA table_info(pipeline_runs) includes snapshot_text column

test_migration_idempotent
    Call init_db() twice
    No exception raised; snapshot_text column present exactly once

test_finish_writes_snapshot_text
    PipelineRunLogger.__enter__()
    finish(snapshot_text="test summary")
    SELECT snapshot_text FROM pipeline_runs WHERE id=run_id
    Asserts "test summary"

test_finish_snapshot_text_defaults_empty
    finish() called without snapshot_text
    Column value is NULL or ""
```

### `tests/test_api_integration.py` — Phase 9

Use FastAPI `TestClient`. Mock `run_pipeline` to return a 3-tuple.

```
test_chat_endpoint_passes_snapshot_to_pipeline
    First request: session has snapshot="", count=0
    run_pipeline receives snapshot="", snapshot_turn_count=0

test_chat_endpoint_persists_snapshot_after_response
    run_pipeline mocked to return ("reply", "summary prose", 5)
    After request, session.snapshot == "summary prose"
    session.snapshot_turn_count == 5

test_snapshot_passed_on_second_request
    First request seeds session.snapshot = "old summary"
    Second request: run_pipeline receives snapshot="old summary"

test_new_session_has_empty_snapshot
    get_session() for unknown session_id
    ConversationContext.snapshot == ""
    ConversationContext.snapshot_turn_count == 0
```

---

## 8. Dependency Audit

| Package | Already in project? | Used for |
|---|---|---|
| `tiktoken` | Yes (transitive via `langchain_text_splitters`) | Token counting in `_count_tokens()` |
| `langchain_text_splitters` | Yes | Existing chunking |
| `langgraph` | Yes | Graph orchestration |
| `pydantic` | Yes | `ConversationContext` model |
| `sqlite3` | stdlib | DB migrations |

No new packages needed. No `requirements.txt` changes.

---

## 9. Rollout Checklist

Work through these in order. Each item should be completable before the next, confirmed by passing tests.

- [ ] **Phase 1:** Write `tests/test_context.py` → implement `context.py` changes → all tests pass
- [ ] **Phase 2:** Write `tests/test_db_logger.py` → implement migration in `db_logger.py` → all tests pass
- [ ] **Phase 3:** Add prompts to `prompts.txt` — no tests needed (covered by downstream tests); clear `_prompts_cache` between tests that use `get_prompt_parts()`
- [ ] **Phase 4:** Write `tests/test_snapshot_compressor.py` → implement `SnapshotCompressor` and `_count_tokens` in `llm_components.py` → all tests pass
- [ ] **Phase 5:** Extend `GraphState` TypedDict in `graph.py` — no isolated test; covered by Phase 6 tests
- [ ] **Phase 6:** Write `tests/test_snapshot_node.py` → implement `snapshot_node` and updated `rewrite_node` in `graph.py` → all tests pass
- [ ] **Phase 7:** Wire graph in `build_graph()` → covered by Phase 6 graph wiring tests
- [ ] **Phase 8:** Update `QueryRewriter.rewrite()` signature and prompt formatting → existing rewriter tests should still pass with `snapshot=""` default
- [ ] **Phase 9:** Write `tests/test_api_integration.py` → implement `api.py` and `run_pipeline()` changes → all tests pass
- [ ] **Phase 10:** Wire `snapshot_text` into `run_logger.finish()` → covered by Phase 2 `test_finish_writes_snapshot_text`
- [ ] **Manual smoke test:** Start server, send 15+ messages in one session, verify rewritten queries reference content from early in the conversation, check `trace_logs.db` for non-null `snapshot_text`

---

*Document version: 1.0 — June 2026*
*Covers Enhancement 1 of ENHANCEMENTS.md v1.0 only*
