# TOKOIN Readiness Hardening - 2026-09-06

## Goal

Improve the low blockchain-discovery scores using verifiable engineering work,
without deploying, publishing, creating keys, moving funds or representing the
internal AGORA ledger as decentralized consensus.

## Implemented

1. Human Owner session and CSRF are required for local institutional TOKOIN API
   mutations. The backing services fail closed in production.
2. Reward Merkle leaves are domain-separated by chain and contract address.
3. A deterministic external-audit bundle binds source, build inputs, ABI and
   bytecode under one hash.
4. CI compiles, tests, statically checks, audits and verifies the contract
   candidate independently from the Python/web jobs.
5. A deterministic settlement tool generates OpenZeppelin-compatible proofs,
   rejects duplicate claims, unsupported chains and rewards over one TOKOIN.
6. A read-only postdeployment verifier checks a future Base Sepolia receipt,
   deployed code, transactions, fixed supply and immutable authorities.
7. The API and human explorer show whether the EVM candidate, external audit,
   authorization and deployment actually exist.

## Boundaries that remain

- No independent external audit has been supplied.
- No 2-of-3 Safe addresses or key-recovery ceremony exist.
- No Base Sepolia contract is deployed.
- No license/public remote is ratified; RAT-05 explicitly selected no automatic
  global license.
- No public testnet operations, backup/restore drill, legal classification,
  mainnet authorization, distribution or liquidity exist.
- Decentralization cannot be raised by adding local files; it requires
  independent operators and a live public consensus network.

## Validation

- Python: 467 passed, 1 skipped.
- Focused TOKOIN and security integration: 31 passed.
- Ruff and mypy: passed; mypy checked 120 source files.
- Web: 33 tests, strict TypeScript, ESLint and production build passed.
- Contracts: compile passed; 13 contract invariants passed.
- Release preflight: 6 tests passed and the live candidate remained fail-closed.
- Candidate, settlement and deployment-verifier tools: 8 tests passed.
- npm audits for web/contracts and pip-audit: zero known vulnerabilities.
- Browser verification: the internal explorer remains usable when the public
  readiness endpoint is not yet present on an older API process.

## Readiness assessment

These scores are engineering judgments, not an external certification. They
measure the repository as it exists after this hardening pass.

| Dimension | Before | After | Reason |
| --- | ---: | ---: | --- |
| Technical completeness | 52 | 68 | Reproducible bundle, deterministic settlement tooling, read-only deployment verifier and CI coverage now exist. |
| Mainnet readiness | 12 | 22 | The release path is defined and fail-closed, but no public testnet deployment or operational history exists. |
| Security readiness | 42 | 67 | Owner/CSRF protection, production fail-closed controls, domain-separated claims and stronger authorization binding are tested. |
| Decentralization | 3 | 3 | There are still no independent validators/operators or live decentralized network. |
| User readiness | 35 | 48 | The explorer reports the two ledgers honestly and tolerates staged API rollout, but no public wallet flow exists. |
| Market readiness | 2 | 2 | No legal classification, distribution authorization, liquidity or market infrastructure exists. |

The local candidate is materially stronger, but the release verdict remains
**NO-GO** for Base Sepolia, mainnet and market activity until the external and
human gates listed above are completed.
