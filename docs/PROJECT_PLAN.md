# Pitchside — Project Plan

This document breaks down the development of Pitchside into distinct, independently testable phases following **Test-Driven Development (TDD)** principles. 

For each feature, the development loop will be:
1. **Red**: Write a failing test for the expected behavior.
2. **Green**: Write the minimal code to pass the test.
3. **Refactor**: Clean up the code while ensuring tests still pass.

---

## Phase 1: Foundation and Infrastructure Setup
**Objective**: Establish the Python project environment, test framework, and foundational data structures.

- **Tasks**:
  - [ ] Initialize Python environment (e.g., Poetry or venv) and install dependencies including `langgraph`.
  - [ ] Setup `pytest`, `pytest-cov`, and `pytest-mock` for testing.
  - [ ] **TDD**: Write tests for Context Management data structures (`Message`, `ConversationContext`), ensuring full history is retained for the UI.
  - [ ] Implement `Message` and `ConversationContext` schemas, including a helper to fetch the last 10 messages for LLM context.
  - [ ] **TDD**: Write tests for a basic rolling summary logic that identifies messages older than 10 turns.
  - [ ] Implement simple rolling summary storage logic.

---

## Phase 2: Data Ingestion and Processing Layer
**Objective**: Scrape football news articles, filter by date, and chunk them for retrieval.

- **Tasks**:
  - [x] **TDD**: Write tests for fetching article URLs and scraping article content.
  - [x] Implement Web Scraper logic (`fetch_article_urls`, `scrape_article`, `scrape_all`).
  - [x] **TDD**: Write tests for date filtering (last 365 days) and URL deduplication.
  - [x] Implement date filtering and deduplication.
  - [x] **TDD**: Write tests for the Text Chunker (enforcing 512 token size, 64 token overlap).
  - [x] Implement Text Chunker logic.

---

## Phase 3: Retrieval Engine (Dense & Sparse)
**Objective**: Build the hybrid search backend using ChromaDB and BM25.

- **Tasks**:
  - [ ] **TDD**: Write tests for ChromaDB insertion and dense retrieval (mocking Ollama embeddings).
  - [ ] Implement ChromaDB database schema and retrieval queries.
  - [ ] **TDD**: Write tests for BM25 index generation and sparse keyword retrieval.
  - [ ] Implement `rank_bm25` wrapper.
  - [ ] **TDD**: Write tests for the Reciprocal Rank Fusion (RRF) algorithm to ensure correct rank merging.
  - [ ] Implement RRF logic.

---

## Phase 4: Core LLM Components & Routing
**Objective**: Build out the independent LLM components that form the logic pipeline.

- **Tasks**:
  - [ ] **TDD**: Write tests for the Query Rewriter formatting and outputs (mocking Small LLM).
  - [ ] Implement Query Rewriter prompts and execution logic.
  - [ ] **TDD**: Write tests for Orchestrator classification (verifying routing to `SIMPLE` or `KNOWLEDGE`).
  - [ ] Implement Orchestrator prompt and routing logic.
  - [ ] **TDD**: Write tests for Draft Answer Generator (ensuring chunks are passed correctly).
  - [ ] Implement Draft Answer Generator.
  - [ ] **TDD**: Write tests for Decision LLM (Judge), covering `PASS` and `FAIL` evaluations with reasoning.
  - [ ] Implement Decision LLM logic and loop-back mechanism (max 3 retries).
  - [ ] **TDD**: Write tests for Heavy LLM (Refiner) input/output handling.
  - [ ] Implement Heavy LLM final answer logic.

---

## Phase 5: RAG Pipeline Orchestration (Using LangGraph)
**Objective**: Connect all the independent components into a cohesive multi-stage workflow utilizing LangGraph for cyclic graph execution.

- **Tasks**:
  - [ ] Define the LangGraph State Schema for the RAG pipeline.
  - [ ] **TDD**: Write tests for LangGraph node execution (verifying state updates for nodes like `rewriter`, `retriever`, `draft_generator`, `judge`).
  - [ ] **TDD**: Write tests for LangGraph conditional edges (e.g., `Judge` routing back to `Rewriter` on FAIL, or proceeding to `Refiner` on PASS).
  - [ ] Implement `SIMPLE` query route graph execution.
  - [ ] Implement full `KNOWLEDGE` RAG pipeline graph using LangGraph.

---

## Phase 6: API Layer Development
**Objective**: Expose the pipeline through RESTful API endpoints.

- **Tasks**:
  - [ ] Setup FastAPI framework.
  - [ ] **TDD**: Write API tests for `POST /api/ingest` (using FastAPI TestClient).
  - [ ] Implement ingest endpoint.
  - [ ] **TDD**: Write API tests for `GET /api/session/{session_id}`.
  - [ ] Implement session endpoint.
  - [ ] **TDD**: Write API tests for `POST /api/chat`.
  - [ ] Implement chat endpoint and connect it to the orchestration pipeline.

---

## Phase 7: UI / Frontend Development
**Objective**: Build a football-themed chat interface.

- **Tasks**:
  - [x] Setup basic frontend project (React or Vanilla JS).
  - [x] **TDD**: Write tests for frontend state management (chat history, session ID).
  - [x] Implement UI components (chat bubbles, input field, typing indicator).
  - [x] Implement API client and integrate with the FastAPI backend.
  - [x] Apply CSS/Theme styling (Dark green/pitch-inspired).

---

## Test-Driven Development (TDD) Rules for This Project:
1. **Never write production code without a failing test first.**
2. **Use Mocks extensively** for LLM calls (`Ollama`), external APIs (`StatsBomb`), and Vector DBs (`ChromaDB`) to ensure tests are fast and deterministic.
3. **Integration Tests** will only be used in Phases 5 & 6, ensuring the mocked unit tests correctly represent the contract between components.
