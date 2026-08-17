from fastapi import FastAPI

from futbot_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    register_exception_handlers,
    setup_metrics,
)
from futbot_common.models import HealthResponse
from services.llm_gateway.routes import router


def create_app() -> FastAPI:
    configure_logging("llm-gateway")
    app = FastAPI(title="FutBot LLM Gateway")
    configure_tracing(app, "llm-gateway")
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "llm-gateway")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="llm-gateway")

    app.include_router(router)
    return app


app = create_app()
