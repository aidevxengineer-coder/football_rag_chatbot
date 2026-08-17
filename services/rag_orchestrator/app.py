from contextlib import asynccontextmanager

from fastapi import FastAPI

from futbot_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    register_exception_handlers,
    setup_metrics,
)
from futbot_common.models import HealthResponse
from services.observability.trace_store import init_db
from services.rag_orchestrator.routes import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    configure_logging("rag-orchestrator")
    app = FastAPI(title="FutBot RAG Orchestrator", lifespan=lifespan)
    configure_tracing(app, "rag-orchestrator")
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "rag-orchestrator")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="rag-orchestrator")

    app.include_router(router)
    return app


app = create_app()
