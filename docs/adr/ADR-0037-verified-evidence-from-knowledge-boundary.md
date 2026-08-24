# ADR-0037: Verified Evidence From Knowledge Boundary

## Status

Accepted.

## Context

Sprint 04 reserved `agora_verified_snapshot` but rejected it from client
Evidence payloads. Sprint 07 needs a safe way to emit that provenance level
without letting arbitrary clients self-certify truth.

## Decision

Only Knowledge snapshots created by allowlisted adapters may be materialized as
Evidence with `provenance_level = agora_verified_snapshot`. The client passes a
snapshot id, not raw verified metadata. AGORA copies the snapshot content hash,
observed timestamp and locator into Evidence and may attach it to a Claim.

This is source-provenance verification, not truth verification.

## Consequences

- Client-created Evidence remains unable to self-assert
  `agora_verified_snapshot`.
- Claims can cite trusted adapter snapshots without mutating historical
  Evidence semantics.
- Knowledge Fabric can later upgrade adapter implementations without breaking
  existing Evidence records.
