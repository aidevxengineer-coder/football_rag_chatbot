from fastapi import FastAPI

from futbot_common.logging_config import configure_logging
from futbot_common.metrics import setup_metrics
from futbot_common.middleware import CorrelationIdMiddleware
from futbot_common.models import HealthResponse
from futbot_common.tracing_config import configure_tracing


def create_stub_app(service_name: str) -> FastAPI:
    configure_logging(service_name)
    app = FastAPI(title=f"FutBot {service_name}")
    configure_tracing(app, service_name)
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, service_name)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service=service_name)

    return app
