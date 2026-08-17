# Pitchside Architecture

This document details the end-to-end architecture and key design decisions behind the Pitchside RAG (Retrieval-Augmented Generation) pipeline.

## System Overview

Pitchside is an intelligent, football-focused conversational agent. It utilizes a LangGraph-orchestrated workflow to intelligently parse user queries, retrieve relevant context from a local knowledge base using hybrid search, and generate factually verified responses via a suite of specialized LLMs.

---

## 1. Data Ingestion & Retrieval Pipeline

### Hybrid Search Approach
To ensure high recall across both semantic concepts and exact keyword matches (e.g., specific player names, years, or teams), we utilize a hybrid search approach:
1. **Dense Retrieval (ChromaDB)**: Uses `DefaultEmbeddingFunction` (all-MiniLM-L6-v2) to capture semantic similarity.
2. **Sparse Retrieval (BM25Okapi)**: Captures exact lexical matches. Title fields are heavily boosted (repeated) during chunk indexing to ensure articles strictly matching query names score highly.

### Reciprocal Rank Fusion (RRF)
The results from ChromaDB and BM25 are merged using Reciprocal Rank Fusion. This mathematically combines the rank of a document across both retrieval methods (`score = 1 / (k + rank)`), ensuring that documents appearing high in both lists bubble to the top.

---

## 2. LLM Orchestration Workflow (LangGraph)

The core reasoning loop is modeled as a state machine using **LangGraph**. This allows us to build a self-correcting loop if the model fails to find a good answer on the first try.

### Workflow Nodes

1. **Query Rewriter (`Qwen3.5-2B`)**: 
   Takes the user's raw query and the conversation history, and rewrites it into a standalone, fully self-contained query.
2. **Orchestrator Classifier (`Qwen3.5-0.8B`)**:
   A small, fast model that acts as a router. It classifies the rewritten query as either `SIMPLE` (greetings, small talk) or `KNOWLEDGE` (requires football facts).
3. **Simple Responder (`Qwen3.5-2B`)**:
   If the query is `SIMPLE`, this node immediately replies (bypassing retrieval), drastically reducing latency for conversational pleasantries.
4. **Retriever**:
   If `KNOWLEDGE`, triggers the Hybrid Search (ChromaDB + BM25).
5. **Draft Generator (`Qwen3.5-2B`)**:
   Given the retrieved chunks, generates a draft answer. It is strictly prompted to use *only* the provided context.
6. **Decision Judge (`Qwen3.5-4B`)**:
   Acts as a fact-checker. It evaluates the draft answer against the retrieved chunks to ensure no hallucinations occurred. It returns a JSON object with a `PASS` or `FAIL` status.
   - If **PASS**: The answer is returned to the user.
   - If **FAIL**: The graph loops back to the Query Rewriter (up to a maximum of 3 retries) to attempt a different retrieval angle.

---

## 3. Database Logging & Observability

To monitor, evaluate, and debug the multi-step pipeline, a heavily normalized SQLite database (`trace_logs.db`) is used.

### Schema Design
- **`pipeline_runs`**: High-level tracking of a single user request, total duration, and final classification.
- **`llm_calls`**: Granular logging of *every single API call* made to the LLMs. Includes the exact prompt sent, the raw response (with `<think>` tags), the cleaned response, and the latency.
- **`loop_iterations`**: Tracks the LangGraph retry loops, storing the rewritten queries and the verdict of the Decision Judge.
- **`retrieval_events` & `retrieved_chunks`**: Logs the exact chunks returned by the RRF hybrid search per iteration.

### Concurrency Handling
Because LangGraph executes nodes in separate threads, the `PipelineRunLogger` relies on opening and closing short-lived, thread-local SQLite connections for every log insertion. This ensures thread-safe database writes without encountering SQLite's threading constraints.

---

## 4. API & Frontend

- **Gateway (FastAPI)**: API-only entry point with fixed routes to auth, chat,
  project/knowledge, tools, observability, and pipeline services.
- **Frontend (Next.js)**: `services/web` provides the Pitchside App Router UI.
  Browser HTTP calls use same-origin `/api`; pipeline updates use WebSockets.
- **State**: Chats and account/project metadata persist in Postgres; pipeline
  traces use the shared observability store, and retrieval uses Qdrant + BM25.

---

## Key Design Decisions

1. **Model Specialization (Multi-Agent Routing)**:
   Instead of using one massive model for everything, we use specialized sizes. `0.8B` handles fast binary routing. `2B` handles drafting and rewriting. `4B` acts as the strict judge. This optimizes latency and cost.
2. **Separation of "Think" Tags**:
   Since the Qwen3 models emit `<think>` reasoning blocks, these are stripped programmatically in `invoke_llm()` so the end user only sees the final polished answer. The raw reasoning is preserved in the database for debugging.
3. **Self-Correction Loop**:
   By using a `DecisionJudge` in a LangGraph cycle, the system catches its own hallucinations before the user sees them. If it fails, it can retry retrieval with a slightly different query variation.
4. **Normalized Logging**:
   Storing logs in a normalized SQL schema instead of flat JSON files enables deep analytics (e.g., "What is the average latency of the Orchestrator?" or "How often does the Judge fail the first draft?").
