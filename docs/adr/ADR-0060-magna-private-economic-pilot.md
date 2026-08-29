# ADR-0060: MAGNA Private Economic Pilot Boundary

Status: Accepted

## Context

The founder ratification bundle authorizes a private local-devnet economic
pilot, but not Base Sepolia, mainnet, public liquidity, Genesis-100 activation
or custody of third-party funds. AGORA must be able to test reward accounting
without manufacturing real economic activity or migrating legacy balances.

## Decision

AGORA adds a private TOKOIN pilot plane around the existing local-devnet
TOKOIN testnet controls. The plane records ratification receipts, reconciles
approved local-devnet settlement plans into `PRE_PUBLIC_EARNED` entitlements,
creates TEST-only migration snapshots and exposes read-only Genesis-100 wallet
readiness.

The plane is explicitly not a public token launch:

- Only chain id `31337` local-devnet transfers are represented.
- Mainnet and Base Sepolia deployment remain unauthorized.
- Genesis-100 wallets are scanned read-only and agents are not activated.
- No raw wallet private keys, seeds or recovery material are accepted.
- PRE_PUBLIC_EARNED is a local pilot classification, not a public claim right.
- Mutating pilot controls fail closed when `AGORA_ENV=production`.

## Consequences

The seven-agent private canary can now be authorized as a human decision after
reviewing code, tests and the ratification receipt state. Public testnet and
mainnet remain blocked by independent external audit and separate go/no-go.
