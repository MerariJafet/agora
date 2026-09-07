# TOKOIN Readiness Hardening Release Gate

Evaluated: 2026-09-07T00:50:48Z

Verdict: **PASS for the local hardened candidate; NO-GO for Base Sepolia,
mainnet and market activity.**

No transaction, deployment, wallet connection, key generation, fund movement,
publication, sale, listing or liquidity action was performed.

## Candidate

- Baseline revision: `1bbf4ac065c279ce8957b8585ebccbd57207a870`.
- Scoped pre-bookkeeping candidate fingerprint (excluding release-gate files
  and the two unrelated Bridge changes):
  `e2df4ba9efacbe2bce0ff2e5f4fc081b8b2f002144e3cb5bc0694f4938be8ec2`.
- Reproducible contract bundle:
  `f283883379dffaa6cbe8b6498957b40a54f6283735e3c8f0b90395c836d165a5`.
- Solidity claims bind chain ID and contract address to prevent cross-domain
  Merkle proof replay.
- Institutional API mutations require Human Owner session and CSRF, and local
  control-plane services fail closed in production.

## Evidence

| Gate | Result |
| --- | --- |
| Full Python suite | PASS, 467 passed / 1 skipped |
| Focused TOKOIN/security tests | PASS, 31 |
| Ruff | PASS |
| mypy | PASS, 120 source files |
| Web tests | PASS, 33/33 |
| TypeScript strict | PASS |
| ESLint | PASS |
| Next production build | PASS |
| Contract compile | PASS, Solidity 0.8.30 / Cancun |
| Contract behavior | PASS, 13 named invariants |
| Release-preflight tests | PASS, 6/6 |
| Bundle/deployment/settlement tests | PASS, 8/8 |
| Static Solidity policy scan | PASS |
| Candidate bundle verification | PASS |
| pip-audit | PASS, zero known vulnerabilities |
| npm audit, web and contracts | PASS, zero known vulnerabilities |
| Intended-change secret scan | PASS, no detected credential patterns |
| Browser compatibility check | PASS, ledger remains usable with an older API process |
| Base Sepolia preflight | EXPECTED DENY before network access |

## Readiness Scores

These are internal engineering assessments, not an audit certificate.

| Dimension | Before | After |
| --- | ---: | ---: |
| Technical completeness | 52 | 68 |
| Mainnet readiness | 12 | 22 |
| Security readiness | 42 | 67 |
| Decentralization | 3 | 3 |
| User readiness | 35 | 48 |
| Market readiness | 2 | 2 |

## Blocking Facts

1. The exact bundle has not received an independent Solidity audit accepted by
   the operator.
2. No hash-bound Base Sepolia authorization exists.
3. Treasury, settlement-authority and identity-issuer 2-of-3 Safe addresses
   have not been supplied and authorized.
4. No dedicated testnet deployer or maximum gas budget has been approved.
5. No public testnet deployment or multi-operator operational history exists.
6. The root open-source license/public remote, legal classification,
   distribution, custody, mainnet and market actions remain unratified.

## Decision

The repository now contains a stronger, reproducible and externally auditable
candidate. The system must remain local and non-market until an independent
audit and explicit human authorization satisfy the fail-closed preflight.
