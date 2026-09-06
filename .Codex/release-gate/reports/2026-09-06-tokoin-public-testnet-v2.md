# TOKOIN Public Testnet V2 Release Gate

Evaluated: 2026-09-06T22:57:44Z

Verdict: **NO-GO for Base Sepolia deployment; NO-GO for mainnet/market.**

The local contract candidate and regression suite are healthy. No blockchain
transaction, wallet connection, subscription, sale, listing or liquidity action
was performed.

## Candidate reviewed

- `TokoinFixedSupply`: fixed 1,000,000 TOKOIN / 8 decimals, one constructor mint.
- `TokoinResearchRewards`: prefunded immutable challenge settlements, knowledge
  root, Merkle claims, replay protection and reservation accounting.
- `AgoraAgentIdentity`: optional locked ERC-721/ERC-5192 identity mirror.
- Base Sepolia deployment script with chain guard, two confirmations and
  exclusive receipt creation.
- Fail-closed preflight binding accepted audit hash and exact 2-of-3 control
  addresses to a separate human authorization.

Pre-gate candidate fingerprint:
`46ed2bfd38e6a398a06f61eed09656527ed183a50a4c1fa468ae1248b55154b4`

Baseline revision: `c0eb30e5fb219f4f85d58a893e069b7d762f0a8c`.

## Evidence

| Gate | Result |
| --- | --- |
| Contract compile, Solidity 0.8.30 / Cancun | PASS |
| Contract behavior simulation | PASS, 11 named invariants |
| Release-preflight unit tests | PASS, 4/4 |
| Static contract policy scan | PASS, 3 contracts |
| Focused Python TOKOIN/security integration | PASS, 26/26 |
| Historical Python regression | PASS, 455 passed / 1 skipped |
| World TypeScript tests | PASS, 33/33 |
| Ruff | PASS |
| mypy | PASS, 120 source files |
| TypeScript strict check | PASS |
| ESLint | PASS |
| Next production build | PASS |
| npm audit, contracts and web | PASS, zero known vulnerabilities |
| pip-audit from pinned requirements | PASS, zero known vulnerabilities |
| Intended-change secret scan | PASS, no detected credential material |
| Live Base Sepolia preflight | EXPECTED DENY |

## Blocking facts

1. Independent audit reference remains `MISSING_REQUIRED_GATE`; it is neither
   complete nor operator-accepted and has no report hash.
2. The required `base-sepolia-deploy-authorization.json` intentionally does not
   exist. Only a non-authorizing example is present.
3. Treasury, settlement-authority and identity-issuer 2-of-3 Safe addresses have
   not been supplied or bound to the audit.
4. No dedicated testnet deployer has been funded and no gas budget approved.
5. Mainnet, sale, custody, performance promises and market activity are outside
   the founder ratification and require new legal and human authorization.
6. The repository still lacks a ratified root open-source license and public
   remote; public source distribution is therefore not authorized by implication.

## Required next gate

Engage an independent Solidity audit for the exact frozen candidate. After zero
critical/high findings, establish the three 2-of-3 controls and create a signed,
hash-bound Base Sepolia-only authorization. Then rerun this gate. Market/mainnet
requires a later, separate release process.
