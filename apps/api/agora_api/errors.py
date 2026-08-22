"""Structured error model. Every error response is:

    {"error": {"code": "...", "message": "...", "request_id": "..."}}

Codes are stable machine-readable identifiers; messages never echo secrets
or raw payloads back.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AgoraError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str = "Internal error"):
        self.message = message
        super().__init__(message)


class ValidationFailed(AgoraError):
    status_code = 422
    code = "validation_failed"


class NotFound(AgoraError):
    status_code = 404
    code = "not_found"


class ChallengeInvalid(AgoraError):
    status_code = 401
    code = "challenge_invalid"


class SignatureInvalid(AgoraError):
    status_code = 401
    code = "signature_invalid"


class AuthRequired(AgoraError):
    status_code = 401
    code = "auth_required"


class DeviceRevoked(AgoraError):
    status_code = 403
    code = "device_revoked"


class OwnerAuthorityRequired(AgoraError):
    """A device tried to act on a different device. Owner-level controls
    (human accounts) arrive in Sprint 02 — see ADR-0009."""

    status_code = 403
    code = "owner_authority_required"


class Conflict(AgoraError):
    status_code = 409
    code = "conflict"


class RateLimited(AgoraError):
    status_code = 429
    code = "rate_limited"


def error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


async def agora_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AgoraError)
    return error_response(request, exc.status_code, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(request, 422, "validation_failed", "Request body failed validation.")
