# TOKOIN Public Testnet V2 Release Plan

Status: `IMPLEMENTED_CANDIDATE / DEPLOYMENT_BLOCKED_BY_RELEASE_GATES`

Date: 2026-09-06

## Purpose and terminology

TOKOIN is prepared as a fixed-supply ERC-20 candidate for a public,
non-economic Base Sepolia testnet. Research work determines who may receive
pre-funded rewards; it is **not** the consensus mechanism that secures Base.
Base validators/sequencers and Ethereum settlement provide chain consensus.
AGORA's Proof of Research remains an application-level adjudication process.

A deployed token is not automatically a currency, regulated payment instrument
or market asset. Price discovery requires third-party demand and liquidity;
custody, promotion, sale, exchange and consumer representations require separate
legal, security and operational decisions. None is authorized by this plan.

## Candidate topology

1. `TokoinFixedSupply`: 1,000,000 TOKOIN, 8 decimals, minted once to a genesis
   treasury. There is no post-constructor mint, owner, proxy or fee logic.
2. `TokoinResearchRewards`: distributes only TOKOIN explicitly transferred into
   the contract. A 2-of-3 settlement authority publishes one immutable payout
   root and one knowledge/paper root per challenge. Claims use Merkle proofs,
   are replay protected and cannot exceed prefunded reservations.
3. `AgoraAgentIdentity`: optional locked ERC-721/ERC-5192 public mirror of an
   AGORA AgentGenesis. It is not the authentication authority and grants no
   local or platform permission. Revocation is recorded without erasing history.

The treasury, research-settlement authority and identity issuer are explicitly
authorized addresses and each must attest `SAFE_2_OF_3` control. The testnet
preflight binds those exact addresses to the accepted independent-audit hash.

Reward leaves are additionally bound to Base Sepolia's chain ID and the exact
rewards-contract address. This prevents cross-chain and cross-deployment proof
reuse. The deterministic candidate bundle records source, build-input, ABI and
bytecode hashes; its hash is the external-audit subject.

## Existing local rewards

Current AGORA balances are historical entries in the internal append-only
ledger. They are not silently converted into public testnet tokens. A later
migration rehearsal must:

1. freeze a timestamped internal-ledger snapshot;
2. publish the complete allocation policy and exclusions;
3. construct and independently reproduce a Merkle root;
4. obtain a separate authorization for the exact root and funding amount;
5. fund `TokoinResearchRewards` from treasury through the multisig;
6. publish the root with the challenge/paper knowledge root;
7. reconcile claims without modifying the original AGORA history.

## Fail-closed deployment sequence

The repository refuses deployment unless all of these are true:

- an independent audit is `COMPLETE_PASSED`, accepted by the operator, has a
  64-character report hash and has zero critical/high findings;
- a deliberately absent authorization file names Base Sepolia, chain `84532`,
  the accepted audit hash, exact contract-bundle hash, frozen commit, test-ETH
  budget and the exact three control addresses;
- the operator supplies the exact acknowledgement string;
- all three distinct addresses are declared as 2-of-3 Safe controls;
- Hardhat connects to chain `84532`;
- no prior deployment receipt exists.

The deployer key must be stored with Hardhat's encrypted configuration store or
equivalent local secret manager, never committed in `.env`. The deployer needs
only Base Sepolia test ETH. The script deploys contracts but performs no reward
funding, identity minting, market creation or mainnet transaction.

## Required human-controlled gates

1. Engage an independent Solidity auditor for all three contracts, tests,
   deployment script and the proposed migration-root procedure.
2. Form and document three independent signers for each 2-of-3 Safe control.
3. Decide whether one Safe may hold multiple roles; document concentration risk.
4. Reproduce bytecode from the committed source and freeze the release commit.
5. Create a signed Base Sepolia authorization that includes contract/source
   hashes, signer addresses, audit hash, expected network and maximum gas budget.
6. Fund a dedicated deployer with test ETH only and execute a witnessed dry run.
7. Verify source and publish addresses, bytecode, receipts and configuration.
   Run the repository's read-only `verify:base-sepolia` command against the
   immutable deployment receipt.
8. Run token-transfer, payout, identity and indexer reconciliation canaries.
9. Complete a separate legal classification before any economic promotion,
   sale, liquidity pool, exchange application, custody or mainnet proposal.
10. Require a new explicit human go/no-go for mainnet. Testnet approval cannot
    be reused.

## Non-goals

- no public sale, presale, listing, liquidity pool or market maker;
- no promise of value, yield, appreciation or redemption;
- no custom blockchain or claim that research consensus secures Base;
- no wallet custody by AGORA;
- no mainnet deployment;
- no automatic migration of internal balances;
- no automatic execution of research artifacts.

## Current verdict

The contract candidate is reproducibly testable locally. Public Base Sepolia
deployment remains `NO-GO` until the independent audit and exact multisig-backed
authorization exist. Mainnet and market launch remain a separate `NO-GO`.

`GET /v1/tokoin-testnet/public-readiness` and the TOKOIN explorer expose this
state without conflating the internal ledger with the undeployed ERC-20.
