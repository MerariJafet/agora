# ADR-0063: Reproducible TOKOIN release and domain-separated claims

Status: Accepted for the undeployed Base Sepolia candidate

## Context

TOKOIN has an internal PostgreSQL ledger and a separate EVM testnet candidate.
Neither source code nor an application database proves which bytecode was
reviewed or deployed. A Merkle reward leaf that contains only challenge,
recipient, amount and role can also be reused accidentally if the same payout
root is published by another deployment.

## Decision

The EVM candidate has a deterministic release bundle that binds all Solidity
sources, Hardhat/package inputs, ABI and creation/runtime bytecode hashes. CI
rebuilds and verifies that bundle. The exact bundle hash is the unit submitted
to an independent auditor.

`TokoinResearchRewards.claimLeaf` binds every allocation to:

```text
chain_id | rewards_contract_address | challenge_id | account | amount | role
```

The settlement-bundle tool emits sorted, OpenZeppelin-compatible Merkle proofs.
It does not authorize, publish or fund a settlement. The postdeployment
verifier is read-only and checks receipts, contract code and immutable contract
configuration against Base Sepolia.

The deployment preflight requires the independent-audit reference and the
human authorization to name the same bundle hash. It also binds a full release
commit, integer test-ETH budget, two independent authorizer identities and
three distinct 2-of-3 Safe role addresses.

## Consequences

- Proofs cannot be reused across a different chain or rewards deployment.
- An auditor and operator can identify the exact candidate by one bundle hash.
- Changing source, compiler input, ABI or bytecode invalidates bundle verification.
- Independent audit, multisig setup and human authorization remain external gates.
- This does not create a new consensus network or make TOKOIN market-ready.
