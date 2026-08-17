import logging
import os
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from futbot_common.errors import AuthError
from futbot_common.responses import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)


def is_dev_mode() -> bool:
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).lower()
    if env in ("production", "prod"):
        return False
    debug = os.getenv("DEBUG", "").lower()
    if debug in ("0", "false", "no"):
        return False
    if debug in ("1", "true", "yes"):
        return True
    return env in ("development", "dev", "local", "test")


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[dict] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error=ErrorBody(code=code, message=message, details=details)
        ).model_dump(),
    )


def _dev_details(exc: BaseException) -> list[dict]:
    return [
        {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc().splitlines(),
        }
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    async def auth_error_handler(_request: Request, exc: AuthError) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = str(exc.detail)
        details = None
        if is_dev_mode() and not isinstance(exc.detail, str):
            details = [{"detail": exc.detail}]
        return _error_response(
            status_code=exc.status_code,
            code="HTTP_ERROR",
            message=message,
            details=details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        message = "; ".join(
            f"{'.'.join(str(p) for p in err.get('loc', []))}: {err.get('msg', 'invalid')}"
            for err in errors
        )
        return _error_response(
            status_code=422,
            code="VALIDATION_ERROR",
            message=message or "Request validation failed.",
            details=errors if is_dev_mode() else None,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception")
        if is_dev_mode():
            return _error_response(
                status_code=500,
                code="INTERNAL_ERROR",
                message=str(exc) or type(exc).__name__,
                details=_dev_details(exc),
            )
        return _error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An internal server error occurred.",
        )
