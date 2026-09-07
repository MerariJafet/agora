# MAGNA Sprint 04.1 External Audit Scope

Status: READY_FOR_SCOPING_NOT_ENGAGED

Canonical audit target:
`audit/tokoin-testnet/release-candidate/contract-release-bundle-v1.json`.
The auditor must record and sign the bundle's `bundle_sha256`; a source,
compiler-input, ABI or bytecode change creates a different candidate.

The scope matrix is complete enough to approach an independent auditor without
misrepresenting off-chain components as contracts. No auditor has been hired,
paid or accepted in this repository.

In scope for audit:

- `TokoinFixedSupply` fixed-supply ERC-20 source.
- `TokoinResearchRewards` prefunded Merkle settlement, reservation accounting,
  replay protection, chain/contract domain separation, trust model and
  abandoned-claim behavior.
- `AgoraAgentIdentity` locked ERC-721/ERC-5192 mirror, issuer concentration,
  uniqueness, revocation and non-transferability.
- Hardhat compilation, contract tests, release preflight and Base Sepolia
  deployment/receipt scripts.
- Reproducibility of production bytecode and proposed internal-ledger snapshot
  to Merkle-root migration procedure.
- Deterministic settlement-bundle construction, OpenZeppelin proof
  compatibility, recipient/amount/role review and duplicate-leaf rejection.
- Read-only Base Sepolia postdeployment verification and immutable receipt
  validation.
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
