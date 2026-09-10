# V04-C — Genesis Ceremony

Goal: transform "my blockchain" into "an initial state recognized by
distinct operators". This does not solve mainnet governance; it introduces
**administrative independence** at the root of the chain.

## Rules

1. **Nobody on the AGORA team generates another operator's validator key.**
   Each operator generates their own key on their own machine, keeps the
   private key, and publishes only the public key.
2. The genesis candidate is built collectively from the four public keys.
3. Every operator independently verifies, byte for byte:

```
genesis_hash
chain_id
protocol_version
validator_set        (the four public keys, powers)
initial_supply
reward_parameters
```

4. Each operator signs (or publicly confirms, with their published key)
   the genesis hash. Four confirmations → the ceremony record is frozen
   and published alongside the rehearsal report.
5. Any change to any parameter after confirmation = new ceremony, new
   hash, new record. No silent edits, ever.

## Ceremony record (published)

```
ceremony_id:
date:
participants: [operator_id → public_key]
genesis_hash:
confirmations: [operator_id → signature or signed statement]
tooling used + versions:
deviations / questions raised:
```

## Explicitly out of scope

Permissionless membership, stake-weighted governance, validator rotation,
slashing. V0.4 only needs to prove the creator does not silently hold all
four identities — which today he does, and after this ceremony he will
hold exactly one.
