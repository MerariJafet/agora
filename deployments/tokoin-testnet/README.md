# TOKOIN Testnet Deployment Records

This directory contains immutable, public-safe deployment evidence. It must not
contain private keys, mnemonics, RPC credentials or unsigned claims of a real
deployment.

`base-sepolia-receipt.json` is created once by the guarded deployment script.
The script uses exclusive file creation and refuses to overwrite an existing
receipt. Absence of that file means no repository-recorded Base Sepolia
deployment exists.

Run local verification from `contracts/tokoin`:

```bash
npm ci
npm run compile
npm run test:contracts
npm run test:preflight
npm run test:bundle
npm run audit:static
npm run bundle:verify
npm audit --audit-level=high
```

The immutable audit handoff is
`audit/tokoin-testnet/release-candidate/contract-release-bundle-v1.json`.
It binds source, build inputs, ABI and bytecode. Rebuild it only when creating a
new audit candidate; any change requires a new external audit decision.

Create an unsigned, non-authorizing settlement proof package from reviewed JSON:

```bash
npm run settlement:build -- reviewed-allocations.json settlement-bundle.json
```

The input must identify chain `84532` (or local test chain `31337`), the exact
`TokoinResearchRewards` address, challenge, knowledge root, Unix
`claim_deadline` and recipient allocations. The on-chain deadline must be 1 to
365 days after publication. Leaves are domain-separated by chain and contract
address. The output does not publish a root or move TOKOIN.

Institutional local-devnet API mutations are disabled by default. A local
operator must set `AGORA_TOKOIN_LOCAL_CONTROL_PLANE_ENABLED=true`; production
rejects them regardless. Mutations also require an authenticated Owner, CSRF,
rate limiting and reservation-operator binding.

After a separately authorized deployment, verify it without a private key:

```bash
BASE_SEPOLIA_RPC_URL=https://... npm run verify:base-sepolia
```

This checks recorded transactions, deployed code, fixed supply, decimals,
treasury, settlement authority and identity issuer. It performs only RPC reads.

Run `npm run preflight:base-sepolia` to list blockers. Do not create a fake audit
or authorization document to make it pass. Deployment requires an independently
accepted human audit and a separately signed authorization for the exact
contract release, audit hash, network and multisig addresses. Internal
model-assisted review is useful evidence but does not satisfy this gate.
