from contextlib import asynccontextmanager

from fastapi import FastAPI

from starlette.middleware.sessions import SessionMiddleware

from futbot_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    register_exception_handlers,
    setup_metrics,
)
from futbot_common.models import HealthResponse
from services.auth.config import settings
from services.auth.db import init_db
from services.auth.redis_store import close_redis
from services.auth.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.database_url)
    yield
    await close_redis()


@asynccontextmanager
async def _noop_lifespan(app: FastAPI):
    yield


def create_app(*, with_lifespan: bool = True) -> FastAPI:
    configure_logging("auth")
    ls = lifespan if with_lifespan else _noop_lifespan
    app = FastAPI(title="FutBot Auth Service", lifespan=ls)
    configure_tracing(app, "auth")
    app.add_middleware(SessionMiddleware, secret_key=settings.jwt_secret)
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "auth")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="auth")

    app.include_router(router)
    return app


app = create_app()
