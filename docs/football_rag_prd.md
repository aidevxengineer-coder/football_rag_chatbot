# Pitchside — Product Requirements Document

**Version:** 1.0  
**Status:** Architecture Finalized, Pre-Build  

---

## 1. Overview

A football-themed conversational chatbot that answers questions about football using a Retrieval-Augmented Generation (RAG) pipeline. The system is designed with a primary goal of **minimizing hallucination** by using a multi-LLM pipeline with draft generation, judgment, and refinement stages before any answer reaches the user.

The knowledge base is built from StatsBomb Open Data, converted into natural language summaries and indexed into a ChromaDB vector database.

---

## 2. Goals

- Provide accurate, grounded answers to football-related queries
- Minimize LLM hallucination through multi-stage retrieval validation and output judgment
- Handle simple conversational queries without invoking the full RAG pipeline
- Maintain coherent multi-turn conversation context
- Present a polished, football-themed chat UI

---

## 3. Non-Goals

- Real-time match data or live scores
- User accounts or authentication
- Multi-user / multi-session persistence
- Support for non-football domains

---

## 4. System Architecture

### 4.1 High-Level Pipeline

```
User Query
    │
    ▼
┌─────────────────────┐
│   Query Rewriter    │  ← Small LLM 1
│  (clarifies query   │
│   for retrieval)    │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│    Orchestrator     │  ← Small LLM 1 (same model)
│  (classifies query) │
└────────┬────────────┘
         │
    ┌────┴─────┐
    │          │
SIMPLE      KNOWLEDGE
    │          │
    ▼          ▼
Heavy LLM   ┌──────────────────┐
(direct)    │   RAG Retrieval  │  ← ChromaDB (dense) + BM25 (sparse)
    │       └────────┬─────────┘
    │                │
    │                ▼
    │       ┌──────────────────┐
    │       │       RRF        │  ← Reciprocal Rank Fusion (re-ranking)
    │       └────────┬─────────┘
    │                │
    │                ▼
    │       ┌──────────────────┐
    │       │   Heavy LLM      │  ← Draft answer generation
    │       │  (draft answer) │
    │       └────────┬─────────┘
    │                │
    │                ▼
    │       ┌──────────────────────────────────────────┐
    │       │           Decision LLM                   │  ← Small LLM 2 (same or different)
    │       │  Inputs:                                 │
    │       │   - Original user query                  │
    │       │   - Rewritten query                      │
    │       │   - Reranked retrieved documents         │
    │       │   - Heavy LLM draft answer               │
    │       │  Judges: Is the draft grounded           │
    │       │          in the retrieved docs?          │
    │       └────────┬─────────────────────────────────┘
                     │
              ┌──────┴──────┐
            FAIL           PASS
              │              │
              ▼              ▼
       Back to          final answer -> user
     Query Rewriter  
                     

```

### 4.2 Component Descriptions

#### Query Rewriter
- **Model:** Small LLM
- **Input:** Raw user query + conversation context (summary + last 10 messages)
- **Output:** A clarified, self-contained query optimized for vector retrieval
- **Purpose:** Removes ambiguity and co-references (e.g. "what did he say?" → "What did Messi say about the 2022 World Cup?")

#### Orchestrator
- **Model:** Small LLM  (same inference call or chained)
- **Input:** Rewritten query
- **Output:** Classification — `SIMPLE` or `KNOWLEDGE`
- **Purpose:** Routes simple/conversational queries (greetings, meta questions) directly to the Heavy LLM, bypassing RAG entirely. Avoids unnecessary retrieval on trivial queries.

* Above two tasks (Query rewriter and orchestrator are done using a single system prompt and api call)

#### RAG Retrieval
- **Vector DB:** ChromaDB
- **Embedding Model:** Ollama embedding model (placeholder)
- **Retrieval Strategy:** Hybrid
  - **Dense:** Semantic vector similarity search (ChromaDB)
  - **Sparse:** BM25 keyword search
- **Top-K:** Configurable (default: 5 chunks per method)

#### RRF (Reciprocal Rank Fusion)
- **Type:** Algorithm (no LLM)
- **Input:** Ranked results from dense + sparse retrieval
- **Output:** Single merged, re-ranked list of chunks
- **Purpose:** Combines the strengths of semantic and keyword search into a single superior ranking

#### Draft Answer Generator
- **Model:** Small LLM (different system prompt)
- **Input:** Rewritten query + reranked retrieved chunks + conversation context
- **Output:** A draft answer grounded in the retrieved documents
- **Purpose:** Cheap first-pass generation before committing the Heavy LLM

#### Decision LLM
- **Model:** Small LLM 2 (same model, different prompt) or dedicated model
- **Inputs:**
  - Original user query
  - Rewritten query
  - Reranked retrieved documents
  - Draft answer from Small LLM 2
- **Output:** `PASS` or `FAIL` with optional reasoning
- **Judgment Criteria:**
  - Is every claim in the draft traceable to the retrieved chunks?
  - Does the draft actually answer the original query?
  - Are there any unsupported or fabricated facts?
- **On FAIL:** Loop back to Query Rewriter with failure context appended
- **On PASS:** Forward draft to Heavy LLM for refinement

#### Heavy LLM (Final Refiner)
- **Model:** Large LLM (GPU-hosted via Ollama)
- **Input:** Approved draft + original query + reranked chunks + conversation context
- **Output:** Polished, fluent final answer
- **Purpose:** Elevates the approved draft into a high-quality response. Does NOT generate from scratch — refines only.
- **Also used for:** Direct responses to SIMPLE queries (orchestrator bypass path)

---

## 5. Context Management

### Strategy: Summary-Based Rolling Context

```
┌──────────────────────────────────────────────┐
│  Context Window passed to every LLM call     │
│                                              │
│  [Rolling Summary]                           │
│   ↑ summarized from messages older than 10  │
│                                              │
│  [Last 10 Messages]                          │
│   - Kept verbatim as conversation history   │
│                                              │
│  [Current Query]                             │
└──────────────────────────────────────────────┘
```

- Messages 1–N (older than last 10) are **summarized** into a single rolling summary block
- The summary is updated incrementally as new messages push old ones out of the window
- Every LLM in the pipeline receives the full context: `[summary] + [last 10 messages] + [current query]`
- Summary generation is handled by Small LLM 1

### Context Schema

```python
class Message:
    role: str          # "user" | "assistant"
    content: str
    timestamp: datetime

class ConversationContext:
    session_id: str
    messages: list[Message]        # last 10 messages (verbatim)
    rolling_summary: str           # summarized history beyond 10
    message_count: int             # total messages in session
```

---

## 6. Data Layer

### 6.1 Knowledge Base Source

**StatsBomb Open Data** (`statsbombpy` library)

- Free, no API key required
- Event-level match data in JSON format
- Covers: La Liga, Champions League, Women's World Cup, Premier League (select seasons), AFCON, and more

### 6.2 Ingestion Pipeline

```
StatsBomb JSON (match events)
    │
    ▼
NL Summary Generator (Small LLM)
    │  Converts structured event data into
    │  readable match narrative chunks
    ▼
Text Chunker
    │  chunk_size: 512 tokens
    │  overlap: 64 tokens
    ▼
Embedding Model (Ollama)
    │
    ▼
ChromaDB (vector store)
    + BM25 index (keyword store)
```

### 6.3 ChromaDB Schema

```python
# Collection: "football_knowledge"

Document {
    id:        str          # unique chunk ID e.g. "match_3788_chunk_004"
    document:  str          # natural language chunk text
    embedding: list[float]  # vector from embedding model
    metadata: {
        match_id:       int
        competition:    str   # e.g. "La Liga"
        season:         str   # e.g. "2020/2021"
        home_team:      str
        away_team:      str
        chunk_index:    int
        source:         str   # "statsbomb"
    }
}
```

### 6.4 BM25 Index Schema

```python
# Stored as serialized index (pickle / JSON)
BM25Index {
    corpus:     list[str]   # raw text of each chunk (aligned with ChromaDB IDs)
    chunk_ids:  list[str]   # corresponding ChromaDB document IDs
}
```

---

## 7. API Schema

### 7.1 Chat Endpoint

```
POST /api/chat

Request:
{
    "session_id": "uuid",
    "query": "Who scored the most goals in the 2020/21 La Liga season?"
}

Response:
{
    "session_id": "uuid",
    "answer": "...",
    "route": "rag" | "direct",
    "retrieval_attempts": 1,
    "sources": [
        {
            "chunk_id": "match_3788_chunk_004",
            "competition": "La Liga",
            "season": "2020/2021",
            "home_team": "Barcelona",
            "away_team": "Real Madrid",
            "excerpt": "..."
        }
    ]
}
```

### 7.2 Ingest Endpoint

```
POST /api/ingest

Request:
{
    "competition_id": 11,
    "season_id": 90
}

Response:
{
    "status": "success",
    "chunks_indexed": 1423,
    "competition": "La Liga",
    "season": "2020/2021"
}
```

### 7.3 Session Endpoint

```
GET /api/session/{session_id}

Response:
{
    "session_id": "uuid",
    "message_count": 14,
    "rolling_summary": "...",
    "last_10_messages": [...]
}
```

---

## 8. LLM Role Assignment

| Role | Model Slot | Tasks |
|---|---|---|
| Small LLM | `SMALL_LLM_1` (placeholder) | Query rewriting, Orchestration, Summary generation, Decision/Judgement |

| Large LLM | `LARGE_LLM` (placeholder) | Draft answer generation, Direct simple query responses |

All models served via Ollama on the GPU machine, accessed over the network via HTTP.

```python
OLLAMA_BASE_URL = "http://<GPU_MACHINE_IP>:11434"  # placeholder

MODELS = {
    "small": "<small_model_name>",   # placeholder
    "large":   "<large_model_name>", # placeholder
}
```

---

## 9. Prompt Templates (Outline)

### Query Rewriter Prompt
```
You are a query rewriting assistant for a football knowledge system.
Given the conversation history and the user's latest message, rewrite the 
query to be self-contained, specific, and optimized for document retrieval.

Previous attempts (if any): {previous_rewrites}
Failure reason (if retry): {failure_reason}

Conversation summary: {rolling_summary}
Last messages: {last_10_messages}
User query: {raw_query}

Rewritten query:
```

### Orchestrator Prompt
```
Classify the following query as either SIMPLE or KNOWLEDGE.

SIMPLE: greetings, thanks, meta questions, chit-chat, anything not requiring 
        football knowledge lookup.
KNOWLEDGE: any question requiring factual football information.

Query: {rewritten_query}

Classification (respond with only SIMPLE or KNOWLEDGE):
```

### Draft Generator Prompt
```
You are a football expert assistant. Answer the query using ONLY the 
information provided in the retrieved documents below. Do not use any 
external knowledge. If the documents do not contain enough information, 
say so explicitly. Be fluent, well-structured, and engaging.

Retrieved documents:
{reranked_chunks}

Conversation context:
{context}

Query: {rewritten_query}

Answer:
```


### Decision LLM Prompt
```
You are a strict factual grounding evaluator. 

Original user query: {original_query}
Rewritten query: {rewritten_query}

Retrieved documents:
{reranked_chunks}

Draft answer:
{draft_answer}

Evaluate whether the draft answer:
1. Is fully grounded in the retrieved documents (no fabricated facts)
2. Directly answers the original query
3. Contains no claims unsupported by the documents

Respond with PASS or FAIL, followed by a one-line reason.
```

---

## 10. UI Specification

- **Style:** Claude-like chat interface with football theme
- **Theme elements:** Dark green / pitch-inspired color palette, football iconography
- **Features:**
  - Chat input with send button
  - Message history display (user + assistant bubbles)
  - Source citations shown beneath assistant responses (collapsible)
  - Typing indicator during pipeline execution
  - Session persistence within browser tab

---

## 11. Tech Stack

| Layer | Technology |
|---|---|
| LLM Serving | Ollama (remote GPU machine) |
| Vector DB | ChromaDB |
| Keyword Search | BM25 (rank_bm25 library) |
| Re-ranking | RRF algorithm (custom implementation) |
| Data Source | StatsBomb Open Data (statsbombpy) |
| Backend | FastAPI (Python) |
| Frontend | TBD (React or plain HTML/CSS/JS) |
| Context Store | In-memory (per session) / Redis (if persistent sessions needed) |

---

## 12. Hallucination Mitigation Summary

| Mechanism | How it reduces hallucination |
|---|---|
| Query Rewriting | Cleaner queries → more relevant retrieval → less gap-filling by LLM |
| Hybrid Retrieval (dense + sparse) | Better chunk coverage → model has accurate grounding material |
| RRF Re-ranking | Best chunks surface to top → less noise in context |
| Draft Generation (Small LLM) | Cheap constrained generation — easier to catch errors at low cost |
| Decision LLM | Explicitly verifies draft is grounded in retrieved docs before surfacing |
| Loop-back on FAIL | Bad answers rejected and retried — never served to user |
| Heavy LLM as Refiner only | Refines approved content, never generates from scratch — minimal hallucination surface |

---

## 13. Loop Termination

To prevent infinite retry loops:

```python
MAX_RETRIEVAL_ATTEMPTS = 3

# On each loop iteration, pass to Query Rewriter:
# - All previous rewritten queries (to avoid regenerating the same one)
# - The failure reason from the Decision LLM
# - The attempt number

# After MAX_RETRIEVAL_ATTEMPTS, return a fallback response:
FALLBACK_RESPONSE = "I wasn't able to find reliable information about that 
                     in my knowledge base. Could you rephrase your question?"
```

---

*Document end. Next step: implementation.*
