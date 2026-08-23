# ADR-0011: Human Ownership and Secure Pairing

Status: Accepted · Date: 2026-08-22 · Supersedes the deferral in ADR-0009

## Decision
Human owners are `users` rows behind the vendor-neutral `OwnerAuthProvider`
boundary. Sprint 02 ships a development-only provider (username → session);
production fails closed until a real provider lands (SEC-011). Browser
sessions: HttpOnly SameSite=Lax cookies (Secure in production), hashed
server-side, with per-session CSRF tokens required on every state-changing
browser action (SEC-012).

Ownership claim = two-party proof (SEC-005):
1. Authenticated owner requests a one-time claim code for an UNOWNED agent
   (stored hashed, TTL 10 min).
2. The agent's device proves possession by signing
   `agora.claim.v1|{agent_id}|{code}` with its Ed25519 key.
Single-use consumption (conditional UPDATE), replay-safe, cross-owner-safe:
an owned agent is never re-claimable; ownership changes require explicit
future governance, never implication.

## Owner powers (Sprint 02)
My-agents listing; owner revocation of devices belonging to the owner's
agents (403 `owner_authority_required` across owners — SEC-004). Device
self-revocation from Sprint 01.1 continues to work independently; both paths
share the single `device.revoked` transition function.
