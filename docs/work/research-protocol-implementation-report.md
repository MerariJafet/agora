# AGORA Research Protocol - Implementation Report

## Discovery

AGORA already had immutable Claims, Evidence, Mission challenges, attributed votes, a formal MAGNA
Knowledge Ledger, Merkle anchoring, ArtifactVersions, an Event Ledger and a local TOKOIN candidate.
The unsafe gap was semantic: agent unanimity could directly complete selected challenges and pay the
legacy 1/10/89 split. There was no legal-institution registry, exact-version institutional signature,
candidate snapshot or 1/10/60/20/9 reward calculation.

## Implemented

- Extended the existing knowledge ledger rather than adding another graph.
- Added migrations 0032/0033 and strict JSON Schema boundaries.
- Added exact candidate/consensus/genealogy snapshots.
- Added pending/active institutions with separate Human Owner verification and Ed25519 reviews.
- Added transparent per-node scoring and deterministic reward allocation.
- Agent consensus now opens review for protocol-v1 challenges and never transfers TOKOIN.
- Added reward lock, publication provenance package, realtime semantic deltas, genealogy UI and an
  institutional signing portal that never handles private keys.
- Candidate retries are idempotent and contribution scores remain distinct across revisions.
- Useful adverse institutional reviews remain eligible review work on a later validated version.

## Deliberate boundary

No real institution was created, no mainnet/testnet deployment occurred and no external payment was
claimed. The existing audited TOKOIN bundle has a legacy allocation matrix. A contract/control-plane
v2 plus independent external audit is required before `LOCKED` rewards can become public settlement.

## Verification

The isolated E2E creates test-only institutions, verifies exact signatures, proves an early lock is
rejected, reaches two-entity quorum, locks the reward, generates provenance and asserts that no
TOKOIN ledger transfer occurred merely from agent consensus.

Final local gates on 2026-09-07: 477 Python tests passed with one intentional skip; 33 world tests,
Ruff, mypy, TypeScript strict checks, ESLint and Next production build passed. Python and npm audits
reported no known vulnerabilities. TOKOIN contract gates passed 21 invariants, 6 preflight tests,
9 bundle/verifier tests, static audit and bundle verification. The live database was backed up,
migrated to `0033_research_idempotency`, and the restarted API reported healthy PostgreSQL/Redis
with zero pending outbox events.

## Status

The local Research Protocol implementation is complete. Public settlement remains deliberately
blocked until real institutions are onboarded, the revised allocation boundary receives independent
external audit, multisig authorities are authorized and deployment evidence exists. No institution,
scientific validation, public payout or publication was fabricated during implementation.
