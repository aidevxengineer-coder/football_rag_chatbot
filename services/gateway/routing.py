from services.gateway.config import settings


# Permanent route table — paths map to microservices (never the monolith).
SERVICE_ROUTES: dict[str, str] = {
    "/auth": settings.auth_service_url,
    "/chats": settings.chat_service_url,
    "/projects": settings.project_service_url,
    "/knowledge": settings.project_service_url,
    "/llm": settings.llm_service_url,
    "/retrieve": settings.retrieval_service_url,
    "/ingest": settings.ingestion_service_url,
    "/pipeline": settings.orchestrator_service_url,
    "/traces": settings.observability_service_url,
    "/tools": settings.tools_service_url,
}

ACTIVE_PREFIXES = ("/auth", "/chats", "/projects", "/knowledge", "/traces", "/tools")

NOT_IMPLEMENTED_PREFIXES = (
    "/llm",
    "/retrieve",
    "/ingest",
    "/pipeline",
    "/tools/execute",
)
