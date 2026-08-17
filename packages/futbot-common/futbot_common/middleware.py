import uuid

from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from futbot_common.context import CORRELATION_ID_HEADER, correlation_id_var


def _trace_id_from_active_span() -> str | None:
    """Return the current OpenTelemetry trace ID as a 32-hex-char string.

    FastAPIInstrumentor (see futbot_common.tracing_config) starts the
    request's span before this middleware's dispatch() runs, so when
    tracing is configured the active span here is already either a new
    root span (edge/gateway request) or a child of the span propagated
    via the incoming W3C `traceparent` header (a downstream hop). Either
    way, reusing its trace ID as the correlation ID means "the ID in
    your logs" and "the trace ID in Jaeger" are always the same value.
    """
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return None
    return format(span_context.trace_id, "032x")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = (
            request.headers.get(CORRELATION_ID_HEADER)
            or _trace_id_from_active_span()
            or str(uuid.uuid4())
        )
        token = correlation_id_var.set(correlation_id)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
