# ADR-0019: Generic OIDC Production Authentication

Status: Accepted · Date: 2026-08-22 · Completes the Sprint 02 deferral

## Decision
Production owner authentication uses a **generic OIDC adapter**
(`apps/api/agora_api/oidc.py`) behind the Sprint 02 `OwnerAuthProvider`
boundary. Configuration is four settings — issuer, client_id, client_secret,
redirect_uri — and everything else comes from standard discovery at
`{issuer}/.well-known/openid-configuration`. No vendor name appears anywhere
in the domain: Keycloak, Auth0, Google, Microsoft or a self-hosted issuer are
all configuration, not code.

Validated on every login:
- **state**: single-use (Redis `GETDEL`), 10-minute TTL — replay impossible.
- **nonce**: single-use, bound to the state, must equal the ID token claim.
- **ID token**: signature verified against the issuer's JWKS (RS256/ES256/PS256
  only), `iss` exact match, `aud` contains our client_id, `exp` in the future,
  `sub` present.

Local identity is `{issuer}#{sub}` — stable across email changes and
namespaced per issuer, so two issuers can never collide on one account.

## Fail-closed guarantee (SEC-011 preserved)
- `get_owner_auth_provider()` (dev, username-only) raises in production.
- `get_production_auth_provider()` raises `auth_provider_unavailable` when no
  OIDC configuration exists.
- Result: a production deployment with neither configured has **no login path
  at all**, rather than a weak one.

## Testability without credentials
The provider takes an injectable HTTP fetcher. Tests run a deterministic
in-process mock issuer (`tests/security/test_oidc.py`) that serves discovery,
JWKS and token responses, so the whole flow — including replay, nonce, issuer,
audience, expiry and foreign-key rejection — is covered with no internet
access, no account and no secret. Local development still needs no external
configuration whatsoever.
