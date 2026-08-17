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
from services.project.config import settings
from services.project.db import init_db
from services.project.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.database_url)
    yield


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    configure_logging("project")
    ls = lifespan if with_lifespan else _noop_lifespan
    app = FastAPI(title="FutBot Project Service", lifespan=ls)
    configure_tracing(app, "project")
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "project")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="project")

    app.include_router(router)
    from services.project.knowledge_routes import router as knowledge_router

    app.include_router(knowledge_router)
    return app


app = create_app()
