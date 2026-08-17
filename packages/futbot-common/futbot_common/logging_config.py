"""Shared structured (JSON) logging setup for all FutBot services.

Every service calls ``configure_logging(service_name)`` once at startup
(inside its ``create_app()``). This gives every log line, from every
service, the same JSON shape and automatically stamps it with the
request's correlation ID (see futbot_common.context) whenever one is
active, so logs can be grepped/joined across services by that ID.

No third-party dependency is introduced on purpose -- this uses only
the stdlib `logging` module plus `json`.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

from futbot_common.context import get_correlation_id

_CONFIGURED_SERVICES: set[str] = set()

# Attributes already present on every LogRecord -- anything else passed
# via `extra={...}` is application-specific and gets folded into the
# JSON output automatically.
_RESERVED_RECORD_ATTRS = frozenset(logging.makeLogRecord({}).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self._service_name,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": get_correlation_id(),
        }

        # Include any extra fields the caller passed via `extra=...`
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(service_name: str, *, level: str | None = None) -> None:
    """Configure root logging once per process with JSON output.

    Idempotent per service name -- safe to call from create_app() even
    if it runs more than once (e.g. tests instantiating the app twice).
    """
    if service_name in _CONFIGURED_SERVICES:
        return

    resolved_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_name))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(resolved_level)

    _CONFIGURED_SERVICES.add(service_name)
