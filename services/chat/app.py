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
from services.chat.config import settings
from services.chat.db import init_db
from services.chat.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.database_url)
    yield


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    configure_logging("chat")
    ls = lifespan if with_lifespan else _noop_lifespan
    app = FastAPI(title="FutBot Chat Service", lifespan=ls)
    configure_tracing(app, "chat")
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "chat")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="chat")

    app.include_router(router)
    return app


app = create_app()
