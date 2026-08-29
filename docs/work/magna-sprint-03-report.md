# MAGNA Sprint 03 Report: Knowledge Ledger, Reproducibility and IP Lanes

## Status

COMPLETE_WITH_LIMITED_UI: backend ledger, protocol contracts, bridge/MCP tools,
Observatory summary panel, tests, static checks, build and audits pass. The
web surface is intentionally compact; a full graph explorer remains future UI
work.

## Implemented

- Canonical JSON Schema 2020-12 contracts:
  `packages/protocol/schemas/magna-knowledge-ledger.schema.json`.
- Additive migration `0024_magna_knowledge_ledger`:
  `magna_knowledge_objects`, `magna_knowledge_edges`,
  `magna_resolution_receipts`, `magna_merkle_batches`,
  `magna_publication_decisions`, `magna_access_grants`.
- Domain-separated canonical hashing for objects, edges, Merkle leaves and
  resolution receipts.
- Registered protocol creation with immutable `frozen_hash`.
- Protocol amendments as separate objects linked to the frozen original.
- ExperimentRun registration bound to a registered protocol.
- ReproducibilityCapsule deterministic fixture verification.
- Provenance DAG cycle protection for dependency-like edges.
- Bounded lineage API with depth 1/2 limits.
- OPEN/SEALED/RESTRICTED publication lane guards.
- ResolutionReceipt evaluator that can record supported/inconclusive/contested
  outcomes and rejects `REPLICATED` without independent controller evidence.
- Merkle batch simulated anchor over contiguous ledger windows.
- Bridge client and MCP tools for ledger summary, objects, protocols, edges,
  lineage and receipts.
- Observatory compact Knowledge Ledger panel.

## Safety Results

- No URL fetching, notebook execution, dataset opening or artifact execution.
- No TOKOIN settlement, wallet creation or reward movement.
- SEALED/RESTRICTED public views expose only commitments/summaries.
- OPEN objects require explicit license/right metadata.
- Secret-like and private-CoT payload markers are rejected.
- Receipts set `payment_eligible=false` in this sprint.
- Live smoke was read-only after migration/bootstrap; no live objects were
  fabricated.

## Verification

```text
Pre-edit baseline:
./scripts/run-isolated-tests.sh -q
380 passed, 1 skipped in 131.42s

Focused Sprint 03:
.venv/bin/ruff check ...
.venv/bin/mypy apps/api/agora_api/magna_knowledge_ledger.py ...
./scripts/run-isolated-tests.sh tests/integration/test_magna_knowledge_ledger.py \
  tests/security/test_magna_knowledge_ledger_security.py -q
13 passed in 1.74s

Full isolated regression:
./scripts/run-isolated-tests.sh -q
393 passed, 1 skipped in 138.73s

Static and frontend:
.venv/bin/ruff check .
All checks passed!
.venv/bin/mypy apps/api bridge
Success: no issues found in 137 source files
npm --prefix apps/web run lint
npm --prefix apps/web run typecheck
npm --prefix apps/web run test:world
16 pass / 0 fail
npm --prefix apps/web run build
Compiled successfully

Dependency audits:
.venv/bin/pip-audit -r requirements.txt
No known vulnerabilities found
npm --prefix apps/web audit --audit-level=high
found 0 vulnerabilities

Live smoke:
alembic current -> 0024_magna_knowledge_ledger (head)
GET http://127.0.0.1:8700/v1/knowledge-ledger -> 200
ledger_version magna-knowledge-ledger.v1
counts_by_type {}, counts_by_lane {}
```

## Known Limitations

- Full graph explorer UI is not yet implemented; the Observatory shows a compact
  summary only.
- SEALED storage in Sprint 03 is commitment-only at public boundary. Real
  encrypted payload access workflow remains future work before external use.
- Merkle anchors are simulated local records; Sprint 04 may bind roots to a
  testnet registry.
- Headless canvas screenshot capture remains unreliable in this environment,
  but frontend build/type/lint/world unit tests pass.

## Next Gate

Sprint MAGNA 04 may begin only from this committed state after preserving the
Sprint 03 commit hash and re-running the predecessor gate. It must implement
TOKOIN as no-value testnet only and must not backfill or settle historical
research credits.
