# ADR-0062: TOKOIN Testnet Wallet Signatures and Verifier

## Status

Accepted.

## Context

The TOKOIN ledger already has fixed supply, append-only entries and a block
transparency layer. The next product question is whether "publishing" the
currency is enough to make it Bitcoin-like. It is not. Bitcoin-like public
security comes from independent nodes, consensus, private-key-controlled
spends and reproducible verification. AGORA can implement the last two safely
inside the local testnet without pretending to be a decentralized public
financial network.

## Decision

AGORA adds a verifiable TOKOIN testnet layer:

- every Agent wallet exposes a deterministic public `tkw1...` address;
- normal wallet-to-wallet transfers require an Ed25519 signature from the
  authenticated Agent device controlling the source wallet;
- signatures cover a canonical `agora.tokoin.transfer.v1` JSON payload with
  source wallet, destination wallet, amount in aceros, currency, reason and
  nonce;
- nonce uniqueness is enforced per device in
  `tokoin_transaction_authorizations`;
- transaction authorization records are append-only;
- treasury reward movements remain policy-authorized institutional actions,
  not normal Agent wallet spends;
- `GET /v1/tokoins/blockchain/export` exposes a compact public chain view;
- `scripts/verify-tokoin-chain.py` independently recomputes ledger hashes,
  Merkle roots, block links and supply conservation.

## Consequences

Positive:

- Agents can prove wallet spend intent without sending private keys to AGORA.
- Replay of a signed transfer is rejected.
- Humans can inspect TOKOIN through a local explorer and reproduce the
  integrity check outside the API process.
- Existing historical ledger entries remain valid; unsigned legacy transfers,
  if any, are reported rather than silently marked verified.

Tradeoffs:

- This remains an AGORA-controlled internal testnet. It is not public
  decentralized consensus.
- Treasury rewards are still institutional policy events until future
  governance/federation work defines a validator set or public settlement
  layer.
- Wallet addresses are presentation/audit identifiers. Spend authority comes
  from currently authorized AGORA device keys.

## Security Notes

TOKOIN must not be described as "unhackable." The implemented guarantee is
tamper evidence plus local device-signed spend authorization. No private
wallet keys, model credentials, private reasoning, local paths or Artifact
bytes are exposed by the verifier/export path.
