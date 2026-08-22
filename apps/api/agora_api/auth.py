"""Authentication boundary.

`AuthProvider` is the vendor-neutral interface (Auth Provider boundary,
ADR-0005/architecture). Sprint 01 ships `DeviceSessionAuthProvider`: opaque
short-lived tokens issued at registration, stored server-side as SHA-256
hashes, bound to a device and rejected the moment the device is revoked
(SEC-003).

Fail-closed rule (SEC-006): there is no development bypass token. The dev and
production code paths are identical; the only dev affordance is configuration
(e.g. rate-limit fail-open), never authentication.
"""

import hashlib
import secrets
from datetime import timedelta
from typing import Protocol

from sqlalchemy import select
from ulid import ULID
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import AuthRequired, DeviceRevoked
from agora_api.events import now_utc
from agora_api.models import Device, DeviceSession


class AuthProvider(Protocol):
    async def issue_session(self, session: AsyncSession, device_id: str) -> tuple[str, str]:
        """Returns (opaque_token, expires_at_iso)."""
        ...

    async def authenticate_device(self, session: AsyncSession, token: str) -> Device:
        """Returns the authenticated, non-revoked Device or raises."""
        ...


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class DeviceSessionAuthProvider:
    async def issue_session(self, session: AsyncSession, device_id: str) -> tuple[str, str]:
        token = f"ses_{secrets.token_urlsafe(32)}"
        expires_at = now_utc() + timedelta(seconds=get_settings().session_ttl_seconds)
        session.add(
            DeviceSession(
                session_id=f"ses_{ULID()}",  # internal namespace, not part of the public protocol
                device_id=device_id,
                token_hash=_hash_token(token),
                expires_at=expires_at,
                created_at=now_utc(),
            )
        )
        return token, expires_at.isoformat().replace("+00:00", "Z")

    async def authenticate_device(self, session: AsyncSession, token: str) -> Device:
        if not token or not token.startswith("ses_"):
            raise AuthRequired("Missing or malformed session token.")
        row = await session.execute(
            select(DeviceSession).where(DeviceSession.token_hash == _hash_token(token))
        )
        device_session = row.scalar_one_or_none()
        if device_session is None or device_session.expires_at <= now_utc():
            raise AuthRequired("Session invalid or expired.")
        device = await session.get(Device, device_session.device_id)
        if device is None:
            raise AuthRequired("Session device no longer exists.")
        if device.status == "revoked":
            raise DeviceRevoked("Device has been revoked.")
        return device


auth_provider: AuthProvider = DeviceSessionAuthProvider()
