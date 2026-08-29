# ADR-0058: MAGNA TOKOIN Local-Devnet Gate

Status: Accepted

## Context

MAGNA Sprint 04 asks for TOKOIN as a fixed-supply ERC-20 testnet asset while
also requiring eight human ratifications and an independent external audit
before public testnet deployment. The repository contains no signed
ratification receipts or external audit report.

## Decision

AGORA implements Sprint 04 as a local-devnet, audit-ready control plane only.
The API exposes `PARTIAL_AWAITING_RATIFICATION`, blocks mainnet and unknown
chains, and blocks Base Sepolia unless a future human release gate supplies the
required ratification and audit evidence.

The existing PostgreSQL TOKOIN ledger remains legacy/internal state. The new
testnet plane is additive and does not convert balances, backfill rewards or
create wallets for live agents.

## Consequences

- TOKOIN supply invariants and settlement logic can be tested locally.
- No private keys, real value, mainnet transaction, DEX, bridge or listing are
  introduced.
- Sprint 05 remains gated until Sprint 04 is completed by human ratification,
  external audit and a frozen public-testnet manifest.
