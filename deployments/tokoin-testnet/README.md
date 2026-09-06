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
npm run audit:static
npm audit --audit-level=high
```

Run `npm run preflight:base-sepolia` to list blockers. Do not create a fake audit
or authorization document to make it pass. Deployment requires an independently
accepted audit and a separately signed authorization for the exact contract
release, audit hash, network and multisig addresses.
