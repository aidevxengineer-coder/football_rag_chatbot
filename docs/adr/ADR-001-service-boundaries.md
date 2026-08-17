# ADR-001: Microservices Boundaries and Communication

**Status:** Accepted  
**Date:** 2026-07-12  
**Context:** Phase 0 foundation for strangler-pattern migration from FutBot monolith.

## Decision

Pitchside (formerly FutBot) will be decomposed into bounded-context microservices behind an API Gateway, communicating via sync REST for request/response paths and async events (Redis) for ingestion and observability fan-out.

## Service boundaries

| Service | Owns | Does not own |
|---------|------|--------------|
| **Gateway** | Routing, JWT validation, rate limits | Business logic |
| **Auth** | Users, OAuth, 2FA, tokens | Chat content |
| **Chat** | Chats, messages, snapshots, export | Vector indexes |
| **Project** | Projects, file metadata, inter-chat memory | File extraction |
| **RAG Orchestrator** | LangGraph workflow, citations assembly | Vector storage |
| **Retrieval** | Hybrid search, BM25, embeddings index | LLM calls |
| **Ingestion** | Upload, extract, chunk, enqueue | Index storage logic |
| **LLM Gateway** | Provider routing, streaming, retries | Pipeline routing |
| **Tools** | External APIs, MCP, web search | Retrieval |
| **Realtime** | WebSocket/SSE to browsers | Pipeline execution |
| **Observability** | Pipeline run graphs, audit traces | Application state |

## Communication patterns

- **Sync REST:** Gateway → domain services; Orchestrator → LLM Gateway, Retrieval, Chat (latency-sensitive chat path).
- **Async events (Redis Streams/queue):** Ingestion → Retrieval index rebuild; Orchestrator → Observability span writes.
- **Pub/Sub (Redis):** Orchestrator → Realtime Gateway → browser WebSockets.

## Data ownership

- **Postgres:** per-service schemas (`auth`, `chat`, `project`, `observability`).
- **Redis:** JWT blocklist, session cache, pub/sub, Celery broker (separate key prefixes).
- **MinIO/S3:** raw uploaded files (Project Service metadata, Ingestion Service bytes).
- **Qdrant:** dense vectors (Retrieval Service); `project_id` metadata filter.
- **BM25:** Retrieval Service filesystem/object store; rebuild on `ingest.completed`.

## Cross-cutting concerns

- **Correlation ID:** `X-Correlation-ID` header propagated by Gateway through all services (Phase 0). OpenTelemetry SDK deferred.
- **Standalone chats:** `project_id IS NULL` in Chat Service; UI omits field.
- **Observability:** Pipeline runs stored as span trees (Phase 6 revamp), linked to correlation/trace ID.

## Migration strategy

Extract-in-place: move `src/` modules into `services/`, delete from monolith, gateway routes only to microservices. Phase order: Auth → Chat+Project → LLM → Retrieval → Ingestion → Orchestrator+Realtime+Observability → Tools → UI/Docs. Monolith deleted end of Phase 6.

## Consequences

- **Positive:** Clear ownership, independent scaling, K8s-ready infra from Phase 0.
- **Negative:** Network latency between services; operational complexity vs monolith. Mitigated by co-locating hot-path services in same namespace initially.
