# ADR-0009: Owner authority deferred to Sprint 02 (no fake ownership)

Status: Accepted · Date: 2026-08-22 · Context: Sprint 01.1 security remediation

## Decision
Owner-level (human/organization) controls — including revoking any device of
an agent from the web shell — are NOT implemented until real Human Accounts
with real authentication exist (Sprint 02). Sprint 01.1 deliberately ships no
placeholder ownership mechanism: a fake one would create a false sense of
authorization and an insecure migration path.

Until then, revocation authority equals key/session possession:
- `POST /v1/devices/revoke-signed` — self-revocation by Ed25519 proof of
  possession (canonical kill switch; independent of session freshness).
- `POST /v1/devices/{id}/revoke` — session-authenticated, self only; acting
  on another device returns 403 `owner_authority_required`.

## Schema readiness (reviewed)
`agents` and `devices` use stable string PKs and additive columns only.
Adding `owner_id VARCHAR(30) NULL REFERENCES users(user_id)` (namespace
`usr_` already reserved in the protocol) is a single additive migration —
no destructive redesign, no data backfill required (NULL = "pre-accounts
agent", claimable at account-link time).

## Sprint 02 commitments
1. Human Accounts (usr_) with a real auth provider behind the existing
   `AuthProvider` boundary.
2. `owner_id` additive migration on agents (and optionally devices).
3. Owner-authenticated web revocation replacing the current CLI-only path.
