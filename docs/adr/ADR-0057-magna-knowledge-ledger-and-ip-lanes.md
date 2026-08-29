# ADR-0057: MAGNA Knowledge Ledger and IP Lanes

## Status

Accepted for MAGNA Sprint 03.

## Context

AGORA already has a Knowledge Fabric adapter boundary for source-aware public
snapshots. MAGNA needs a separate formal ledger for research protocols,
experiment runs, reproducibility capsules, evidence, replication, dissent,
outcomes and resolution receipts. This ledger must preserve provenance and
reproducibility without turning votes, popularity or future TOKOIN settlement
into truth.

## Decision

Add a MAGNA Knowledge Ledger projection in PostgreSQL:

- `magna_knowledge_objects` stores canonical, versioned, content-addressed
  formal objects.
- `magna_knowledge_edges` stores attributed provenance/relation assertions and
  rejects DAG cycles for dependency-like relations.
- `magna_resolution_receipts` records deterministic resolver decisions and
  explicitly sets `payment_eligible=false` in Sprint 03.
- `magna_merkle_batches` creates simulated, deterministic anchor batches over
  contiguous ledger objects. On-chain roots remain Sprint 04 scope.
- `magna_publication_decisions` and `magna_access_grants` reserve explicit
  human/IP control surfaces without automatic disclosure.

Visibility lanes are per object version:

- `OPEN` requires explicit rights and a license before public payload exposure.
- `SEALED` exposes only commitment metadata; plaintext is rejected at the
  public API boundary.
- `RESTRICTED` is never downgraded by scheduler, vote or generic admin path.

## Consequences

- Knowledge Fabric snapshots remain the adapter/source cache boundary.
- Knowledge Ledger formal objects are auditable and reconstructable through the
  Event Ledger plus projections.
- AGORA can represent negative, inconclusive and contested outcomes honestly.
- TOKOIN settlement can later consume valid resolution receipts, but Sprint 03
  does not pay, reserve real currency or create wallets.
- Legal/IP templates remain draft workflow metadata, not legal advice.
