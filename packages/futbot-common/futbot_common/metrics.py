"""Shared Prometheus metrics setup for all FutBot services.

Every service calls ``setup_metrics(app, service_name)`` once, right
after the FastAPI app is created. This gives every service, for free:

- ``GET /metrics`` in Prometheus text format
- ``http_requests_total{method, handler, status}`` (counter)
- ``http_request_duration_seconds{method, handler}`` (histogram, for
  computing p50/p95/p99 latency per endpoint)

Domain-specific metrics (LLM calls, retrieval, ingestion jobs) live
next to the code that produces them and register themselves against
the same default Prometheus registry that this module exposes -- see
services/llm_gateway/provider.py, services/retrieval/*, and
services/ingestion/* for examples.
"""

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app: FastAPI, service_name: str) -> None:
    # Deliberately no per-service metric_subsystem: keeping metric names
    # identical across services (e.g. "futbot_http_requests_total") lets
    # Prometheus distinguish services via the scrape-config "job" label
    # instead, so cross-service queries like
    # `sum by (job) (rate(futbot_http_requests_total[5m]))` work directly.
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app, metric_namespace="futbot").expose(
        app, endpoint="/metrics", include_in_schema=False
    )
