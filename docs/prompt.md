generate a presentation with the below stated outline:

Topic: Pitchside - Agentic RAG Football Chatbot: Internal Architecture & Anti-Hallucination Design
Audience: professional
Length: 5-15 pages
Style: minimalist, football-themed
Design Type: presentation


Presentation Outlines:

Slide 1: Pitchside
  Description: - Agentic RAG Chatbot for Football Intelligence
- Subtitle: Internal Architecture & Anti-Hallucination Design
- LangGraph-Orchestrated Multi-Agent Pipeline
- Powered by Groq API + Local Ollama

Slide 2: The Problem: Why Football Needs a Smarter Chatbot
  Description: - Football is a stats-dense, fact-critical domain
- LLMs hallucinate player names, match results, and statistics with confidence
- A naive chatbot is worse than no chatbot when fans can spot wrong answers immediately
- Pitchside's mission: factually verified football intelligence on every response

Slide 3: The Pipeline at a Glance
  Description: - Seven-stage end-to-end architecture
- Stage 1: Data Ingestion — user submits a query via chat UI
- Stage 2: Query Rewriting — raw query made self-contained using conversation history
- Stage 3: Orchestration — fast binary routing: SIMPLE vs KNOWLEDGE
- Stage 4: Hybrid Retrieval — ChromaDB + BM25 fused via RRF
- Stage 5: Response Drafting — context-grounded LLM generation
- Stage 6: Response Evaluation / Judging — hallucination detection
- Stage 7: Output — verified answer delivered; pipeline logged
- Self-correcting: Stages 2-6 loop up to 3 times on FAIL

Slide 4: Stage 1: Data Ingestion
  Description: - User submits a natural language football query via the Vanilla JS chat frontend
- Query and session ID sent to FastAPI /api/chat endpoint
- Session state retrieved from in-memory session dictionary
- Knowledge base pre-built offline: football articles chunked, embedded, and indexed
- ChromaDB handles dense vector storage; BM25 corpus built in parallel at index time
- BM25 title boosting applied at indexing: title fields repeated per chunk to boost exact name matches
- No runtime knowledge base modification — retrieval index is stable during serving

Slide 5: Stage 2: Query Rewriting
  Description: - Model: Qwen 2B (non-thinking mode) via Groq API
- Converts raw user message into a fully self-contained standalone query
- Pulls from two-tier memory: Hot Context (last 10 messages verbatim) + Cold Snapshot
- Snapshot: messages older than hot window eagerly compressed into dense factual prose
- Eager compression chosen over lazy: zero staleness — snapshot always current before rewriting
- Snapshot capped at 300 tokens to protect context window within Groq free tier limits (8000 TPM)
- Ensures downstream nodes always receive a precise, unambiguous query

Slide 6: Stage 3: Orchestration
  Description: - Model: Qwen 0.8B — smallest, fastest model in the pipeline
- Binary classification: SIMPLE (greetings, small talk) vs KNOWLEDGE (requires football facts)
- SIMPLE path: answered immediately by Simple Responder — bypasses retrieval entirely, cuts latency
- KNOWLEDGE path: proceeds to Hybrid Retrieval
- Design decision: binary routing is pattern-matching, not reasoning — 0.8B is sufficient and far faster
- Entire orchestration consumes ~100 input + 5 output tokens

Slide 7: Stage 4: Hybrid Retrieval
  Description: - Dense Retrieval: ChromaDB with all-MiniLM-L6-v2 — captures semantic similarity
- Sparse Retrieval: BM25Okapi — captures exact lexical matches (player names, years, clubs)
- Neither alone is sufficient: semantic search misses exact names; keyword search misses paraphrase
- Fusion: Reciprocal Rank Fusion (RRF) — score = 1 / (k + rank) across both result lists
- Documents ranking high in BOTH lists surface at the top — precision without sacrificing recall
- BM25 title boosting (applied at ingestion) pays off here: exact-name queries surface correct articles

Slide 8: Stage 5: Response Drafting
  Description: - Model: Qwen 2B (non-thinking mode) via Groq API
- Strictly prompted with a hard constraint: answer using ONLY the provided retrieved context
- No reliance on parametric (training-time) memory — model explicitly forbidden from going beyond chunks
- Retrieved chunks injected verbatim into the prompt as the sole source of truth
- Prompt structure: System instruction → Retrieved Context → Rewritten Query → Draft instruction
- Non-thinking mode chosen deliberately: drafting requires fluent generation, not extended reasoning
- Output is a draft — not yet trusted; handed off directly to the Decision Judge for verification

Slide 9: Stage 6: Response Evaluation (Decision Judge)
  Description: - Model: Qwen 4B (thinking mode enabled) — deepest reasoning in the pipeline
- Evaluates drafted answer against retrieved chunks: did the draft invent anything not in context?
- Returns structured JSON verdict: PASS or FAIL
- Thinking mode chosen deliberately: hallucination detection requires careful cross-referencing
- On PASS: answer delivered to user
- On FAIL: loop cycles back to Query Rewriter with a new retrieval angle — up to 3 retries
- Think tags stripped from judge output before anything flows downstream
- Raw reasoning preserved in llm_calls table for post-hoc debugging

Slide 10: Stage 7: Output & Observability
  Description: - Verified answer returned via FastAPI to Vanilla JS frontend
- Full pipeline logged to normalized SQLite database (trace_logs.db)
- pipeline_runs: per-request summary — duration, classification, snapshot state
- llm_calls: every API call — exact prompt, raw response with think tags, cleaned output, latency
- loop_iterations: retry history — rewritten queries and Judge verdicts per attempt
- retrieval_events and retrieved_chunks: full RRF output logged per iteration
- Enables deep analytics: Judge fail rate, Orchestrator latency, snapshot quality over time

Slide 11: Key Design Decisions: The Full Picture
  Description: - Hybrid RRF over single-method retrieval: maximizes both recall and precision
- Model specialization: 0.8B router / 2B rewriter+drafter / 4B judge — right depth for each role
- Hard context-only prompting in Draft Generator: parametric memory explicitly excluded
- Self-correction loop: system catches hallucinations internally before user ever sees them
- Eager snapshot compression: no amnesia boundary on long football analysis conversations
- Normalized SQL logging over flat JSON: analytics-ready, not just debuggable
- Every decision traces back to one goal: factual accuracy in a zero-tolerance domain

Slide 12: Pitchside — Built to Get Football Right
  Description: - Seven tightly integrated stages each with deliberate design choices
- From BM25 title boosting at index time to the Judge's thinking-mode verification
- No component is accidental — every node earns its place in the pipeline
- Football fans will not tolerate wrong answers. Pitchside is engineered to never give one.

* Keep text on slides minimal.
* Use /presentation-design-expert, /scientific-slides, and use the design of the attached presentation.