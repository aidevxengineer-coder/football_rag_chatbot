import os
from typing import Callable

import redis.asyncio as aioredis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from futbot_common.jwt_tokens import decode_token as jwt_decode
from futbot_common.responses import ErrorBody, ErrorResponse
from services.gateway.config import settings

_redis: aioredis.Redis | None = None


async def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


class AnonMessageLimitMiddleware(BaseHTTPMiddleware):
    """Applies when /chats message routes are live (Phase 2+). Ready in Phase 1."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "POST" and request.url.path.endswith("/messages"):
            if not request.url.path.startswith("/chats/"):
                return await call_next(request)
            auth = request.headers.get("authorization", "")
            if auth.startswith("Bearer "):
                return await call_next(request)
            parts = request.url.path.strip("/").split("/")
            chat_id = parts[1] if len(parts) >= 3 and parts[0] == "chats" else None
            if chat_id:
                redis = await _get_redis()
                key = f"anon:msgs:{chat_id}"
                count = await redis.incr(key)
                if count == 1:
                    await redis.expire(key, 86400)
                if count > settings.anon_message_limit:
                    return JSONResponse(
                        status_code=403,
                        content=ErrorResponse(
                            error=ErrorBody(
                                code="LOGIN_REQUIRED",
                                message="Anonymous message limit reached. Please log in.",
                            )
                        ).model_dump(),
                    )
        return await call_next(request)


def optional_user_id_from_jwt(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = jwt_decode(token, settings.jwt_secret, "access")
        return payload["sub"]
    except Exception:
        return None


def _requires_login(path: str, method: str) -> bool:
    if path.startswith("/projects"):
        return True
    if path.startswith("/knowledge"):
        return True
    if path.startswith("/settings"):
        return True
    if method == "GET" and path.rstrip("/") == "/chats":
        return True
    if method == "POST" and path.rstrip("/") == "/chats/merge":
        return True
    if method == "DELETE" and path.startswith("/chats/"):
        return True
    if method == "GET" and path.startswith("/chats/") and path.endswith("/export"):
        return True
    return False


class LoginRequiredMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if _requires_login(path, request.method):
            if not optional_user_id_from_jwt(request):
                return JSONResponse(
                    status_code=403,
                    content=ErrorResponse(
                        error=ErrorBody(
                            code="LOGIN_REQUIRED",
                            message="Authentication required.",
                        )
                    ).model_dump(),
                )
        return await call_next(request)
