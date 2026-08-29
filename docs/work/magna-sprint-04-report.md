# AGORA MAGNA Sprint 04 Report

Status: PARTIAL_AWAITING_RATIFICATION

## Summary

Implemented the local-devnet TOKOIN testnet control plane and preserved all
forbidden boundaries. No public testnet deployment, mainnet transaction, real
value movement, live wallet mutation, legacy balance migration or agent change
was performed.

## Evidence

- Contract source: `contracts/tokoin/contracts/TokoinFixedSupply.sol`
- OpenZeppelin pin: `@openzeppelin/contracts@5.6.1`
- Solidity pin: `solc@0.8.30`
- API prefix: `/v1/tokoin-testnet`
- Database migration: `0025_magna_tokoin_testnet`
- Focused tests: `11 passed`
- Sprint 03 + Sprint 04 focused regression: `24 passed`
- Full isolated regression: `404 passed, 1 skipped`
- Ruff: `All checks passed!`
- Mypy: `Success: no issues found in 140 source files`
- Web world tests: `16 pass, 0 fail`
- Next build: compiled successfully
- Python dependency audit: no known vulnerabilities
- NPM high-severity audit: found 0 vulnerabilities
- Static contract audit: `{"ok":true,"contract":"TokoinFixedSupply","openzeppelin":"5.6.1","solc":"0.8.30"}`
- Live local API smoke on 8700 and 8710: `PARTIAL_AWAITING_RATIFICATION`,
  `LOCAL_DEVNET`, `chain_id=31337`, `mainnet_transactions=0`,
  `real_value_moved=false`.
- Live read-only status verification after fix: `tokoin_events_before=3459`,
  `tokoin_events_after=3459`.
- Local frontend smoke: `http://127.0.0.1:3000/world` returned HTML.

## Implemented

- Fixed supply manifest: 1,000,000 TOKOIN = `100000000000000` ACEROS.
- Contract source with decimals 8 and constructor-only genesis mint.
- Deployment guard for chain IDs: local devnet allowed, mainnet/unknown blocked,
  Base Sepolia blocked until ratification.
- Wallet binding projection with receive-only default and zero authoritative
  balance cache.
- Idempotent one-TOKOIN reservation saga records.
- Settlement plan creation only after a reserved challenge and accepted
  Sprint 03 `RESOLVED_VERIFIED` ResolutionReceipt.
- Role caps: proposer 1%, contributors 59%, independent replication 25%, review
  and adjudication 10%, data/tools/infrastructure 5%.
- Unused shares return instead of silent redistribution.
- Knowledge root anchor projection for Sprint 03 Merkle batches.
- Dashboard card showing local-devnet status and ratification blocker.

## Human Gates

Missing:

- Eight founder/operator ratification receipts.
- Independent external audit report.
- Public Base Sepolia deployment authorization.
- Frozen public-testnet deployment manifest and source/bytecode verification.

Sprint 05 must not start from this state.

## Final Gate

The code is ready for local review, but the sprint is intentionally not
complete. The roadmap's own gate requires human ratification and an external
independent audit before Base Sepolia deployment or Sprint 05.

## Bugs Found

- `GET /v1/tokoin-testnet/status` initially created a local manifest and event.
  Fixed by making status read-only and preserving explicit manifest creation
  under `POST /v1/tokoin-testnet/deployment/local-devnet`.
