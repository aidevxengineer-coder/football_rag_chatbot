# Pitchside UI Requirements

**Status:** Living document — updated as each backend phase lands.  
**Purpose:** Collect every UI-facing requirement discovered during Phases 0–7 so Phase 8 can implement the full frontend in one pass without re-reading ADRs, plans, or service code.

**Related:** Microservices architecture plan (`.cursor/plans/`) · [ADR-001](adr/ADR-001-service-boundaries.md) · [ADR-002](adr/ADR-002-auth-and-gateway.md) · [football_rag_prd.md](football_rag_prd.md) · `pitchai-analyst.html` (design reference) · Next.js app (Phase 8, replaces legacy `frontend/`)

---

## Phase 8 — Locked design decisions (2026-07-16)

| Area | Decision |
|------|----------|
| **Framework** | Next.js — scrap legacy `frontend/` |
| **Brand** | **Pitchside** (from `pitchai-analyst.html`) |
| **Design reference** | `pitchai-analyst.html` — evolve via 21st.dev Magic MCP |
| **Layout** | Control room (Option B) + search field in left panel (Option A) |
| **Left panel** | Football-themed copy: **Kickoff** (create chat), Match History (with relative time labels: `12h` / `10m` / `2d`), Your Leagues, Ball Knowledge, Live Events — **not** "New Chat" |
| **Pitch canvas** | Ambient canvas animation: faint player nodes + ball-passing loop behind chat (`#pitch-anim` in `pitchai-analyst.html`). Prefer `prefers-reduced-motion` off in Next.js production build. |
| **Left panel search** | `Search matches…` filter above match history list |
| **Right panel title** | **Match Status** (pipeline / WS stage cards) |
| **Auth UI** | Reference: `auth-reference.html` (matches `auth ss.png` + `theme.css` dark tokens). Register card with **Google** OAuth only, **first name**, email/password, primary CTA. Modal over blurred/darkened chat. Empty-field warnings use themed tooltips (`--destructive` / `--popover`), not browser defaults. |
| **Anon users** | `POST /chats` without JWT; merge on login via `POST /chats/merge` (to build) |
| **Sidebar auth CTA** | When **not logged in**, footer shows **Sign up** (opens auth modal). When logged in, same slot shows **Logout**. Auth modal toggles Sign up ↔ Sign in (no first name on Sign in; Google OAuth on both). |
| **Leagues screen** | Sidebar stays; main replaces chat with Projects-style layout (title, sort, New league, search, cards). Maps to `GET/POST /projects`. |
| **Ball Knowledge screen** | Sidebar stays; Match Status hidden. **User-account RAG knowledge** (not league/project). Drag-drop upload + stats: Chunks / Files / Memory Tokens for the **logged-in user**. See [Ball Knowledge backend](#ball-knowledge-backend). |
| **Settings screen** | Sidebar stays; Match Status hidden. API keys form; **any logged-in user**. Prefill/save via `GET/PUT /settings/api-keys`. **Hidden when logged out.** |
| **SPA** | Single Next.js app; auth as in-app modal (not separate pages). Soft routes; design from HTML mocks. |
| **Web search toggle** | Pill **to the right** of disclaimer: `AI analysis can make mistakes…` \| `[ Web search ]` |
| **HCI / anti-AI** | One pitch-green accent; labels not icon-only; flat pipeline cards; no sparkles / robot avatars |
| **Phase 8 plan** | [PHASE_8_PLAN.md](PHASE_8_PLAN.md) — full locked Q&A + workstreams |

### Input footer row

```
[ liquid-glass input pill ]
AI analysis can make mistakes. Verify critical match data.     [ Web search ]
← disclaimer (left)                                              toggle (right) →
```

### Left sidebar structure (Control room + search)

1. Pitchside wordmark  
2. **Kickoff** CTA (liquid glass + football icon)  
3. Search field  
4. **Match History** (section, expandable) — chat list from `GET /chats`  
5. **Leagues** — projects (`GET /projects`); opens Leagues screen  
6. **Ball Knowledge** — opens knowledge screen (upload + stats) for active league  
7. **Settings** — opens Settings screen (API keys)  
8. **Live Events** — football context / MCP hooks  
9. Footer: Help · **Sign up** (anon) or **Logout** (authenticated)

### Right panel — Match Status

- Header: **Match Status** + run metadata (classification chip, iteration)  
- Stage cards with left accent bar: done / active / pending / failed  
- Tool stages as first-class rows (`tool:web_search`, etc.)  
- Active card shows live detail (query snippet, chunk count)


## Maintenance process

| When | Action |
|------|--------|
| **End of each phase** | Add or extend the matching section below with screens, states, API fields, and error handling discovered in that phase. |
| **API contract change** | Update the [API reference](#api-reference) table and any dependent screen specs. |
| **Phase 8 start** | Use [Phase 8 implementation checklist](#phase-8-implementation-checklist) as the master backlog; tick items as built. |

**Rule:** Backend phases ship API-only (no `frontend/` changes) unless explicitly noted. This doc is the single source of truth for deferred UI work.

---

## Design foundations

Inherited from the existing monolith UI and PRD; Phase 8 should preserve or evolve these unless overridden below.

| Area | Requirement |
|------|-------------|
| **Visual style** | Pitchside — dark pitch palette, liquid-glass input, pitch-pattern canvas (`pitchai-analyst.html`) |
| **Typography** | From `theme.css`: Montserrat (sans / body), Merriweather (serif / headlines), Source Code Pro (mono / labels); `letter-spacing: 0em` |
| **Layout** | Three-column: **sidebar** (nav + search + match history) · **main chat** · **Match Status** panel |
| **Responsive** | Collapsible sidebar via mobile menu button; chat remains primary on small screens |
| **Message bubbles** | Distinct user vs assistant styling; assistant messages support streaming partial text |
| **Welcome state** | Empty chat shows hero copy + suggested intent (football analyst positioning) |
| **Input** | Textarea with auto-resize; Enter to send, Shift+Enter newline; disabled while awaiting reply |
| **Accessibility** | `aria-live` on messages and status regions; keyboard-send; sufficient color contrast on theme |

### Legacy UI inventory (monolith — migrate in Phase 8)

| Element | Current behavior | Phase 8 target |
|---------|------------------|----------------|
| `#sidebar` | Session id, new chat, ingest file picker | Auth user menu, chat list, project selector |
| `#messages` | Chat history from `GET /api/session/{id}` | `GET /chats/{id}/messages` + streaming append |
| `#pipeline-panel` | WebSocket `/ws/pipeline` stage cards | Same via Realtime Gateway (`/ws/*`) |
| `#ingest-btn` | Direct monolith ingest | `POST /projects/{id}/files` + ingest status poll |
| `localStorage` session id | Client-generated `sess_*` | JWT + server `chat_id`; anon chat id in `localStorage` until login |

---

## Phase 0 — Foundation

| ID | Requirement | API / notes |
|----|-------------|-------------|
| P0-01 | Gateway served static `frontend/` at `/` and `/static/*` | Retired by Phase 8; gateway is now API-only |
| P0-02 | All non-auth API routes return `501` until their phase | UI must handle `501` gracefully if old endpoints are called |

---

## Phase 1 — Auth & gateway

Backend only in Phase 1. UI requirements captured for Phase 8.

### Screens

#### Register (email / password)

| Field / action | Rule |
|----------------|------|
| `email` | Required, validated format |
| `password` | Required, strength hint (min length TBD in Phase 8) |
| `first_name` | **Required** |
| Submit | `POST /auth/register` → user status `pending_2fa` |
| Next step | Redirect to 2FA setup (not skippable for email/password) |

#### 2FA setup (email / password users only)

| Step | Rule |
|------|------|
| Show QR / secret | From `POST /auth/2fa/enable` response |
| Verify TOTP | `POST /auth/2fa/verify` → status becomes `active` |
| Recovery codes | Display once after enable; copy/download affordance |
| Google OAuth users | **Skip entire 2FA flow** — active immediately |

#### Login

| Flow | Rule |
|------|------|
| Email + password | `POST /auth/login` |
| 2FA step-up | If TOTP enabled, second step before tokens issued |
| Google OAuth | `GET /auth/oauth/google` → callback sets JWT |
| Tokens | Store access token (memory or `sessionStorage`); refresh via `POST /auth/refresh` |
| Logout | `POST /auth/logout` + clear local tokens |

#### Session / profile

| Item | Rule |
|------|------|
| Display name | `first_name` from `GET /auth/me` |
| Token refresh | Silent refresh before expiry; redirect to login on `401` |

### Error states

| Code | UI behavior |
|------|-------------|
| `401` | Clear tokens → login screen |
| `403 LOGIN_REQUIRED` | Modal or inline prompt: sign in to continue (see Phase 2 anon rules) |
| `409` / validation errors | Inline field errors from response body |

---

## Phase 2 — Chat & project

Backend ships chat/project CRUD and **context usage API**. No frontend changes in Phase 2.

### Chat list & navigation (authenticated)

| ID | Requirement | API |
|----|-------------|-----|
| P2-01 | Sidebar lists recent chats, newest first | `GET /chats?limit=&sort=-updated_at` |
| P2-02 | Filter chats by project when a project is selected | `GET /chats?project_id={id}` |
| P2-03 | Standalone chats (`project_id` null) shown without project badge | `GET /chats` — omit project filter |
| P2-04 | Create new chat | `POST /chats` `{ title?, project_id? }` |
| P2-05 | Delete chat with confirmation | `DELETE /chats/{id}` (hard delete) |
| P2-06 | Open chat loads full history | `GET /chats/{id}/messages` |
| P2-07 | Export chat | `GET /chats/{id}/export?format=markdown\|json` — download file |

### Anonymous access

| ID | Requirement | API / behavior |
|----|-------------|----------------|
| P2-08 | Visitor can start one anon chat without login | `POST /chats` without JWT → `user_id` null |
| P2-09 | Anon user can send messages on that chat only | `POST /chats/{id}/messages` |
| P2-10 | **10 message cap** for anon on a single chat | Gateway returns `403 LOGIN_REQUIRED` when exceeded |
| P2-11 | Anon cannot list chats, delete, export, or use projects | `403 LOGIN_REQUIRED` on protected routes |
| P2-12 | Login popup when anon hits limit or protected action | Merge anon chat to user account — **deferred detail to Phase 8** (may require new API) |
| P2-13 | Persist anon `chat_id` in `localStorage` so refresh resumes same chat | Client-side only until login |

### Project management (authenticated only)

| ID | Requirement | API |
|----|-------------|-----|
| P2-14 | Project selector in sidebar (or header) | `GET /projects` |
| P2-15 | Create project modal | `POST /projects` `{ name, description? }` |
| P2-16 | Delete project with confirmation | `DELETE /projects/{id}` |
| P2-17 | View project files list | `GET /projects/{id}/files` |
| P2-18 | Upload file to project | `POST /projects/{id}/files` multipart |
| P2-19 | File row shows `status` (`pending`, etc.) | From `project_files.status` |
| P2-20 | Project context summary (memory + files) | `GET /projects/{id}/context` |

### Context usage indicator

| ID | Requirement | API / behavior |
|----|-------------|----------------|
| P2-21 | Show **context used %** for active chat | `context_usage.percent_used` on `GET /chats/{id}` and after `POST /chats/{id}/messages` |
| P2-22 | Display `used_tokens / limit_tokens` on hover or sublabel | `context_usage.used_tokens`, `context_usage.limit_tokens` |
| P2-22b | Optional breakdown tooltip | `context_usage.breakdown.{snapshot,hot_messages,current_query,memory,retrieved_chunks}` |
| P2-23 | Progress bar or ring near chat header / input area | Visual only in Phase 8; data available Phase 2 |
| P2-24 | Warning state when `percent_used >= 85` | `should_compress: true` in response |
| P2-25 | Optional “compressing context…” state | `compression_pending: true` on chat (cleared after Phase 3 LLM compress) |
| P2-26 | Budget is env-driven (`CONTEXT_BUDGET_TOKENS`, default 8192) | UI displays server values, does not hardcode limit |

**Suggested component:** `#context-usage-bar` in chat header — green &lt; 70%, amber 70–84%, red ≥ 85%.

### Messaging (Phase 2 — CRUD only, no RAG replies)

| ID | Requirement | Notes |
|----|-------------|-------|
| P2-27 | Send user message stores via API | `POST /chats/{id}/messages` `{ role: "user", content }` |
| P2-28 | No assistant pipeline reply until Phase 6 | UI may show “RAG not connected” in dev or hide send affordance for assistant |

---

## Phase 3 — LLM gateway

Backend only. UI-relevant contracts for Phase 8 streaming.

| ID | Requirement | API / notes |
|----|-------------|-------------|
| P3-01 | Auto-compress runs server-side when threshold hit | Inline on `POST /chats/{id}/messages`; Chat → internal `POST /llm/compress`; show P2-25 while `compression_pending` |
| P3-02 | Rate limit (`429`) shows retry message | Exponential backoff hint; disable send briefly |
| P3-03 | Streaming tokens for draft generation | Consumed via orchestrator/realtime in Phase 6 |

---

## Phase 4 — Retrieval

| ID | Requirement | API / notes |
|----|-------------|-------------|
| P4-01 | Citation metadata on chunks: `chunk_id`, `source_file`, `page`, `section_heading` | Attached to assistant messages as `citations_json` |
| P4-02 | Project-scoped retrieval only when chat has `project_id` | Standalone chats use global KB — UI copy should explain scope |
| P4-03 | Prepare citation link component (href or expand panel) | Phase 8 renders; data available Phase 4+ |

---

## Phase 5 — Ingestion

| ID | Requirement | API / notes |
|----|-------------|-------------|
| P5-01 | After file upload, show ingest progress | Poll `GET /projects/{id}/files` until `status` → `ingested` or `failed` |
| P5-02 | Ingest failure shows error state on file row | `status=failed` + optional error message field |
| P5-03 | Project file ingest (future project-open UI) | `POST /projects/{id}/files` — **not** Ball Knowledge |
| P5-04 | Accepted formats: `.txt`, `.md`, `.csv`, `.xlsx`, `.pdf`, images | Match `accept` on file input |
| P5-05 | Ball Knowledge drag-and-drop uploader | User-scoped `POST /knowledge/files` |
| P5-06 | Ball Knowledge **Chunks / Files / Memory Tokens** | `GET /knowledge/stats` (per user) |

---

## Ball Knowledge backend

Ball Knowledge is the **per-user RAG knowledge base** (account-scoped). It is **not** league/project data. Leagues (= projects) are separate; chats may exist with `project_id` null.

| Metric | Ideal UI field | Backend work |
|--------|----------------|--------------|
| **Files** | Count of files in the user’s KB | User-scoped file list/metadata |
| **Chunks** | Indexed chunk count for that user | Retrieval stats filtered by `user_id` |
| **Memory Tokens** | Token total for the user’s knowledge/memory budget | Aggregate for that user (define in Phase 8 impl) |

### Proposed API (Phase 8)

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/knowledge/stats` | JWT → `{ chunks, files, memory_tokens }` |
| `GET` | `/knowledge/files` | JWT |
| `POST` | `/knowledge/files` | JWT multipart upload + ingest |

Do **not** use `GET /projects/{id}/knowledge-stats` for this screen. Project file APIs remain for a later project-open UI.

**Implementation notes:** index chunks with `user_id` metadata; orchestrator may retrieve from user KB on chat turns; anon users must sign in to use Ball Knowledge.

---

## Settings / API keys backend

Settings UI lets a self-hosted operator enter third-party keys used by LLM, tools, and OAuth. Keys today live only in repo-root `.env` (see `.env.example`). **There is no settings API yet** — Phase 8 UI mock exists in `pitchai-analyst.html`; backend must be added.

### Keys exposed in Settings

| Env var | Used by | Purpose |
|---------|---------|---------|
| `GROQ_API_KEY` | LLM gateway | Groq provider (`LLM_PROVIDER=groq`) |
| `TAVILY_API_KEY` | Tools | Web search (Tavily) |
| `SERPER_API_KEY` | Tools | Web search (Serper) |
| `API_FOOTBALL_KEY` | Tools / MCP | API-Football MCP |
| `GOOGLE_CLIENT_ID` | Auth | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Auth | Google OAuth |

Infra secrets (`JWT_SECRET`, Postgres, MinIO, Redis) stay out of this screen — deploy/ops only.

### Proposed API (Phase 8 companion)

| Method | Path | Auth | Behavior |
|--------|------|------|----------|
| `GET` | `/settings/api-keys` | JWT (any logged-in user) | Read allowlisted keys from server `.env`. Prefill Settings form. |
| `PUT` | `/settings/api-keys` | JWT (any logged-in user) | Upsert provided keys into `.env` (merge). Return updated map. |

```json
{
  "data": {
    "GROQ_API_KEY": "gsk_…",
    "TAVILY_API_KEY": "",
    "SERPER_API_KEY": "…",
    "API_FOOTBALL_KEY": "",
    "GOOGLE_CLIENT_ID": "….apps.googleusercontent.com",
    "GOOGLE_CLIENT_SECRET": "…"
  }
}
```

**Implementation notes:**

1. **Gateway (or small config service)** — own routes; resolve `.env` path via `ENV_FILE` (default: repo/process working dir `.env`). Create from `.env.example` if missing.
2. **GET when `.env` exists** — parse and return only the allowlisted keys above (empty string if unset). UI fills inputs. Prefer returning real values only for trusted self-host admin; optional `configured: true` + masked preview for multi-tenant later.
3. **PUT** — validate key names against allowlist; update/insert lines in `.env`; never log raw secrets.
4. **Runtime reload** — writing `.env` alone does not refresh already-running containers/processes. Options: (a) document restart required; (b) push updates into a shared secrets store / Redis and teach LLM/Tools/Auth to re-read; (c) hot-reload via SIGHUP where supported. Prefer (a) for v1 + toast “Restart services to apply.”
5. **Docker** — Compose uses `env_file: .env`; after PUT, operator restarts affected services (`llm_gateway`, `tools`, `auth`) or the stack.
6. **Security** — require authenticated user (any logged-in JWT per Phase 8 lock); never log raw secrets; CSRF on cookie sessions if used.  
7. **UI** — Settings hidden when logged out; password-type inputs; Save → `PUT /settings/api-keys`.

---

## Phase 6 — RAG orchestrator, realtime, observability

| ID | Requirement | API / notes |
|----|-------------|-------------|
| P6-01 | Send message triggers full RAG pipeline | `POST /chats/{id}/messages` or `POST /pipeline/run` (final contract TBD) |
| P6-02 | **Live pipeline panel** — stage timeline | WebSocket `/ws/*` events (migrate existing `#pipeline-panel`) |
| P6-03 | Stage labels | `collecting_context`, `rewriting`, `orchestrating`, `retrieving`, `drafting`, `judging`, `responding` |
| P6-04 | Stream assistant tokens into message bubble | SSE or WS token events |
| P6-05 | On `retry` event, clear partial draft and restart stream | Per ENHANCEMENTS.md protocol |
| P6-06 | Typing / pipeline-running indicator on input | Disable send while `isWaitingForReply` |
| P6-07 | **Citations** under assistant bubble — collapsible | `citations_json` from persisted message |
| P6-08 | Clickable citation links | Open source detail or scroll to chunk ref |
| P6-09 | Fallback message when max retries exhausted | Orchestrator returns user-facing fallback string |
| P6-10 | Debug / trace panel (optional, power users) | `GET /traces/{run_id}` — span tree from Observability service |
| P6-11 | Link OTel trace id to domain graph if both exposed | For developers / support mode |

### SSE / WS event protocol (assistant streaming)

Align with `docs/ENHANCEMENTS.md`:

| Event `type` | UI action |
|--------------|-----------|
| `token` | Append to current assistant bubble |
| `judging` | Show “Verifying…” substate |
| `verified` | Mark draft verified |
| `retry` | Clear bubble content; show attempt badge |
| `exhausted` | Show fallback styling |
| `simple` | Replace with non-streamed simple response |
| `done` | Enable input; persist final message |

---

## Phase 7 — Tools & MCP

| ID | Requirement | API / notes |
|----|-------------|-------------|
| P7-01 | Web search toggle on send | `POST /chats/{id}/messages` `web_search_enabled: bool` |
| P7-02 | Show tool invocation in pipeline panel | New stage cards e.g. `tool:web_search` |
| P7-03 | Surface tool errors inline in assistant message or panel | Non-fatal tool failure copy |

---

## Phase 8 — Implementation checklist

Master backlog for the full UI build. See [PHASE_8_PLAN.md](PHASE_8_PLAN.md) for the locked plan.

### Shell & auth
- [ ] Scaffold Next.js App Router as **`web` service** (Docker + K8s)
- [ ] P1 — Register (incl. **first_name**), login, Google OAuth, **2FA**, logout, `/auth/me`
- [ ] P1 — Auth **modal** over chat (SPA); Sign up ↔ Sign in
- [ ] P1 — Sidebar: **Sign up** when anon; **Logout** when auth; **no Settings when logged out**
- [ ] P1 — Token refresh + global `401` / `403 LOGIN_REQUIRED` handler

### Chat & sidebar
- [ ] P2-01–P2-07 — Chat list, CRUD, export
- [ ] P2-08–P2-13 — Anonymous flow + auth modal at limit
- [ ] **`POST /chats/merge`** on login
- [ ] P2-21–P2-26 — Context usage bar
- [ ] Soft routes: `/`, `/chat/[id]`, `/leagues`, `/knowledge`, `/settings`, `/help`
- [ ] Leagues screen + empty state
- [ ] Match Status + empty state
- [ ] Ball Knowledge — user KB upload + stats
- [ ] Settings — API keys via `/settings/api-keys`
- [ ] Live Events — real MCP/tools data
- [ ] Help — minimal themed page

### Backend companions
- [ ] User-scoped `/knowledge/*` — see [Ball Knowledge backend](#ball-knowledge-backend)
- [ ] `GET/PUT /settings/api-keys` — see [Settings / API keys backend](#settings--api-keys-backend)
- [x] Cutover: remove legacy `frontend/`; gateway is API-only

### RAG experience
- [ ] P6-01–P6-09 — Pipeline send, streaming, citations, retry behavior
- [ ] P6-02–P6-03 — Match Status panel
- [ ] P4-03, P6-07–P6-08 — Citation UI
- [ ] P3-02 — Rate limit UX

### Tools & debug
- [ ] P7-01–P7-03 — Tool settings + pipeline cards
- [ ] P6-10–P6-11 — Optional trace debug panel

### Quality
- [ ] Responsive sidebar
- [ ] Accessibility pass
- [ ] Contract tests against gateway

---

## API reference

| UI concern | Method | Path | Auth | Phase |
|------------|--------|------|------|-------|
| Register | POST | `/auth/register` | No | 1 |
| Login | POST | `/auth/login` | No | 1 |
| Google OAuth | GET | `/auth/oauth/google` | No | 1 |
| 2FA | POST | `/auth/2fa/*` | JWT | 1 |
| Me | GET | `/auth/me` | JWT | 1 |
| Refresh | POST | `/auth/refresh` | Refresh cookie/body | 1 |
| Logout | POST | `/auth/logout` | JWT | 1 |
| List chats | GET | `/chats` | JWT | 2 |
| Create chat | POST | `/chats` | Optional | 2 |
| Get chat + usage | GET | `/chats/{id}` | Optional | 2 |
| Messages | GET | `/chats/{id}/messages` | Optional | 2 |
| Send message | POST | `/chats/{id}/messages` | Optional | 2 |
| Export | GET | `/chats/{id}/export` | JWT | 2 |
| Delete chat | DELETE | `/chats/{id}` | JWT | 2 |
| List projects | GET | `/projects` | JWT | 2 |
| Create project | POST | `/projects` | JWT | 2 |
| Upload file | POST | `/projects/{id}/files` | JWT | 2 |
| Project context | GET | `/projects/{id}/context` | JWT | 2 |
| Knowledge stats | GET | `/knowledge/stats` | JWT | **TBD** Phase 8 |
| Knowledge files | GET/POST | `/knowledge/files` | JWT | **TBD** Phase 8 |
| API keys (settings) | GET | `/settings/api-keys` | JWT | **TBD** Phase 8 |
| API keys (settings) | PUT | `/settings/api-keys` | JWT | **TBD** Phase 8 |
| Chat merge | POST | `/chats/merge` | JWT | **TBD** Phase 8 |
| List tools | GET | `/tools` | JWT | 7 |
| Run pipeline | POST | `/pipeline/run` | JWT | 6 |
| Pipeline WS | WS | `/ws/*` | Optional | 6 |
| Traces | GET | `/traces/{id}` | JWT | 6 |

### `context_usage` response shape (Phase 2+)

Budget = **full next-turn LLM prompt**: snapshot + hot messages + current query + project memory + retrieved chunks (0 until Phase 6 RAG).

```json
{
  "context_usage": {
    "used_tokens": 6120,
    "limit_tokens": 8192,
    "percent_used": 74.7,
    "breakdown": {
      "snapshot": 500,
      "hot_messages": 2000,
      "current_query": 0,
      "memory": 300,
      "retrieved_chunks": 0
    }
  },
  "should_compress": false,
  "compression_pending": false
}
```

---

## Changelog

| Date | Phase | Changes |
|------|-------|---------|
| 2026-07-13 | 2 | Phase 2 implemented: full prompt budget breakdown in context_usage API |
| 2026-07-13 | 3 | Phase 3 implemented: LLM gateway (internal), inline auto-compress on message POST, `/llm/*` stays 501 on public gateway |
| 2026-07-14 | 4 | Phase 4 implemented: retrieval service (Qdrant + BM25 + RRF), citation metadata on chunks, `/retrieve/*` internal-only |
| 2026-07-14 | 5 | Phase 5 implemented: ingestion service (async jobs), project upload auto-trigger, `error_message` on files, `/ingest/*` internal-only |
| 2026-07-14 | 6 | Phase 6 implemented: RAG orchestrator (LangGraph), chat inline RAG on message POST, WS `/ws/pipeline`, observability `GET /traces/{id}`, monolith `/api/chat` → 501 |
| 2026-07-15 | 7 | Phase 7 implemented: tools service (`:8088`), web search opt-in, football MCP, PDF export, TOOL pipeline path, `tool_notice` / `tool_calls` tracing, `GET /tools` on gateway |
| 2026-07-16 | 8 | Phase 8 design locked: Next.js + Pitchside (`pitchai-analyst.html`), Control room + search, Match Status panel, sessionStorage auth, web search pill on disclaimer row |
| 2026-07-16 | 8 | Auth modal + first_name; Login↔Logout sidebar CTA; Leagues screen; Ball Knowledge screen + documented `knowledge-stats` backend gap |
| 2026-07-16 | 8 | Settings screen: API key fields; documented `GET/PUT /settings/api-keys` + `.env` sync |
| 2026-07-16 | 8 | Phase 8 plan locked ([PHASE_8_PLAN.md](PHASE_8_PLAN.md)): SPA Next.js `web` service; Ball Knowledge = user RAG (not projects); full mock + companion APIs |
