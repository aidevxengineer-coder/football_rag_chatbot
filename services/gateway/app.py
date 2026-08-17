import asyncio
import json
import logging
import os
from typing import Callable
from urllib.parse import urlparse

import httpx
import websockets
from fastapi import FastAPI, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from futbot_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    is_dev_mode,
    register_exception_handlers,
    setup_metrics,
)
from futbot_common.context import CORRELATION_ID_HEADER
from futbot_common.models import HealthResponse
from futbot_common.responses import ErrorBody, ErrorResponse
from services.gateway.config import settings
from services.gateway.middleware import (
    AnonMessageLimitMiddleware,
    LoginRequiredMiddleware,
    optional_user_id_from_jwt,
)
from services.gateway.routing import (
    ACTIVE_PREFIXES,
    NOT_IMPLEMENTED_PREFIXES,
    SERVICE_ROUTES,
)
from services.gateway.settings_routes import router as settings_router

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=300.0)
    return _client


def _match_prefix(path: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return None


async def _proxy(request: Request, upstream_base: str) -> Response:
    client = _get_client()
    url = upstream_base.rstrip("/") + request.url.path
    if request.url.query:
        url += f"?{request.url.query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    correlation_id = request.headers.get(CORRELATION_ID_HEADER)
    if correlation_id:
        headers[CORRELATION_ID_HEADER] = correlation_id
    user_id = optional_user_id_from_jwt(request)
    if user_id:
        headers["X-User-ID"] = user_id

    body = await request.body()
    try:
        upstream = await client.request(
            request.method,
            url,
            headers=headers,
            content=body,
        )
    except httpx.HTTPError as exc:
        logger.exception("Upstream request failed: %s %s", request.method, url)
        message = str(exc) if is_dev_mode() else "Upstream service unavailable."
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                error=ErrorBody(code="UPSTREAM_UNAVAILABLE", message=message)
            ).model_dump(),
        )

    content = upstream.content
    if upstream.status_code >= 500 and is_dev_mode():
        try:
            payload = upstream.json()
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict) and "error" not in payload:
            detail = payload.get("detail")
            if detail:
                content = ErrorResponse(
                    error=ErrorBody(
                        code="UPSTREAM_ERROR",
                        message=str(detail),
                        details=[{"upstream_status": upstream.status_code, "upstream_url": url}],
                    )
                ).model_dump(mode="json")
                content = json.dumps(content).encode("utf-8")

    response_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
    }
    if correlation_id:
        response_headers[CORRELATION_ID_HEADER] = correlation_id

    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=response_headers,
        background=BackgroundTask(upstream.aclose),
    )


def create_app() -> FastAPI:
    configure_logging("gateway")
    app = FastAPI(title="FutBot Gateway")
    configure_tracing(app, "gateway")
    app.add_middleware(AnonMessageLimitMiddleware)
    app.add_middleware(LoginRequiredMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    setup_metrics(app, "gateway")
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", service="gateway")

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "service": "gateway",
            "status": "ok",
            "docs": "/docs",
            "ui": "Pitchside web service (:3000)",
        }

    @app.websocket("/ws/pipeline")
    async def ws_pipeline_proxy(
        websocket: WebSocket, session_id: str = Query(...)
    ) -> None:
        await websocket.accept()
        parsed = urlparse(settings.orchestrator_service_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.netloc or parsed.path
        upstream_url = f"{scheme}://{host}/ws/pipeline?session_id={session_id}"
        try:
            async with websockets.connect(upstream_url) as upstream:
                async def relay_upstream() -> None:
                    async for message in upstream:
                        await websocket.send_text(message)

                async def relay_client() -> None:
                    try:
                        while True:
                            await websocket.receive_text()
                    except WebSocketDisconnect:
                        pass

                await asyncio.gather(relay_upstream(), relay_client())
        except WebSocketDisconnect:
            pass
        except Exception:
            await websocket.close()

    app.include_router(settings_router)

    @app.api_route(
        "/{full_path:path}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def route_all(request: Request, full_path: str = "") -> Response:
        path = "/" + full_path

        not_impl = _match_prefix(path, NOT_IMPLEMENTED_PREFIXES)
        if not_impl:
            return JSONResponse(
                status_code=501,
                content=ErrorResponse(
                    error=ErrorBody(
                        code="NOT_IMPLEMENTED",
                        message=f"Route {not_impl} is not available yet.",
                    )
                ).model_dump(),
            )

        active = _match_prefix(path, ACTIVE_PREFIXES)
        if active:
            return await _proxy(request, SERVICE_ROUTES[active])

        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error=ErrorBody(code="NOT_FOUND", message="Route not found")
            ).model_dump(),
        )

    return app


app = create_app()
