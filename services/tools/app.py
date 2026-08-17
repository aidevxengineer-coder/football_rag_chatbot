from fastapi import FastAPI

from futbot_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    register_exception_handlers,
    setup_metrics,
)
from futbot_common.models import HealthResponse
from services.tools.builtins.web_search import register_web_search
from services.tools.mcp.register import register_football_mcp_tools, register_pdf_tool
from services.tools.routes import router


def create_app() -> FastAPI:
    configure_logging("tools")
    app = FastAPI(title="FutBot Tools Service")
    configure_tracing(app, "tools")
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "tools")
    register_exception_handlers(app)

    @app.on_event("startup")
    def _startup() -> None:
        register_web_search()
        register_pdf_tool()
        register_football_mcp_tools()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="tools")

    app.include_router(router)
    return app


app = create_app()
