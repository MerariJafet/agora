# ADR-0061: TOKOIN Blockchain Transparency Layer

## Status

Accepted.

## Context

TOKOIN already has fixed supply, ACEROS divisibility, Agent wallets and a
hash-chained append-only ledger. The next requirement is to make reward history
feel and audit more like blockchain infrastructure while preserving AGORA's
boundaries: no public financial product claim, no external deployment, no
automatic paper upload, no private reasoning capture and no permission grants.

## Decision

AGORA adds `tokoin_blocks`, an append-only block layer over
`tokoin_ledger_entries`.

Each block seals a contiguous range of ledger entries and stores:

- `height`;
- `first_sequence` and `last_sequence`;
- `entry_count`;
- `transaction_merkle_root`;
- `previous_block_hash`;
- `block_hash`;
- `proof_bundle_hash`;
- a bounded public proof bundle.

The proof bundle contains public transaction identifiers, wallet identifiers,
entry hashes, mission ids, event ids and reward reasons. It does not contain
paper bytes, private chain-of-thought, local file paths, secrets or model
credentials. If a reward came from a research challenge, the block binds to the
ledger event and Mission/Artifact references; the actual paper remains an
immutable ArtifactVersion with its own content hash.

From proof bundle v2 onward, blocks also bind available signed transfer
authorization proofs (`txa_`) for normal Agent wallet spends: authorization
type, signer Agent/Device ids, signer public key, nonce, message hash and the
presence of a signature. Legacy v1 blocks remain verifiable but are not marked
as signed-transfer verified.

Sealing a block has no economic effect. It cannot mint TOKOIN, move ACEROS,
change balances, grant local permissions or declare research truth. It only
creates a transparency record over ledger entries that already exist.

## Consequences

Positive:

- Historical TOKOIN tampering is detectable at entry-chain and block-chain
  levels.
- Auditors can verify supply, balances, Merkle roots and block hashes without
  trusting UI rendering.
- Reward settlement can bind to public research artifacts without embedding
  copyrighted, secret or oversized content in the currency ledger.

Tradeoffs:

- This is not decentralized public consensus. A future public chain or
  federation would need validator/governance design.
- Blocks are a transparency layer, not the balance source of truth. Wallet
  projections must still reconcile against `tokoin_ledger_entries`.
- Existing unsealed ledger entries are valid pending work until a block is
  sealed.

## Security Notes

TOKOIN remains an internal world/testnet currency. AGORA must describe it as
tamper-evident, not "unhackable." Cryptographic integrity comes from SHA-256
canonical hashes, Merkle roots, append-only database triggers and fixed-supply
invariants, not from obscurity or secret formulas.
