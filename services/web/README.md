# Pitchside web (Next.js)
#
# Local:
#   cp .env.example .env.local
#   npm install
#   npm run dev
#
# Docker (from repo root):
#   docker compose up -d --build web
#
# Targets:
# - API p95 < 500ms for CRUD via gateway (chat send excluded)
# - LCP < 2.5s on mid-tier laptop / Wi-Fi for shell routes
# - Uptime SLO: 99.5% for web Deployment once in k8s

## Auth

- Modal via `?auth=signup` / `?auth=signin` (Sign up CTA, Ball Knowledge / Settings when logged out)
- Email/password register → 2FA setup → tokens
- Email/password login → optional 2FA step-up → tokens
- Google button redirects to gateway `/auth/oauth/google` (needs OAuth env + SPA-friendly callback later)
- Tokens: access `sessionStorage`, refresh `localStorage`
- Settings nav hidden until signed in

## Scripts

- `npm run dev` — turbopack dev server :3000
- `npm run build` / `npm start` — production
- `npm run lint` — ESLint

## Routes

| Path | View |
|------|------|
| `/` | Kickoff + Match Status |
| `/chat/[id]` | Chat thread + live pipeline status |
| `/leagues` | League list/create/search |
| `/knowledge` | Account Ball Knowledge upload/stats |
| `/live-events` | MCP-backed live scores |
| `/settings` | Provider and OAuth API keys |
| `/help` | Themed usage guide |

Browser requests use same-origin `/api`; the Next server rewrites them to
`API_URL`. WebSocket pipeline traffic goes directly to the local gateway on
`:8000`, or through the deployed app ingress at `/ws`.
