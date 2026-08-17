from fastapi import FastAPI

from futbot_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    register_exception_handlers,
    setup_metrics,
)
from futbot_common.models import HealthResponse
from services.ingestion.routes import router


def create_app() -> FastAPI:
    configure_logging("ingestion")
    app = FastAPI(title="FutBot Ingestion Service")
    configure_tracing(app, "ingestion")
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "ingestion")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="ingestion")

    app.include_router(router)
    return app


app = create_app()
