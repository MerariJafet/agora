"""Generic OIDC provider tests (S3-G02/T22).

Uses a deterministic in-process mock issuer injected through the provider's
HTTP fetcher boundary: no internet, no credential, no vendor.
"""

import secrets
import time
from typing import Any

import pytest
from agora_api.config import Settings
from agora_api.db import session_factory
from agora_api.oidc import OIDCConfig, OIDCError, OIDCOwnerAuthProvider
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

pytestmark = pytest.mark.integration

ISSUER = "https://issuer.test"
CLIENT_ID = "agora-local"


class MockIssuer:
    """Minimal but standards-shaped OIDC issuer."""

    def __init__(self, issuer: str = ISSUER):
        self.issuer = issuer
        self.key = RSAKey.generate_key(2048, parameters={"kid": "mock-1"})
        self.claims_override: dict[str, Any] = {}
        self.last_nonce: str | None = None

    async def get_json(self, url: str) -> dict[str, Any]:
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": self.issuer,
                "authorization_endpoint": f"{self.issuer}/authorize",
                "token_endpoint": f"{self.issuer}/token",
                "jwks_uri": f"{self.issuer}/jwks",
            }
        if url.endswith("/jwks"):
            return KeySet([self.key]).as_dict()
        raise AssertionError(f"unexpected GET {url}")

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        claims = {
            "iss": self.issuer,
            "aud": CLIENT_ID,
            "sub": "user-123",
            "nonce": self.last_nonce,
            "exp": int(time.time()) + 300,
            "iat": int(time.time()),
            **self.claims_override,
        }
        token = jwt.encode({"alg": "RS256", "kid": "mock-1"}, claims, self.key)
        return {"id_token": token, "access_token": "at", "token_type": "Bearer"}


def _provider(issuer: MockIssuer) -> OIDCOwnerAuthProvider:
    return OIDCOwnerAuthProvider(
        OIDCConfig(issuer=issuer.issuer, client_id=CLIENT_ID,
                   client_secret="s3cr3t", redirect_uri="http://localhost:3000/cb"),
        fetcher=issuer,  # type: ignore[arg-type]
    )


async def _begin(provider: OIDCOwnerAuthProvider, issuer: MockIssuer) -> str:
    started = await provider.begin_login()
    state = started["state"]
    from agora_api.ratelimit import get_redis

    nonce = await get_redis().get(f"oidc:state:{state}")
    issuer.last_nonce = nonce.decode() if isinstance(nonce, bytes) else nonce
    assert issuer.issuer in started["authorization_url"]
    return state


async def test_happy_path_provisions_user():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    async with session_factory()() as session:
        user = await provider.login(session, {"code": "abc", "state": state})
        await session.commit()
    assert user.username.startswith(ISSUER)


async def test_state_replay_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    async with session_factory()() as session:
        await provider.login(session, {"code": "abc", "state": state})
        await session.commit()
    async with session_factory()() as session:
        with pytest.raises(OIDCError):
            await provider.login(session, {"code": "abc", "state": state})


async def test_unknown_state_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    async with session_factory()() as session:
        with pytest.raises(OIDCError):
            await provider.login(session, {"code": "x", "state": secrets.token_urlsafe(8)})


async def test_nonce_mismatch_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    issuer.claims_override = {"nonce": "attacker-chosen-nonce"}
    async with session_factory()() as session:
        with pytest.raises(OIDCError, match="nonce"):
            await provider.login(session, {"code": "abc", "state": state})


async def test_issuer_mismatch_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    issuer.claims_override = {"iss": "https://evil.test"}
    async with session_factory()() as session:
        with pytest.raises(OIDCError, match="issuer"):
            await provider.login(session, {"code": "abc", "state": state})


async def test_audience_mismatch_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    issuer.claims_override = {"aud": "some-other-client"}
    async with session_factory()() as session:
        with pytest.raises(OIDCError, match="audience"):
            await provider.login(session, {"code": "abc", "state": state})


async def test_expired_id_token_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    issuer.claims_override = {"exp": int(time.time()) - 10}
    async with session_factory()() as session:
        with pytest.raises(OIDCError):
            await provider.login(session, {"code": "abc", "state": state})


async def test_foreign_signing_key_rejected():
    issuer = MockIssuer()
    provider = _provider(issuer)
    state = await _begin(provider, issuer)
    issuer.key = RSAKey.generate_key(2048, parameters={"kid": "mock-1"})  # rotate AFTER discovery
    provider._discovery = None  # force refetch of discovery, JWKS now differs
    original_get = issuer.get_json

    stale_jwks = KeySet([RSAKey.generate_key(2048, parameters={"kid": "mock-1"})]).as_dict()

    async def get_json(url: str):
        if url.endswith("/jwks"):
            return stale_jwks
        return await original_get(url)

    issuer.get_json = get_json  # type: ignore[assignment]
    async with session_factory()() as session:
        with pytest.raises(OIDCError):
            await provider.login(session, {"code": "abc", "state": state})


async def test_production_without_oidc_fails_closed(monkeypatch):
    """SEC-011: production + no provider configured => no login path at all."""
    from agora_api import oidc, owners
    from agora_api.oidc import OIDCNotConfigured

    monkeypatch.setattr(oidc, "get_settings", lambda: Settings(env="production"))
    with pytest.raises(OIDCNotConfigured):
        owners.get_production_auth_provider()
    monkeypatch.setattr(owners, "get_settings", lambda: Settings(env="production"))
    with pytest.raises(owners.DevAuthDisabled):
        owners.get_owner_auth_provider()
