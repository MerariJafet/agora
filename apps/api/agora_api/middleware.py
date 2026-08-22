"""Request ID + trace propagation, latency logging and security headers."""

import secrets
import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from agora_api.logging import get_logger

log = get_logger("agora.api.request")

_TRACEPARENT_PREFIX = "00-"


def _extract_trace_id(request: Request) -> str:
    """W3C traceparent propagation; generate a new trace id when absent."""
    tp = request.headers.get("traceparent", "")
    if tp.startswith(_TRACEPARENT_PREFIX):
        parts = tp.split("-")
        if len(parts) >= 3 and len(parts[1]) == 32:
            return parts[1]
    return secrets.token_hex(16)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or f"req_{secrets.token_hex(8)}"
        trace_id = _extract_trace_id(request)
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        structlog.contextvars.bind_contextvars(request_id=request_id, trace_id=trace_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        # Operation metadata only — never bodies, prompts or secrets.
        log.info(
            "http.request",
            request_id=request_id,
            trace_id=trace_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["cache-control"] = "no-store"
        return response
