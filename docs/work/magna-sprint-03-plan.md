# MAGNA Sprint 03 Plan: Knowledge Ledger, Reproducibility and IP Lanes

## Gate

- Starting branch: `feat/agora-magna-sprint-03-knowledge-ledger`.
- Pre-edit baseline: `./scripts/run-isolated-tests.sh -q` -> `380 passed, 1 skipped`.
- Sprint 02 live gate closed on commit `fb6d1f7`; `/v1/research-market` responds on 8700/8710 after additive migration and explicit MAGNA bootstrap.

## Scope

Build an additive MAGNA Knowledge Ledger beside the existing Knowledge Fabric. The existing adapter registry and snapshots remain intact; MAGNA Sprint 03 adds formal research objects, canonical hashing, provenance DAG, registered protocol semantics, reproducibility capsules, publication lanes and resolution receipts.

## Non-Goals

- No TOKOIN settlement, wallets or chain registry changes.
- No automatic URL/file/code execution.
- No disclosure of SEALED or RESTRICTED plaintext through public surfaces.
- No mutation of live agents for tests.

## Implementation Order

1. Add JSON Schema 2020-12 contracts for MAGNA knowledge objects and actions.
2. Add additive PostgreSQL tables for objects, DAG edges, resolution receipts, Merkle batches and access grants.
3. Implement deterministic canonical JSON hashing with domain separation.
4. Implement registered protocols, amendments, experiment runs, reproducibility capsule verification fixture, provenance DAG cycle guards and bounded lineage reads.
5. Implement lane guards for OPEN/SEALED/RESTRICTED and draft publication/access metadata.
6. Add API routes and bridge/MCP read tools where existing surfaces permit.
7. Add tests for hashing, DAG cycles, protocol immutability, independence, lanes, receipts and Merkle proofs.
8. Update docs/ADRs and run full gates.
