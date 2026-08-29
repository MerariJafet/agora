# MAGNA Sprint 04.1 External Audit Scope

Status: READY_FOR_SCOPING_NOT_ENGAGED

The scope matrix is complete enough to approach an independent auditor without
misrepresenting off-chain components as contracts. No auditor has been hired,
paid or accepted in this repository.

In scope for audit:

- `TokoinFixedSupply` fixed-supply ERC-20 source.
- Chain guard behavior and public-testnet deployment readiness.
- Off-chain reservation, settlement and wallet-binding trust boundaries.
- Evidence that no legacy TOKOIN balances are moved into the testnet plane.
- Documentation that TOKOIN rewards do not certify truth.

Out of scope until a future sprint:

- Mainnet deployment.
- Pool escrow contract.
- Trustless on-chain reward vault/splitter.
- On-chain Agent Passport anchor.
- Knowledge Fabric verified-source providers.
