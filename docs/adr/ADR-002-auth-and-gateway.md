# ADR-002: Auth and Gateway (Phase 1)

**Status:** Accepted; amended by Phase 8 cutover  
**Date:** 2026-07-12

## Context

Phase 1 introduces the permanent API gateway and auth microservice. No monolith proxying.

## Decisions

### Gateway

- FastAPI BFF with fixed route table to microservice URLs.
- Served `frontend/` static assets directly in Phase 1 (superseded below).
- Proxies only `/auth/*` in Phase 1; other prefixes return `501 NOT_IMPLEMENTED`.
- `ANON_MESSAGE_LIMIT` middleware ready for `/chats/*` (Phase 2).

### Auth

- `users.first_name` required (register body) or from Google `given_name`.
- Email/password: register → `pending_2fa` → TOTP setup → `active`.
- Google OAuth: `active` immediately; **no 2FA**.
- JWT HS256; access 15m, refresh 7d with rotation stored in `auth.refresh_tokens`.
- Logout blocklists access token `jti` in Redis.

### Data

- Postgres schema `auth` via Alembic migration `001_initial_auth`.
- Redis for JWT blocklist and anon counters.

## Consequences

- Chat/RAG unavailable via gateway until Phases 2–6.
- Google OAuth requires `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` in env.

## Phase 8 amendment (2026-07-19)

- The gateway is API-only and no longer serves HTML or `/static/*`.
- Pitchside is the standalone Next.js service in `services/web`.
- Local UI traffic enters on `:3000`; Kubernetes UI traffic enters through
  `app.futbot.local`. API traffic is proxied from same-origin `/api`.
- The legacy root `frontend/` was removed after the cutover.
