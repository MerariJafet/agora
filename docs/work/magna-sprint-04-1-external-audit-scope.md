# MAGNA Sprint 04.1 External Audit Scope

Status: READY_FOR_SCOPING_NOT_ENGAGED

The scope matrix is complete enough to approach an independent auditor without
misrepresenting off-chain components as contracts. No auditor has been hired,
paid or accepted in this repository.

In scope for audit:

- `TokoinFixedSupply` fixed-supply ERC-20 source.
- `TokoinResearchRewards` prefunded Merkle settlement, reservation accounting,
  replay protection, trust model and abandoned-claim behavior.
- `AgoraAgentIdentity` locked ERC-721/ERC-5192 mirror, issuer concentration,
  uniqueness, revocation and non-transferability.
- Hardhat compilation, contract tests, release preflight and Base Sepolia
  deployment/receipt scripts.
- Reproducibility of production bytecode and proposed internal-ledger snapshot
  to Merkle-root migration procedure.
- Chain guard behavior and public-testnet deployment readiness.
- Off-chain reservation, settlement and wallet-binding trust boundaries.
- Evidence that no legacy TOKOIN balances are moved into the testnet plane.
- Documentation that TOKOIN rewards do not certify truth.

Out of scope until a future sprint:

- Mainnet deployment.
- Pool escrow contract.
- Permissionless or trustless research-result adjudication. The initial root is
  an explicit 2-of-3 multisig attestation, not a truth oracle.
- Knowledge Fabric verified-source providers.
