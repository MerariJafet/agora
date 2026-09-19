# TOKOIN candidate bundle — rebaseline 2026-09-18

## Why

A high-severity advisory landed on `adm-zip <= 0.6.0`
([GHSA-vwc7-r8mq-g2x9](https://github.com/advisories/GHSA-vwc7-r8mq-g2x9)
symlink-following extraction, and
[GHSA-7q85-xj36-vmfc](https://github.com/advisories/GHSA-7q85-xj36-vmfc)
uncontrolled memory allocation). `adm-zip` is a transitive dependency of
`hardhat@3.15.0`; the fix is the patch release `0.6.1`, applied via
`npm audit fix`, which moves `package-lock.json` and nothing else.

`package-lock.json` is one of the `build_inputs` sealed by the candidate
bundle, so taking the security fix necessarily invalidates the hash of the
2026-09-09 bundle. The operator runbook is explicit that the historical bundle
must not be overwritten and its audits must not be re-bound to a new hash, so
this is a **new dated candidate**; `audit/launch-2026-09-09/` is left byte for
byte as it was.

## What actually changed

Comparing `launch-2026-09-09/tokoin-candidate-bundle.json` against
`launch-2026-09-18/tokoin-candidate-bundle.json`, exactly **two** fields
differ:

| field | 2026-09-09 | 2026-09-18 |
| --- | --- | --- |
| `build_inputs["package-lock.json"]` | `f98521d4…` | `2ed78a19…` |
| `bundle_sha256` | `5086bcb6efd63e6758a447e6ed5d7984171f293fa7a4f2c0b2120b49d83cf2b6` | `d9c5c40f2ac0faf3e719830980790f4621ca29ed62dede3835016cb1b7cab617` |

Everything else is identical: all four contract sources, every ABI hash, every
creation- and deployed-bytecode hash, the toolchain (solc 0.8.30, hardhat
3.15.0, ethers 6.17.0, OpenZeppelin 5.6.1, EVM cancun) and the monetary policy
(fixed supply 1,000,000 TOKOIN, 8 decimals, not mintable after genesis).

**The dependency moved. The contracts did not.** A dev-time archive extractor
inside hardhat cannot reach the compiled output, and the byte-identical
bytecode hashes are the evidence rather than the claim.

## Status, unchanged

`UNDEPLOYED_AUDIT_CANDIDATE`, Base Sepolia (chain 84532), `economic_value:
false`, `mainnet_authorized: false`. This rebaseline is a dependency hygiene
step. It is **not** an external review, an authorization, or a deployment gate,
and it does not move the release any closer to one — those doors are still
described in `docs/launch/2026-09-09/operator-runbook.md`.

## Evidence in this directory

- `tokoin-candidate-bundle.json` — the new sealed candidate.
- `tokoin-npm-audit.log` — `npm audit --audit-level=high` reporting zero
  vulnerabilities, plus the resolved `adm-zip@0.6.1` in the hardhat tree.
