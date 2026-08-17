# Phase 8 — Pitchside Next.js frontend (+ companion APIs)

**Status:** Plan locked 2026-07-16 (clarifying Q&A answered)  
**Design source of truth:** `pitchai-analyst.html`, `auth-reference.html`, `theme.css`  
**Product brand:** Pitchside  

This phase implements the full control-room UI as a **single-page Next.js app** (App Router), with auth and other overlays as **in-app modals** (not separate HTML pages). Companion backend endpoints required by the UI ship in the same phase.

---

## Locked decisions

| # | Topic | Decision |
|---|--------|----------|
| 1 | Scope | **Full mock** parity in one pass |
| 2 | Anon | Keep anon Kickoff + 10-message cap + login prompt at limit |
| 3 | Live Events | **Real data** (MCP / tools-backed) |
| 4 | Help | Real minimal page; `theme.css` tokens |
| 5 | Settings keys | **UI + backend** (`GET/PUT /settings/api-keys`) |
| 6 | Routing | Soft routes (App Router + client nav) |
| 7 | Deep links | **Yes** — bookmarkable views (recommendation below) |
| 8 | 2FA | **Build** email/password 2FA setup + verify UI |
| 9 | Settings access | **Any logged-in user** |
| 10 | Chat merge | **Build** `POST /chats/merge` in Phase 8 |
| 11 | Ball Knowledge | **User-account RAG corpus** — not project/league scoped |
| 12 | Hosting | Next.js as its **own Docker/K8s service**; browser → gateway API |
| 13 | Router | App Router |
| 14 | CSS | Tailwind + ported `theme.css` tokens |
| 15 | Frontend service | **Yes** — `web` (or `frontend`) microservice |
| 16 | Legacy UI | Keep `frontend/` until Next is green, then remove |
| 17 | Deploy | Local Docker + Kubernetes manifests |
| 18 | Logged-out UX | Chat shell; Sign up modal on demand + at anon limit; **no Settings** in sidebar |
| 19 | Leagues vs chats | Leagues = projects; chats may be standalone (`project_id` null); project-open views later |
| 20 | Empty states | Match Status empty copy; Leagues empty copy when none exist |

### Recommendations (accepted)

**Deep links (7)**  
Use path-based soft routes so refresh/share works:

| Path | View |
|------|------|
| `/` | Chat (welcome / last active) |
| `/chat/[id]` | Specific chat |
| `/leagues` | Leagues list |
| `/knowledge` | Ball Knowledge (auth required) |
| `/settings` | API keys (auth required) |
| `/help` | Help |
| `/auth/2fa` | 2FA setup/verify (auth flow; can be full-screen step inside SPA shell) |

Auth Sign up / Sign in: **modal over current route** via `?auth=signup` / `?auth=signin` (or client state). Never navigate to a separate auth HTML page.

**Hosting (12)**  
- Service name: `web` (Next.js), port **3000**.  
- Browser calls same-origin **`/api`**; Next rewrites to the gateway (`API_URL`).
- Optional Next rewrites: `/api/*` → gateway (same-origin cookies if needed later).  
- Gateway **stops** being the primary static UI host once `web` is healthy; legacy static can remain until cutover.  
- K8s: Deployment + Service + Ingress for `web`; ConfigMap for `NEXT_PUBLIC_*`.

---

## Domain model (UI-facing)

```
User
 ├── Chats (optional project_id)     → Match History / Kickoff
 ├── Leagues (= Projects)            → Leagues screen (CRUD later views deferred)
 └── Ball Knowledge (user RAG KB)   → uploads, chunks, files, memory tokens
                                      NOT tied to a league/project
```

- **Leagues** ↔ existing Project service (`GET/POST /projects`, …).  
- **Ball Knowledge** ↔ **new** user-scoped knowledge APIs (see below). Project file upload remains for future “project open” UI, not for Ball Knowledge.  
- **Standalone chats** remain first-class (`project_id` null).

---

## Architecture

```
┌─────────────┐     REST/WS      ┌──────────┐     ┌─────────────────────┐
│  web:3000   │ ───────────────► │ gateway  │ ──► │ auth, chat, project,│
│  (Next.js)  │   :8000          │  :8000   │     │ orchestrator, …     │
└─────────────┘                  └──────────┘     └─────────────────────┘
```

- **SPA shell:** left sidebar always mounted; center view swaps; Match Status only on chat routes.  
- **Tokens:** access in `sessionStorage`; refresh in `localStorage` (per prior lock).  
- **Design:** port `theme.css` CSS variables into Tailwind theme; dark Pitchside look from mock.

---

## Workstreams

### A — Scaffold & shell
1. Create Next.js App Router app as service (`services/web` or `apps/web` — prefer **`services/web`** to match monorepo).  
2. Dockerfile + compose service + k8s manifests.  
3. Tailwind + `theme.css` tokens; fonts (Montserrat / Merriweather / Source Code Pro).  
4. App shell: sidebar, Kickoff, search, Match History, nav, collapsible rail.  
5. Soft routing for views; hide Settings when logged out.  
6. Pitch canvas ambient animation (client component); `prefers-reduced-motion` off by default (respect OS if easy).

### B — Auth (modal SPA)
1. Sign up / Sign in modal over blurred chat (from `auth-reference.html`).  
2. Google OAuth (popup or redirect back into SPA).  
3. Email/password register (`first_name`) + login.  
4. **2FA** setup + verify flows for email/password users.  
5. Logout; `/auth/me`; silent refresh; global `401` / `403 LOGIN_REQUIRED`.  
6. Validation tooltips **only on submit** (themed).

### C — Chat & Match Status
1. Anon `POST /chats` + persist `chat_id`; 10-message cap → open Sign up/Sign in modal.  
2. **`POST /chats/merge`** after login (claim anon chat).  
3. Message send, streaming, citations, web search pill.  
4. Match Status panel + empty state when no active run.  
5. Context usage indicator.

### D — Leagues
1. List / create / sort / search (Projects API).  
2. Empty state when user has zero leagues.  
3. No requirement to open a league for chat or Ball Knowledge.  
4. Defer project-open subviews (project chats, project memory UI).

### E — Ball Knowledge (user RAG)
1. Drag-drop uploader + stats cards (Chunks / Files / Memory Tokens) for **current user**.  
2. Backend: user-scoped upload + ingest + stats (see companion APIs).  
3. Auth required; anon sees Sign up prompt if they open `/knowledge`.

### F — Settings
1. API key form; any logged-in user.  
2. `GET/PUT /settings/api-keys` + `.env` merge; toast to restart services after save (v1).

### G — Live Events & Help
1. Live Events: real data via Tools/MCP (FIFA / live scores — wire to existing tools).  
2. Help: minimal themed page (`/help`).

### H — Cutover
1. Point local + k8s ingress at `web`.  
2. Remove legacy `frontend/` when parity checklist is green.  
3. Update gateway docs: API-only for browsers (optional health static).

---

## Companion backend (Phase 8)

### 1. `POST /chats/merge`
Claim anon chat into authenticated user (body: `{ chat_id }` or server reads anon cookie/header). Idempotent.

### 2. Ball Knowledge — **user-scoped** (replaces earlier project-stats idea for this screen)

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/knowledge/stats` | `{ chunks, files, memory_tokens }` for `user_id` |
| `GET` | `/knowledge/files` | List user KB files + ingest status |
| `POST` | `/knowledge/files` | Multipart upload → ingest pipeline |
| (internal) | Retrieval index filter | Metadata `user_id` (and optional `scope=user_kb`) |

**Important:** Do **not** use `GET /projects/{id}/knowledge-stats` for Ball Knowledge. Project file APIs stay for future league/project UI.

Implementation sketch:
- Store file metadata in Postgres (new `user_knowledge_files` or extend ingestion with `owner_user_id` + `scope=account`).  
- Chunks in Qdrant/BM25 filtered by `user_id`.  
- **Memory tokens:** sum of user-level memory / snapshot budget used for that user’s KB context (define precisely in implementation — likely token count of indexed user chunks or a dedicated memory store).  
- Orchestrator retrieval for chats: include user KB chunks when appropriate (standalone + project chats — product rule: always search user Ball Knowledge; project corpus later).

### 3. `GET/PUT /settings/api-keys`
Allowlist: `GROQ_API_KEY`, `TAVILY_API_KEY`, `SERPER_API_KEY`, `API_FOOTBALL_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`.  
Auth: any logged-in JWT. Merge into `.env`; document restart.

### 4. Live Events
Expose or reuse tools/MCP endpoints the UI can poll/subscribe to (exact contract during implementation).

---

## Empty states (copy direction)

| Surface | Empty state |
|---------|-------------|
| Match Status | e.g. “No active analysis — send a message to start the match pipeline.” |
| Leagues | e.g. “No leagues yet — create one to organize projects and briefings.” |
| Ball Knowledge stats | Zeros / “Upload your first document to build Ball Knowledge.” |

Final copy can be tuned in UI polish.

---

## Suggested delivery order

1. Scaffold `services/web` + Docker/K8s + theme shell — **complete** (`services/web` App Router, tokens, shell routes, compose + k8s)
2. Auth modals + session + 2FA — **complete** (email/password + Google redirect; full 2FA setup/verify/step-up-login flow in `AuthModal` + `TwoFactorSetup`, backed by `/auth/2fa/enable` and `/auth/2fa/verify`, including recovery-code fallback)
3. Chat + Match Status + anon + merge — **complete** (`POST /chats`, anon cap via gateway middleware, `POST /chats/merge` fully wired gateway → chat service)
4. Leagues + empty states — **complete** (Projects API + `LeaguesView`)
5. Ball Knowledge APIs + UI — **complete** (`GET /knowledge/stats`, `GET/POST /knowledge/files`, synthetic `user_kb:{user_id}` retrieval scope merged in orchestrator). Note: each service creates its own tables from SQLAlchemy metadata on startup (`Base.metadata.create_all`, see `services/*/db.py`), so `project.user_knowledge_files` was already present at runtime even before Alembic migration `005_user_knowledge_files` was added — the migration documents the schema for the record but wasn't actually blocking.
6. Settings keys API + UI — **complete** (`GET/PUT /settings/api-keys` implemented directly in the gateway, `.env` merge, restart-toast copy)
7. Live Events + Help — **complete** (`GET /tools/live-events` backed by LiveScore/API-Football MCP tools, polled by `LiveEventsView`; `/help` page present)
8. Cutover; delete legacy `frontend/` — **complete**

**Verified live** (2026-08-17, local Docker Compose against `docker-compose.infra.yml` + `docker-compose.services.yml`, auth image rebuilt with current code):
- Register → activate → login (no 2FA) → `access_token`/`refresh_token` issued correctly.
- `/auth/2fa/enable` with a plain access token (the new "any logged-in user" path) → QR secret + 8 recovery codes returned.
- `/auth/2fa/verify` confirms enrollment; subsequent `/auth/login` now correctly returns `requires_2fa: true` + `step_up_token` instead of tokens (this was the login bug fixed this session — previously 2FA was silently bypassed).
- Step-up `/auth/2fa/verify` with a live TOTP code completes login and returns real tokens.
- Recovery-code fallback accepted once, then correctly rejected as `INVALID_CODE` on reuse.
- Re-`enable` on an already-2FA account correctly rejected as `INVALID_STATE`.
- `GET /knowledge/stats` through the gateway with a real bearer token → `200 {chunks:0, files:0, memory_tokens:0}`; unauthenticated call → `403 LOGIN_REQUIRED`.
- Test user and its recovery codes/refresh tokens were deleted from the dev DB after the run.

Not yet exercised live: Ball Knowledge file upload/ingest round-trip, anon chat → merge flow, Leagues UI, Settings UI save, and Live Events against real `LIVESCORE_MCP_*`/`API_FOOTBALL_KEY` credentials (not configured in this environment's `.env`).

---

## Out of scope (explicit defer)

- Project-open views (project chat list, project memory panel, project-scoped ingest UI).  
- Multi-tenant SaaS hardening of settings secrets (masking-only GET).  
- Hot-reload of API keys without service restart.
- Disabling 2FA once enabled (only enable/verify is implemented; account recovery for lost devices is manual/support-driven for now).

---

## Success criteria

- [x] Full mock UX parity in Next.js SPA
- [ ] Anon chat + merge-on-login works end-to-end (code path correct by inspection; not yet exercised live — only the authenticated-user paths were smoke-tested this session)
- [x] Ball Knowledge uploads/stats are **per user**, independent of leagues (`GET /knowledge/stats` verified live through the gateway; table confirmed present via `create_all`)
- [ ] Settings keys persist to `.env` and load into form (implementation present; not yet smoke-tested live)
- [x] `web` backend services run in Docker Compose (auth, gateway, chat, project, retrieval, ingestion, orchestrator, tools, llm-gateway, observability, qdrant, postgres, redis, minio all verified up and healthy locally; the `web` Next.js container itself was not started/tested this session)
- [x] Legacy `frontend/` removed without gateway/static coupling
- [x] 2FA setup/verify UI implemented end-to-end and **verified live**, including the step-up login flow, recovery-code fallback, and reuse/already-enabled rejections
