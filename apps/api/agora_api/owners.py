"""Human Owner domain: auth provider boundary, browser sessions, CSRF and
secure agent-claim pairing (S2-T02/T03/T04).

Auth provider boundary: `OwnerAuthProvider` keeps AGORA vendor-neutral.
Sprint 02 ships only `DevOwnerAuthProvider` (username → user, no password —
local development convenience). Fail-closed rule (SEC-011): the login route
checks the environment at request time and returns 403 in production, where
only a real provider (Sprint 03+) may authenticate; there is no code path
that lets dev auth run in production.

Browser session: opaque token in an HttpOnly SameSite=Lax cookie (Secure in
production), stored server-side as SHA-256. CSRF (SEC-012): per-session token
returned in the login/me response body; every state-changing browser request
must echo it in `X-CSRF-Token` (cookie is HttpOnly so an attacker page can
neither read the CSRF token nor set the header cross-origin).
"""

import hashlib
import secrets
from datetime import timedelta
from typing import Annotated, Protocol

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.db import get_session
from agora_api.errors import AgoraError, AuthRequired
from agora_api.events import now_utc
from agora_api.ids import new_id, new_user_id
from agora_api.models import ClaimChallenge, User, WebSession

SESSION_COOKIE = "agora_session"
SESSION_TTL = timedelta(hours=24)
CLAIM_TTL = timedelta(minutes=10)
CLAIM_CONTEXT = "agora.claim.v1"


class CsrfRejected(AgoraError):
    status_code = 403
    code = "csrf_rejected"


class DevAuthDisabled(AgoraError):
    status_code = 403
    code = "auth_provider_unavailable"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class OwnerAuthProvider(Protocol):
    """Vendor-neutral owner authentication boundary."""

    async def login(self, session: AsyncSession, credentials: dict) -> User: ...


class DevOwnerAuthProvider:
    """Development-only. The route guards on environment before calling."""

    async def login(self, session: AsyncSession, credentials: dict) -> User:
        username = str(credentials.get("username", "")).strip()
        if not (1 <= len(username) <= 64) or not username.replace("-", "").isalnum():
            raise AuthRequired("Invalid username.")
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing:
            return existing
        user = User(user_id=new_user_id(), username=username, created_at=now_utc())
        session.add(user)
        return user


def get_owner_auth_provider() -> OwnerAuthProvider:
    """Dev provider only. Production never reaches it (SEC-011): the OIDC
    provider is resolved separately by the /v1/auth/oidc routes."""
    if get_settings().is_production:
        raise DevAuthDisabled(
            "Development authentication is disabled in production. "
            "Configure an OIDC provider (ADR-0019)."
        )
    return DevOwnerAuthProvider()


def get_production_auth_provider() -> OwnerAuthProvider:
    """Resolve the configured production provider or fail closed."""
    from agora_api.oidc import OIDCNotConfigured, build_oidc_provider

    provider = build_oidc_provider()
    if provider is None:
        raise OIDCNotConfigured(
            "No production AuthProvider configured (set AGORA_OIDC_* settings)."
        )
    return provider


async def create_web_session(session: AsyncSession, user: User) -> tuple[str, str, str]:
    """Returns (cookie_token, csrf_token, expires_at_iso)."""
    token = f"web_{secrets.token_urlsafe(32)}"
    csrf = secrets.token_hex(32)
    expires = now_utc() + SESSION_TTL
    session.add(
        WebSession(
            session_id=f"wss_{new_id('usr')[4:]}",  # internal ns, ULID body
            user_id=user.user_id,
            token_hash=_hash(token),
            csrf_token=csrf,
            expires_at=expires,
            created_at=now_utc(),
        )
    )
    return token, csrf, expires.isoformat().replace("+00:00", "Z")


async def resolve_web_session(session: AsyncSession, cookie_token: str | None) -> WebSession:
    if not cookie_token or not cookie_token.startswith("web_"):
        raise AuthRequired("Owner login required.")
    ws = (
        await session.execute(
            select(WebSession).where(WebSession.token_hash == _hash(cookie_token))
        )
    ).scalar_one_or_none()
    if ws is None or ws.expires_at <= now_utc():
        raise AuthRequired("Owner session invalid or expired.")
    return ws


async def current_owner(
    session: Annotated[AsyncSession, Depends(get_session)],
    agora_session: Annotated[str | None, Cookie()] = None,
) -> User:
    ws = await resolve_web_session(session, agora_session)
    user = await session.get(User, ws.user_id)
    if user is None:
        raise AuthRequired("Owner no longer exists.")
    return user


async def csrf_protected_owner(
    session: Annotated[AsyncSession, Depends(get_session)],
    agora_session: Annotated[str | None, Cookie()] = None,
    x_csrf_token: Annotated[str | None, Header()] = None,
) -> User:
    """For state-changing browser actions (SEC-012)."""
    ws = await resolve_web_session(session, agora_session)
    if not x_csrf_token or not secrets.compare_digest(x_csrf_token, ws.csrf_token):
        raise CsrfRejected("Missing or invalid CSRF token.")
    user = await session.get(User, ws.user_id)
    if user is None:
        raise AuthRequired("Owner no longer exists.")
    return user


CurrentOwner = Annotated[User, Depends(current_owner)]
MutatingOwner = Annotated[User, Depends(csrf_protected_owner)]


# -- Secure agent claim (SEC-005: agent_id alone is never enough) -----------

def claim_message(agent_id: str, code: str) -> bytes:
    return f"{CLAIM_CONTEXT}|{agent_id}|{code}".encode()


async def create_claim(session: AsyncSession, user: User, agent_id: str) -> str:
    """Issue a one-time pairing code bound to (user, agent). Stored hashed."""
    code = secrets.token_urlsafe(24)
    session.add(
        ClaimChallenge(
            claim_id=f"clm_{new_id('usr')[4:]}",
            user_id=user.user_id,
            agent_id=agent_id,
            code_hash=_hash(code),
            expires_at=now_utc() + CLAIM_TTL,
            consumed_at=None,
            created_at=now_utc(),
        )
    )
    return code
