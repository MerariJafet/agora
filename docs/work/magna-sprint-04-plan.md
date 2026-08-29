# AGORA MAGNA Sprint 04 Plan

Status: LOCAL IMPLEMENTATION ONLY

Sprint 04 introduces the TOKOIN testnet control plane. The roadmap requires
eight human ratifications and an independent external audit before public
testnet deployment or Sprint 05 continuation. Those receipts are not present in
the repository, so the maximum authorized mode is `LOCAL_DEVNET`.

Implementation scope:

- Preserve the existing PostgreSQL TOKOIN ledger as legacy/internal state.
- Add an audit-ready local-devnet projection for EVM TOKOIN manifests, wallet
  bindings, reservations, settlement plans, claimable allocations and knowledge
  root anchors.
- Add a minimal non-upgradeable ERC-20 contract source using OpenZeppelin
  Contracts `5.6.1` and Solidity `0.8.30`.
- Block mainnet, unknown chains and unratified Base Sepolia.
- Keep all amounts as decimal atomic strings in ACEROS.
- Require Sprint 03 `ResolutionReceipt` before settlement allocation.
- Record split caps `1/59/25/10/5`; unused shares return rather than being
  redistributed silently.
- Expose a truthful dashboard status: `PARTIAL_AWAITING_RATIFICATION`.

Non-goals:

- No mainnet transaction.
- No Base Sepolia deployment without ratification.
- No private key generation.
- No wallet custody.
- No conversion of `RESEARCH_CREDITS_TEST`.
- No migration or correction of legacy balances.
- No external independent audit self-certification.
- No Sprint 05 start from a partial Sprint 04.
