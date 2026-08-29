# MAGNA Sprint 04.1 Scope Completeness Matrix

Status: COMPLETE_LOCAL_CLASSIFICATION

This matrix separates implemented on-chain source from off-chain trust
boundaries and intentionally deferred release scope. It prevents AGORA from
claiming that local database controls are deployed contracts.

| Component | Classification | Evidence | Release claim |
| --- | --- | --- | --- |
| TokoinFixedSupply | IMPLEMENTED_ONCHAIN | `contracts/tokoin/contracts/TokoinFixedSupply.sol`, static audit script | Fixed-supply ERC-20 source is locally audit-ready. |
| GenesisTreasury | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `TokoinDeploymentManifest` placeholder | Treasury policy is local/off-chain until deployment. |
| RewardBudgetVault | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `TokoinReservation`, `TokoinSettlementPlan` | Reservation/budget accounting is database mediated. |
| ChallengeEscrow | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `TokoinReservation` | Challenge escrow is an off-chain saga, not trustless escrow. |
| RewardSplitter | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `ROLE_CAPS`, `TokoinClaimableAllocation` | Role-cap splitting is validated off-chain. |
| PoolEscrow | INTENTIONALLY_DEFERRED_AND_NOT_IN_RELEASE | Sprint 04 report | No release claim is made for pool escrow. |
| AgentPassportAnchor | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | Ed25519 identity, JWS Agent Cards | Passport anchoring remains off-chain identity. |
| KnowledgeRootRegistry | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `TokoinKnowledgeRootAnchor`, `MagnaMerkleBatch` | Knowledge roots are local projections, not chain registry writes. |
| SettlementSaga | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `TokoinSettlementPlan`, Event Ledger | Settlement is auditable local-devnet state. |
| WalletBinding | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `TokoinWalletBinding` | Wallet binding is receive-only and non-custodial. |
| DeploymentScriptsAndChainGuard | IMPLEMENTED_OFFCHAIN_WITH_EXPLICIT_TRUST_BOUNDARY | `/deployment/guard`, contract package | Mainnet/unknown chains are blocked; Base Sepolia remains gated. |

Missing blockers: none in local classification.

Blocking external gates: eight human ratifications and independent external
audit are still missing, so Sprint 04 remains `PARTIAL_AWAITING_RATIFICATION`.
