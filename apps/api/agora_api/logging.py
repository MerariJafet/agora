"""Structured JSON logging (OpenTelemetry-compatible field naming).

Never logs prompts, model outputs, key material or secrets: log call sites
only pass identifiers, operation names, status and latency. A defensive
processor additionally redacts common secret-shaped keys.
"""

import logging
from collections.abc import MutableMapping

import structlog

SENSITIVE_KEYS = {
    "private_key", "secret", "password", "token", "session_token",
    "api_key", "authorization", "signature",
}


def _redact(
    _logger: object, _method: str, event_dict: MutableMapping[str, object]
) -> MutableMapping[str, object]:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
