"""Generic production OIDC AuthProvider (S3-G02, ADR-0019).

Vendor-neutral: configuration is (issuer, client_id, client_secret,
redirect_uri) plus standard discovery at
`{issuer}/.well-known/openid-configuration`. Nothing in the domain knows
about Google/Microsoft/Auth0/Keycloak — swapping providers is configuration.

Validated on every login:
- `state`: single-use, Redis-stored, bound to the browser flow (CSRF for the
  authorization redirect).
- `nonce`: single-use, must match the `nonce` claim of the ID token.
- ID token signature against the issuer's JWKS (fetched from discovery),
  plus `iss` exact match, `aud` containing our client_id, and `exp`.
Tests inject a deterministic in-process issuer through `http_client`, so no
internet access or real credential is ever required.

Production fail-closed rule stays intact (SEC-011): if `AGORA_ENV=production`
and no OIDC configuration exists, no provider is returned and login is 403.
"""

import base64
import hashlib
import json
import math
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import AgoraError
from agora_api.events import now_utc
from agora_api.ids import new_user_id
from agora_api.logging import get_logger
from agora_api.models import User
from agora_api.ratelimit import get_redis

log = get_logger("agora.api.oidc")

STATE_TTL = 600  # seconds
ALLOWED_ID_TOKEN_ALGS = ["RS256", "ES256", "PS256"]


class OIDCError(AgoraError):
    status_code = 401
    code = "oidc_rejected"


class OIDCNotConfigured(AgoraError):
    status_code = 403
    code = "auth_provider_unavailable"


class HttpFetcher(Protocol):
    async def get_json(self, url: str) -> dict[str, Any]: ...
    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]: ...


class HttpxFetcher:
    async def get_json(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, data=data)
            r.raise_for_status()
            return r.json()


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str

    @classmethod
    def from_settings(cls) -> "OIDCConfig | None":
        s = get_settings()
        if not (s.oidc_issuer and s.oidc_client_id and s.oidc_redirect_uri):
            return None
        return cls(
            issuer=s.oidc_issuer,
            client_id=s.oidc_client_id,
            client_secret=s.oidc_client_secret,
            redirect_uri=s.oidc_redirect_uri,
        )


class OIDCOwnerAuthProvider:
    """Implements the Sprint 02 OwnerAuthProvider boundary."""

    def __init__(self, config: OIDCConfig, fetcher: HttpFetcher | None = None):
        self.config = config
        self.fetcher = fetcher or HttpxFetcher()
        self._discovery: dict[str, Any] | None = None

    async def discovery(self) -> dict[str, Any]:
        if self._discovery is None:
            discovery_base = self.config.issuer.rstrip("/")
            doc = await self.fetcher.get_json(
                f"{discovery_base}/.well-known/openid-configuration"
            )
            if doc.get("issuer") != self.config.issuer:
                raise OIDCError("Discovery document issuer mismatch.")
            self._discovery = doc
        return self._discovery

    async def begin_login(self) -> dict[str, str]:
        """Returns the authorization URL plus the single-use state/nonce."""
        doc = await self.discovery()
        state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
        r = get_redis()
        await r.set(f"oidc:state:{state}", nonce, ex=STATE_TTL)
        params = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
        }
        query = str(httpx.QueryParams(params))
        return {
            "authorization_url": f"{doc['authorization_endpoint']}?{query}",
            "state": state,
        }

    async def _consume_state(self, state: str) -> str:
        """Single-use: the Redis GETDEL makes replay impossible."""
        nonce = await get_redis().getdel(f"oidc:state:{state}")
        if not nonce:
            raise OIDCError("Unknown, expired or already-used state.")
        return nonce.decode() if isinstance(nonce, bytes) else nonce

    async def _jwks(self) -> KeySet:
        doc = await self.discovery()
        raw = await self.fetcher.get_json(doc["jwks_uri"])
        return KeySet.import_key_set(cast("Any", raw))

    async def login(self, session: AsyncSession, credentials: dict) -> User:
        code, state = credentials.get("code"), credentials.get("state")
        if not isinstance(code, str) or not isinstance(state, str):
            raise OIDCError("code and state are required.")
        expected_nonce = await self._consume_state(state)

        doc = await self.discovery()
        tokens = await self.fetcher.post_form(doc["token_endpoint"], {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.config.redirect_uri,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        })
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str):
            raise OIDCError("Token endpoint returned no id_token.")

        try:
            decoded = jwt.decode(id_token, await self._jwks(),
                                 algorithms=ALLOWED_ID_TOKEN_ALGS)
        except Exception as exc:
            log.info("oidc.id_token_invalid", error=type(exc).__name__)
            raise OIDCError("ID token signature validation failed.") from exc
        claims = decoded.claims

        if claims.get("iss") != self.config.issuer:
            raise OIDCError("ID token issuer mismatch.")
        aud = claims.get("aud")
        audiences = aud if isinstance(aud, list) else [aud]
        if self.config.client_id not in audiences:
            raise OIDCError("ID token audience mismatch.")
        if (len(audiences) > 1 or "azp" in claims) and claims.get("azp") != self.config.client_id:
            raise OIDCError("ID token authorized party mismatch.")
        if claims.get("nonce") != expected_nonce:
            raise OIDCError("ID token nonce mismatch or replayed.")
        exp = claims.get("exp")
        if (
            isinstance(exp, bool) or not isinstance(exp, int | float)
            or not math.isfinite(exp) or exp <= time.time()
        ):
            raise OIDCError("ID token expired.")
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject or len(subject) > 255:
            raise OIDCError("ID token has no valid subject.")

        # Stable local identity: issuer+sub, never the display email alone.
        # Hash the complete tuple; truncation merged different long subjects.
        # Do not auto-link legacy truncated usernames: their ownership is ambiguous.
        identity = json.dumps([self.config.issuer, subject], ensure_ascii=False).encode()
        digest = base64.urlsafe_b64encode(hashlib.sha256(identity).digest()).decode().rstrip("=")
        username = f"oidc:{digest}"
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing:
            return existing
        user = User(user_id=new_user_id(), username=username, created_at=now_utc())
        session.add(user)
        log.info("oidc.user_provisioned", user_id=user.user_id)
        return user


def build_oidc_provider(fetcher: HttpFetcher | None = None) -> OIDCOwnerAuthProvider | None:
    config = OIDCConfig.from_settings()
    if config is None:
        return None
    return OIDCOwnerAuthProvider(config, fetcher)


def dumps_claims(claims: dict[str, Any]) -> str:
    return json.dumps(claims, sort_keys=True)
