"""Shared OpenTelemetry distributed tracing setup for all FutBot services.

Every service calls ``configure_tracing(app, service_name)`` once, right
after the FastAPI app is created. This gives every service:

- A span for every inbound HTTP request (via FastAPIInstrumentor)
- A span for every outbound httpx/requests call, with the W3C
  ``traceparent`` header automatically injected -- this is what stitches
  spans from different services (gateway -> chat -> rag_orchestrator ->
  retrieval -> llm_gateway) into one continuous trace, without any of
  the call sites needing to pass anything by hand.
- Spans exported to an OpenTelemetry Collector (``OTEL_EXPORTER_OTLP_ENDPOINT``,
  default ``http://otel-collector:4317``), which forwards them to Jaeger.

If the collector is unreachable (e.g. running a service standalone
without the observability stack), span export simply fails silently in
the background -- it never blocks or breaks a request.

See also: futbot_common.middleware.CorrelationIdMiddleware, which reuses
the active span's trace ID as the correlation ID whenever one is
available, so "the correlation ID in your logs" and "the trace ID in
Jaeger" are the same value.
"""

import logging
import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_CONFIGURED_SERVICES: set[str] = set()
_HTTP_CLIENTS_INSTRUMENTED = False


def configure_tracing(app: FastAPI, service_name: str) -> None:
    global _HTTP_CLIENTS_INSTRUMENTED

    if service_name in _CONFIGURED_SERVICES:
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    # httpx/requests instrumentation patches the libraries globally, not
    # per-app -- only needs doing once per process, regardless of how
    # many times configure_tracing() is called (e.g. in tests).
    if not _HTTP_CLIENTS_INSTRUMENTED:
        HTTPXClientInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        _HTTP_CLIENTS_INSTRUMENTED = True

    _CONFIGURED_SERVICES.add(service_name)
