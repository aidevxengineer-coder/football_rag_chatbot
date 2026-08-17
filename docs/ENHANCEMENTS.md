# Pitchside Enhancements

This document details the architecture, design decisions, and implementation specifications for five planned enhancements to the Pitchside RAG pipeline. Each section is self-contained and cross-references the relevant components in `ARCHITECTURE.md` where applicable.

---

## Table of Contents

1. [Snapshot Context Maintenance](#1-snapshot-context-maintenance)
2. [Multi-Format File Ingestion with Football Relevance Guard](#2-multi-format-file-ingestion-with-football-relevance-guard)
3. [Groq API Provider Option](#3-groq-api-provider-option)
4. [Smart Chunking](#4-smart-chunking)
5. [Real-Time Token Streaming](#5-real-time-token-streaming)
6. [Cross-Cutting Concerns](#6-cross-cutting-concerns)

---



## 1. Snapshot Context Maintenance



### Problem

The current `QueryRewriter` pulls only the last N messages from the session state to construct its context window. Any conversation history beyond that window is silently dropped. For a football-focused assistant handling extended analytical discussions — where a user might reference "the formation we discussed earlier" or "that stat from before" — this creates a hard amnesia boundary that breaks conversational coherence.

### Design Overview

A two-tier memory model replaces the current single-window approach:

- **Hot Context:** The last 10 messages passed verbatim to the `QueryRewriter`. This number is configurable via the `HOT_CONTEXT_WINDOW` environment variable (default: `10`).
- **Cold Context (Snapshot):** All messages older than the hot window are compressed into a running natural-language summary — the snapshot. The snapshot is stored directly in the session state dictionary alongside the message list and is updated eagerly on every turn where a message ages out of the hot window.



### Eager vs. Lazy Update Decision

Since accuracy is the primary concern over latency, **eager compression** is used. The snapshot is updated synchronously before the current query is processed. This guarantees the `QueryRewriter` always receives a fully current snapshot — there is no staleness window, no dirty flag, no deferred background task.

Lazy compression (updating asynchronously after the response is returned) would reduce latency slightly but introduces a one-turn lag where the snapshot does not yet reflect the most recent aged-out message. Given the conversational nature of the pipeline, this lag is unacceptable.

### Session State Schema

The session state dictionary is extended with two new fields:

```python
session = {
    "messages": [...],          # Full message history (all turns)
    "snapshot": str,            # Compressed summary of messages older than HOT_CONTEXT_WINDOW
    "snapshot_turn_count": int  # How many messages were included in the last snapshot compression
}
```

`snapshot_turn_count` is used to detect whether new messages have aged out of the hot window since the last compression, triggering a re-compression if so.

### Compression Logic

A dedicated `SnapshotCompressor` function runs before the `QueryRewriter` node on every pipeline invocation. Its behavior:

1. Calculate `aged_messages = messages[:-HOT_CONTEXT_WINDOW]`
2. If `len(aged_messages) == snapshot_turn_count`, the snapshot is current — skip compression.
3. If `len(aged_messages) > snapshot_turn_count`, new messages have aged out. Re-compress:
  - Pass the existing snapshot (if any) plus the newly aged-out messages to the compression prompt.
  - The model incrementally updates the snapshot rather than reprocessing the entire history from scratch on every turn.
4. Store the result back to `session["snapshot"]` and update `snapshot_turn_count`.

**Compression Model:** `qwen/qwen3.6-27b` in non-thinking mode. The same model used for rewriting and drafting — no additional dependency.

**Compression Prompt:**

```
You are a memory compressor for a football-focused conversational assistant.

EXISTING SUMMARY (may be empty on first compression):
{existing_snapshot}

NEW MESSAGES TO INCORPORATE:
{newly_aged_messages}

Update the summary to incorporate the new messages. The summary must:
- Be written in dense, factual prose. No bullet points.
- Preserve all specific football entities mentioned: player names, clubs, seasons,
  statistics, formations, match results, and any user preferences or hypotheses.
- Discard pleasantries, filler, and meta-commentary about the conversation itself.
- Target length: {SNAPSHOT_MAX_TOKENS} tokens maximum. Be ruthlessly concise.

Return only the updated summary. No preamble.
```

`SNAPSHOT_MAX_TOKENS` is a configurable environment variable (default: `300`). This caps snapshot size to protect the `QueryRewriter`'s context window, especially important given the 6,000–8,000 TPM limits on Groq's free tier.

### Updated QueryRewriter Prompt Structure

The `QueryRewriter` prompt is extended to receive both tiers:

```
[CONVERSATION SNAPSHOT]
{snapshot}   ← empty string if no snapshot exists yet

[RECENT MESSAGES]
{last_10_messages_verbatim}

[CURRENT QUERY]
{raw_user_query}

Rewrite the current query into a fully self-contained, standalone question that
incorporates all relevant context from both the snapshot and recent messages.
Return only the rewritten query. No explanation.
```



### Database Logging

A new column `snapshot_text` is added to the `pipeline_runs` table to log the snapshot state at the time of each query. This enables post-hoc analysis of snapshot quality and debugging of context failures.

```sql
ALTER TABLE pipeline_runs ADD COLUMN snapshot_text TEXT;
```



### Environment Variables


| Variable              | Default | Description                                                         |
| --------------------- | ------- | ------------------------------------------------------------------- |
| `HOT_CONTEXT_WINDOW`  | `10`    | Number of most recent messages passed verbatim to the QueryRewriter |
| `SNAPSHOT_MAX_TOKENS` | `300`   | Maximum token length of the compressed snapshot                     |


---



## 2. Multi-Format File Ingestion with Football Relevance Guard

### Problem

The existing `/api/ingest` endpoint accepts only structured JSON text. Users need to be able to add their own source material — match reports as PDFs, squad stats as spreadsheets, broadcast screenshots as images — without the knowledge base being polluted with off-topic content.

### Supported File Formats


| Format      | Extensions                       | Extraction Method                                        |
| ----------- | -------------------------------- | -------------------------------------------------------- |
| Plain text  | `.txt`, `.md`                    | Direct UTF-8 read                                        |
| PDF         | `.pdf`                           | PyMuPDF (`fitz`) for text + embedded image extraction    |
| Spreadsheet | `.csv`, `.xlsx`                  | Pandas for tabular parsing → structured text conversion  |
| Image       | `.jpg`, `.jpeg`, `.png`, `.webp` | Vision model (description) + Tesseract (OCR) — see below |


**Videos are explicitly out of scope.**

### Ingestion Pipeline

Every uploaded file passes through the following sequential stages before any content reaches the vector store:

```
Upload → Format Extraction → Football Relevance Guard → Smart Chunking → Embedding → Index
```

Stages 4 and 5 (Smart Chunking and Embedding) are covered in detail in Section 4. This section covers Stages 1–3.

### Stage 1: Format Extraction



#### Plain Text and Markdown

Read directly. No preprocessing beyond stripping null bytes and normalising line endings.

#### PDF Extraction

PyMuPDF (`fitz`) is used for all PDF extraction. It handles:

- **Text blocks:** Extracted in reading order, preserving page and section structure.
- **Embedded images:** Each embedded image in the PDF is extracted as a raw bytes object and routed through the image processing pipeline (description + OCR) independently. The resulting text is inserted inline at the position where the image appeared in the PDF.
- **Page metadata:** Page numbers are tracked and stored in chunk metadata (see Section 4).

```python
import fitz

def extract_pdf(path: str) -> list[dict]:
    doc = fitz.open(path)
    blocks = []
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text("blocks")
        for block in text:
            blocks.append({"text": block[4], "page": page_num, "type": "text"})
        for img in page.get_images(full=True):
            img_bytes = doc.extract_image(img[0])["image"]
            img_text = process_image(img_bytes)
            blocks.append({"text": img_text, "page": page_num, "type": "image_derived"})
    return blocks
```



#### Spreadsheet Extraction

Pandas loads `.csv` and `.xlsx` files. The conversion to indexable text follows this structure:

1. **Header preservation:** Column names are prepended to every chunk (see Section 4 for chunking strategy).
2. **Type normalisation:** Numeric columns with football semantics (goals, assists, minutes, etc.) are formatted as `column_name: value` pairs.
3. **Row serialisation:** Each row is serialised as a single sentence: `"Player: Erling Haaland | Season: 2023/24 | Goals: 36 | Assists: 8 | Club: Manchester City"`

This format is retrievable by both the dense (semantic) and sparse (BM25 keyword) search legs of the hybrid retriever.

#### Image Extraction (Two-Pass)

Images undergo a mandatory two-pass extraction. Both passes run concurrently and their outputs are concatenated.

**Pass 1 — Visual Description (**`qwen/qwen3.6-27b` **vision):**

The image is encoded as base64 and sent to `qwen/qwen3.6-27b` via Groq's multimodal API. The prompt is football-aware to maximise relevant description density:

```
Describe this image in precise detail, focusing on all football-related content.
Include: visible players, jersey colours and numbers, formation or tactical positioning,
stadium or pitch context, scoreboard information, match events in progress, any
on-screen graphics or overlays, and broadcast text elements.
Be specific. Do not speculate beyond what is visible.
```

**Pass 2 — OCR (Tesseract):**

Tesseract runs on the same image independently. The raw OCR output is post-processed:

- Strip lines that are fewer than 3 characters (noise).
- Strip lines with a confidence score below 60 (Tesseract's `--oem 3 --psm 6` mode).
- If the remaining output is empty or all-noise, the `[TEXT IN IMAGE]` block is omitted entirely.

**Concatenated output structure:**

```
[VISUAL DESCRIPTION]
A football broadcast screenshot showing Arsenal vs Chelsea. Arsenal players in red
jerseys are pressing high. The scoreboard reads 2-1 with 74 minutes elapsed...

[TEXT IN IMAGE]
Arsenal 2 - 1 Chelsea
74'
Emirates Stadium
```

This combined blob is what enters the relevance guard and chunking pipeline. The exact OCR text is critical for ensuring precise entity matching in retrieval (player names, scorelines, timestamps) rather than relying on the vision model's paraphrase of the same information.

### Stage 2: Football Relevance Guard

Before any extracted content is chunked or indexed, it is classified for football relevance. This prevents knowledge base pollution.

**Classifier:** `qwen/qwen3.6-27b` in non-thinking mode (fast, binary task).

**Prompt:**

```
You are a content classifier for a football knowledge base.

Determine whether the following content is related to football (soccer).
Content qualifies if it discusses: matches, players, clubs, leagues, tactics,
formations, statistics, transfers, managers, stadiums, competitions, or any
other football-specific subject matter.

Content:
{extracted_text_first_1000_chars}

Respond with exactly one word: YES or NO.
```

Only the first 1,000 characters of extracted text are sent to the classifier. This is sufficient for topic detection and avoids wasting TPM budget on long documents at this stage.

**If the response is** `NO`**:**

A `FootballRelevanceError` is raised immediately. The file is not chunked, not embedded, and not indexed. The API returns a clear, descriptive error to the user:

```json
{
  "error": "FootballRelevanceError",
  "message": "The uploaded file does not appear to contain football-related content and cannot be added to the knowledge base.",
  "filename": "quarterly_earnings_report.pdf"
}
```

**If the response is** `YES`**:** Extraction output proceeds to Stage 3 (Smart Chunking, Section 4) and then to embedding and indexing.

### API Changes

The existing `POST /api/ingest` endpoint is extended to accept `multipart/form-data` with a `file` field:

```
POST /api/ingest
Content-Type: multipart/form-data

file: <binary file upload>
```

The endpoint auto-detects format from the file extension. Unsupported extensions return a `415 Unsupported Media Type` error listing the accepted formats.

### Dependencies


| Library            | Purpose                               |
| ------------------ | ------------------------------------- |
| `pymupdf` (`fitz`) | PDF text and image extraction         |
| `pandas`           | CSV and XLSX parsing                  |
| `openpyxl`         | XLSX backend for Pandas               |
| `pytesseract`      | Python wrapper for Tesseract OCR      |
| `Pillow`           | Image preprocessing before Tesseract  |
| `tesseract-ocr`    | System-level OCR binary (apt package) |


---



## 3. Groq API Provider Option



### Problem

Running local Qwen models requires significant hardware resources and introduces environment-specific setup complexity. A Groq API backend provides fast, hardware-agnostic inference via a simple API call, enabling development and deployment on any machine without GPU requirements.

### Provider Switching

A single environment variable controls which backend all LLM calls use:

```
LLM_PROVIDER=local   # default — use local Ollama models
LLM_PROVIDER=groq    # use Groq API for all LLM calls
```

The existing `invoke_llm()` function is refactored into a provider-aware dispatcher. All call sites (Query Rewriter, Orchestrator, Draft Generator, Decision Judge, Simple Responder, Snapshot Compressor) remain unchanged — they pass a logical role name, and the dispatcher resolves it to the correct model and backend.

```python
def invoke_llm(role: str, prompt: str, image: bytes | None = None) -> str:
    if config.LLM_PROVIDER == "groq":
        return _call_groq(GROQ_MODEL_MAP[role], prompt, image)
    else:
        return _call_local(LOCAL_MODEL_MAP[role], prompt)
```



### Model Mapping



#### Current Local Models (unchanged)


| Role                                                                   | Local Model    |
| ---------------------------------------------------------------------- | -------------- |
| Orchestrator / Classifier                                              | `Qwen3.5-0.8B` |
| Query Rewriter, Draft Generator, Simple Responder, Snapshot Compressor | `Qwen3.5-2B`   |
| Decision Judge                                                         | `Qwen3.5-4B`   |




#### Groq Models


| Role                       | Groq Model                         | Rationale                                                                                    |
| -------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------- |
| Orchestrator / Classifier  | `openai/gpt-oss-20b`               | Fast, capable of binary classification, separate daily request budget from the primary model |
| Query Rewriter             | `qwen/qwen3.6-27b` (non-thinking)  | Best intelligence score on Groq free tier, 262K context window                               |
| Snapshot Compressor        | `qwen/qwen3.6-27b` (non-thinking)  | Same model, concise summarisation task                                                       |
| Simple Responder           | `qwen/qwen3.6-27b` (non-thinking)  | Conversational responses do not require thinking mode                                        |
| Draft Generator            | `qwen/qwen3.6-27b` (non-thinking)  | Streamed live to the user (see Section 5)                                                    |
| Decision Judge             | `qwen/qwen3.6-27b` (thinking mode) | Fact-checking requires rigorous reasoning; thinking mode is toggled ON for this role only    |
| Vision (image description) | `qwen/qwen3.6-27b` (multimodal)    | Natively accepts image inputs; no separate vision model required                             |


**Why** `qwen/qwen3.6-27b` **for most roles:** As of June 2026, `qwen/qwen3-32b` has been deprecated by Groq in favour of `qwen/qwen3.6-27b`, which is the current highest-intelligence model on the free tier. It supports switchable thinking/non-thinking modes within a single model, multimodal image input, a 262K context window, tool use, and JSON mode. Using one model for most roles simplifies the codebase and avoids splitting the daily request budget across multiple model quotas.

**Why** `openai/gpt-oss-20b` **for the Orchestrator:** Offloading binary `SIMPLE`/`KNOWLEDGE` classification to a separate model distributes the daily request budget. The orchestrator fires on every single query, so using `qwen3.6-27b` for it would consume a disproportionate share of the 1,000 RPD quota.

### Thinking Mode Control

`qwen/qwen3.6-27b` supports toggling thinking mode per request via the `thinking` field in the request body (or via a system prompt instruction in non-native clients). The dispatcher sets this per role:

```python
GROQ_THINKING_ROLES = {"judge"}  # Only the Decision Judge uses thinking mode

def _call_groq(model: str, prompt: str, role: str, image: bytes | None = None) -> str:
    thinking = role in GROQ_THINKING_ROLES
    # Build request with thinking flag accordingly
```

The existing `<think>` tag stripping logic in `invoke_llm()` carries over unchanged. Raw reasoning blocks are preserved in the `llm_calls` database table for debugging; only the cleaned response is passed downstream.

### Rate Limits and Free Tier Constraints

Groq free tier limits (as of June 2026):


| Model                | RPM | TPM   | RPD   |
| -------------------- | --- | ----- | ----- |
| `qwen/qwen3.6-27b`   | 30  | 8,000 | 1,000 |
| `openai/gpt-oss-20b` | 30  | 8,000 | 1,000 |


**Rate limit analysis:** A single worst-case user query (knowledge path, 3 retries) makes approximately:


| Call                               | Model         | Count         |
| ---------------------------------- | ------------- | ------------- |
| Snapshot Compressor (if triggered) | `qwen3.6-27b` | 0–1           |
| Query Rewriter                     | `qwen3.6-27b` | 1–3 (retries) |
| Orchestrator                       | `gpt-oss-20b` | 1             |
| Draft Generator                    | `qwen3.6-27b` | 1–3 (retries) |
| Decision Judge                     | `qwen3.6-27b` | 1–3 (retries) |
| **Total (worst case)**             |               | **~10 calls** |


At 1,000 RPD per model, the `qwen3.6-27b` budget supports approximately **100 worst-case queries per day**, which is appropriate for a personal or demo-scale deployment.

**Prompt caching:** Groq does not count cached tokens toward TPM limits. System prompts that are consistent across calls — particularly the Decision Judge's evaluation prompt — should be structured to maximise prefix caching, meaningfully extending effective token throughput.

### Retry and Backoff

A `429 Too Many Requests` response triggers exponential backoff with jitter:

```python
GROQ_MAX_RETRIES = int(os.getenv("GROQ_MAX_RETRIES", "5"))
GROQ_BACKOFF_BASE = float(os.getenv("GROQ_BACKOFF_BASE", "1.5"))  # seconds

for attempt in range(GROQ_MAX_RETRIES):
    response = call_groq_api(...)
    if response.status_code == 429:
        retry_after = float(response.headers.get("retry-after", GROQ_BACKOFF_BASE ** attempt))
        time.sleep(retry_after + random.uniform(0, 0.5))
        continue
    break
```

The `retry-after` header returned by Groq is used directly when available, as it specifies the exact reset time rather than requiring guess-and-check backoff.

### Environment Variables


| Variable            | Default | Description                          |
| ------------------- | ------- | ------------------------------------ |
| `LLM_PROVIDER`      | `local` | `local` or `groq`                    |
| `GROQ_API_KEY`      | —       | Required when `LLM_PROVIDER=groq`    |
| `GROQ_MAX_RETRIES`  | `5`     | Maximum retry attempts on 429        |
| `GROQ_BACKOFF_BASE` | `1.5`   | Base seconds for exponential backoff |


---



## 4. Smart Chunking



### Problem

Fixed-size chunking (e.g., 512 tokens with overlap) splits sentences mid-thought, fractures structured data like tables, strips heading context from PDF sections, and loses the semantic boundaries that naturally exist in football writing. This degrades retrieval precision because chunks retrieved may contain partial, decontextualised information.

### Format-Aware Chunking Strategy

Chunking is performed by a `SmartChunker` class that dispatches to a format-specific strategy based on the `chunk_type` metadata set during extraction.

#### Plain Text and Articles

Sentence-boundary-aware chunking using `nltk.sent_tokenize`:

1. Split the document into sentences.
2. Greedily accumulate sentences into a chunk until the target token count (`CHUNK_TARGET_TOKENS`, default: `400`) is reached or a paragraph boundary is encountered.
3. Never split mid-sentence. If adding the next sentence would exceed the target, close the current chunk and start a new one.
4. Apply a sliding overlap of `CHUNK_OVERLAP_SENTENCES` sentences (default: `2`) between consecutive chunks to preserve cross-boundary context.

**Why** `nltk` **over** `spaCy`**:** `nltk.sent_tokenize` is lightweight, has no model download requirement at runtime, and is sufficient for English football text. `spaCy` is not justified for sentence splitting alone.

#### PDFs

Structure-aware chunking using PyMuPDF's block-level API:

1. During extraction, each text block is tagged with its font size and weight relative to the document's modal body font.
2. Blocks with significantly larger or bolder font than the body are classified as headings.
3. The document is segmented into sections at each heading boundary.
4. Each section becomes one or more chunks, with the section heading prepended to every chunk derived from it:

```
[SECTION: Premier League 2023/24 Season Review]
Liverpool finished third in the table with 82 points, their best return since...
```

Prepending the heading to every child chunk ensures that when a chunk is retrieved in isolation, the section context is not lost.

#### Spreadsheets (CSV / XLSX)

Row-group chunking:

1. The header row is stored separately and prepended to every chunk.
2. Rows are grouped into chunks of `TABLE_CHUNK_ROWS` rows (default: `10`).
3. Each chunk is serialised in the `column: value | column: value` format established during extraction.

```
[TABLE HEADER: Player | Club | Season | Goals | Assists | Minutes]
Player: Erling Haaland | Club: Manchester City | Season: 2023/24 | Goals: 36 | Assists: 8 | Minutes: 2890
Player: Harry Kane | Club: Bayern Munich | Season: 2023/24 | Goals: 44 | Assists: 12 | Minutes: 3180
...
```

This format is intentionally optimised for BM25 lexical matching — the `column: value` structure ensures that queries for "Kane goals 2023" surface the correct row through keyword overlap.

#### Image-Derived Text

Image-derived text (from the two-pass vision + OCR pipeline) is treated as a single atomic chunk regardless of length, up to a maximum of `CHUNK_TARGET_TOKENS` tokens. It is not split because the visual description and OCR output are tightly coupled — splitting them would produce decontextualised fragments.

### Chunk Metadata Schema

Every chunk produced by the `SmartChunker` carries a metadata dictionary stored in ChromaDB alongside the embedding vector and in the `retrieved_chunks` database table:

```python
{
    "source_file": "arsenal_2024_squad_stats.csv",
    "chunk_type": "table_row",          # text | pdf_section | table_row | image_derived
    "section_heading": "",              # populated for pdf_section chunks
    "page_number": None,                # populated for pdf chunks (int)
    "chunk_index": 3,                   # position within source document
    "token_count": 387,
    "ingested_at": "2026-06-28T14:32:00Z"
}
```

This metadata serves two purposes: debugging retrieval failures (which source documents and sections are being retrieved) and future citation support (surfacing the source file and section in the user-facing answer).

### BM25 Index Updates

When new files are ingested, the BM25 index must be rebuilt or incrementally updated to include the new chunks. The current architecture serialises BM25Okapi at startup from the full chunk corpus. On ingestion, the new chunks are appended to the corpus and BM25Okapi is re-instantiated. For the current scale of Pitchside's knowledge base, full re-instantiation on ingestion is acceptable. If the corpus grows large enough that re-instantiation becomes slow, a persistent BM25 index library (e.g., `bm25s`) should be adopted.

### Environment Variables


| Variable                  | Default | Description                                            |
| ------------------------- | ------- | ------------------------------------------------------ |
| `CHUNK_TARGET_TOKENS`     | `400`   | Target token count per chunk (plain text and PDFs)     |
| `CHUNK_OVERLAP_SENTENCES` | `2`     | Sentence overlap between consecutive plain text chunks |
| `TABLE_CHUNK_ROWS`        | `10`    | Number of data rows per table chunk                    |


---



## 5. Real-Time Token Streaming



### Problem

The current pipeline buffers the complete response before sending anything to the client. For the Draft Generator — the most token-heavy LLM call in the pipeline — this means users see a blank response area for several seconds while the model generates. This is poor UX and gives no signal that the system is working.

### Design Philosophy

Streaming is applied **only at the Draft Generator node**. Intermediate nodes (Query Rewriter, Orchestrator, Snapshot Compressor) are not streamed — they feed into each other and the user has no need to see their outputs. The Decision Judge is also not streamed, but its role changes significantly under this design (see below).

The key design insight is that streaming and fact-checking must happen **simultaneously**, not sequentially. The user sees the draft being generated in real time, and the judge evaluates it after generation completes. The visual treatment communicates the tentative state of the draft to the user throughout.

### Streaming Flow

```
Draft Generator begins streaming
        │
        ├─── SSE tokens → Frontend (renders at reduced opacity)
        │
        └─── Accumulated buffer (server-side, in parallel)
                │
        Draft generation completes
                │
        Decision Judge evaluates accumulated buffer
                │
        ┌───────┴───────┐
      PASS             FAIL
        │                │
  SSE: "VERIFIED"   SSE: "RETRY"
  Frontend:          Frontend:
  Opacity → 1.0     Clear draft text
                    Loop retries (up to 3x)
                    New draft streams
```



### Backend Implementation



#### FastAPI StreamingResponse

The `/api/chat` endpoint returns a `StreamingResponse` with `text/event-stream` media type:

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        pipeline.stream_chat(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
```

`X-Accel-Buffering: no` is required when running behind Nginx to prevent the proxy from buffering the SSE stream, which would negate the streaming benefit.

#### SSE Event Protocol

A simple structured event protocol communicates pipeline state to the frontend. All events are newline-delimited SSE:

```
# Token from Draft Generator
data: {"type": "token", "content": "Liverpool", "attempt": 1}

# Draft generation complete, judge is evaluating
data: {"type": "judging"}

# Judge passed — draft is verified
data: {"type": "verified"}

# Judge failed — draft is being retried
data: {"type": "retry", "attempt": 2}

# All retries exhausted, returning best available answer
data: {"type": "exhausted"}

# Simple responder response (not streamed, sent as single event)
data: {"type": "simple", "content": "Sure, I can help with that!"}

# Stream complete
data: {"type": "done"}
```



#### Concurrent Streaming and Buffer Accumulation

When the Draft Generator runs in Groq streaming mode, the server simultaneously forwards tokens to the client and accumulates them in a buffer string. The Decision Judge receives this buffer after streaming completes:

```python
async def stream_and_accumulate(groq_stream) -> AsyncGenerator[str, None]:
    buffer = []
    async for chunk in groq_stream:
        token = chunk.choices[0].delta.content or ""
        if token:
            buffer.append(token)
            yield f'data: {{"type": "token", "content": {json.dumps(token)}}}\n\n'
    # After all tokens yielded, run judge on the full buffer
    full_draft = "".join(buffer)
    yield f'data: {{"type": "judging"}}\n\n'
    verdict = run_decision_judge(full_draft, retrieved_chunks)
    if verdict["status"] == "PASS":
        yield f'data: {{"type": "verified"}}\n\n'
    else:
        yield f'data: {{"type": "retry", "attempt": attempt + 1}}\n\n'
```



#### Retry Behaviour

On a `FAIL` verdict, the graph loops back to the Query Rewriter as in the current architecture, with the addition that a `retry` event is emitted over SSE before the loop begins. The frontend clears the streamed draft on receiving this event. The new draft streams fresh from the beginning of the next attempt, with the same opacity treatment.

Maximum retries remain at 3. If all 3 attempts fail, an `exhausted` event is emitted and the best available draft (the one with the lowest hallucination score from the judge, if the judge returns structured scoring) is sent as a final `token` event followed by `done`.

### Frontend Implementation

The vanilla JS frontend is extended with an SSE consumer. No framework changes are required.

#### SSE Connection

```javascript
async function sendMessage(query) {
    const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, session_id: sessionId })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let currentBubble = createMessageBubble('assistant', { tentative: true });

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                const event = JSON.parse(line.slice(6));
                handleEvent(event, currentBubble);
            }
        }
    }
}
```



#### Event Handling and Visual Treatment

```javascript
function handleEvent(event, bubble) {
    switch (event.type) {
        case 'token':
            bubble.appendText(event.content);         // Append token to chat bubble
            break;
        case 'judging':
            bubble.setStatus('verifying...');          // Show status label
            break;
        case 'verified':
            bubble.setOpacity(1.0);                   // Full opacity
            bubble.clearStatus();                      // Remove "verifying..." label
            break;
        case 'retry':
            bubble.clear();                            // Wipe streamed text
            bubble.setStatus(`Retrying (attempt ${event.attempt})...`);
            break;
        case 'exhausted':
            bubble.setStatus('Best available answer:');
            break;
        case 'simple':
            bubble.setText(event.content);             // Non-streamed simple response
            bubble.setOpacity(1.0);
            break;
        case 'done':
            bubble.finalise();                         // Lock bubble, remove cursor
            break;
    }
}
```



#### Visual Design

- **Tentative draft (streaming):** `opacity: 0.45`, blinking cursor at end of text, subtle "verifying..." label in muted text below the bubble.
- **Verified draft:** Smooth CSS transition `opacity: 1.0` over 200ms, cursor removed, status label fades out.
- **Retry:** Draft text fades out over 150ms and is removed. Status label updates to "Retrying...".
- **Thinking indicator:** During the Orchestrator and Query Rewriter phases (before streaming begins), a pulsing three-dot indicator is shown in the chat area to signal that the pipeline is active.



### Groq Streaming API

Groq's client supports streaming via the `stream=True` parameter, which returns an async generator compatible with the accumulation pattern above:

```python
stream = groq_client.chat.completions.create(
    model="qwen/qwen3.6-27b",
    messages=[{"role": "user", "content": prompt}],
    stream=True,
    # thinking mode off for draft generation
)
async for chunk in stream:
    yield chunk.choices[0].delta.content or ""
```

The local Ollama path also supports streaming via its `/api/generate` endpoint with `"stream": true`. Both paths are exposed through a unified `invoke_llm_stream()` async generator so the LangGraph node implementation is provider-agnostic.

---



## 6. Cross-Cutting Concerns



### Token Budget Awareness

Several enhancements add LLM calls to the pipeline. The cumulative impact on Groq's free tier TPM limit (8,000 tokens/minute for `qwen3.6-27b`) should be understood:


| Node                                 | Typical Token Usage       | Mode                   |
| ------------------------------------ | ------------------------- | ---------------------- |
| Snapshot Compressor (when triggered) | ~500 input + 300 output   | Non-thinking           |
| Query Rewriter                       | ~400 input + 80 output    | Non-thinking           |
| Orchestrator                         | ~100 input + 5 output     | Non-thinking           |
| Draft Generator                      | ~1,500 input + 400 output | Non-thinking, streamed |
| Decision Judge                       | ~2,000 input + 100 output | Thinking               |
| **Per-query total (approx.)**        | **~5,385 tokens**         |                        |


This approaches the 8,000 TPM limit in a single query when the Snapshot Compressor fires. The practical implication: back-to-back queries may occasionally trigger a 429, handled by the retry/backoff logic in Section 3. This is expected behaviour for the free tier.

**Mitigation:** Prompt caching on the Decision Judge's system prompt (which is static and long) meaningfully reduces effective TPM consumption. Structure the judge's system prompt as a stable prefix to maximise Groq's cache hit rate.

### `<think>` Tag Handling

`qwen/qwen3.6-27b` emits `<think>...</think>` blocks when thinking mode is enabled (Decision Judge role). The existing `invoke_llm()` stripping logic remains in place and is applied to all responses regardless of role. The raw response (including `<think>` blocks) is preserved in the `llm_calls` table for debugging. The stripped response is what flows downstream.

When streaming (Draft Generator, non-thinking mode), thinking blocks are not expected. If a `<think>` token is encountered during streaming, the frontend suppresses it from the rendered output and it is excluded from the accumulated buffer passed to the judge.

### Image Ingestion and Groq TPM

Image description calls to `qwen/qwen3.6-27b` consume tokens from the same TPM budget as text calls. Large images encoded as base64 have significant input token cost. If ingesting many images in a batch, implement a short delay between image calls to avoid saturating the TPM limit during ingestion. This only affects the ingestion path, not live query serving.

### BM25 Title Boosting for Ingested Files

The existing architecture repeats title fields during chunk indexing to boost BM25 scores for exact name matches. When ingesting user-uploaded files, the `source_file` filename (stripped of extension) and any detected `section_heading` should be injected as boosted prefix text in the BM25 corpus entry for each chunk, consistent with the existing boosting convention.

### Database Schema Additions

The following additions to `trace_logs.db` support the new features:

```sql
-- Snapshot state at time of each query
ALTER TABLE pipeline_runs ADD COLUMN snapshot_text TEXT;
ALTER TABLE pipeline_runs ADD COLUMN snapshot_token_count INTEGER;

-- Ingestion tracking
CREATE TABLE IF NOT EXISTS ingestion_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,           -- txt, pdf, csv, xlsx, image
    chunk_count INTEGER,
    relevance_verdict TEXT,            -- YES or NO
    error TEXT,                        -- FootballRelevanceError message if rejected
    duration_ms INTEGER,
    ingested_at TEXT DEFAULT (datetime('now'))
);

-- Streaming attempt tracking
ALTER TABLE loop_iterations ADD COLUMN streaming_tokens_before_retry INTEGER;
```

---

*Document version: 1.0 — Finalised June 2026*
*Covers enhancements to Pitchside as described in ARCHITECTURE.md v1.0*