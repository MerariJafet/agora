# TOKOIN release review — 2026-09-09

Verdict: **NO-GO for public token launch, including public testnet until its existing release gates are met.** Internal AI code review and local reproduction; this is not an independent human/security-firm audit. No deployment, funding, signing, transaction, token issuance, or owner creation was performed.

## Scope and architecture

Reviewed all four Solidity sources and deployment, candidate bundle, preflight, settlement and verifier scripts in `contracts/tokoin`. Token has 8 decimals and 100,000,000,000,000 base units (1,000,000 TOKOIN), fixed at constructor time with no later mint. Research rewards distribute prefunded tokens via deployment-and-chain-bound Merkle leaves, enforce reservation accounting and immutable roots, and allow governed pause/cancellation before claims. Identity is an optional revocable locked ERC-721/ERC-5192 mirror; it grants no AGORA permissions. Off-chain adjudication remains trusted for allocations and does not establish scientific truth.

Boundaries: operator audit/authorization files -> deployment runner -> RPC -> immutable contracts; privileged treasury, settlement authority and identity issuer -> token/claim/identity operations; untrusted claim inputs -> proof and accounting checks. Mainnet/economic use is explicitly outside current deployment authorization schema.

## Reproduced and repaired

1. **HIGH / NF-02 partial remediation:** deployment previously trusted `SAFE_2_OF_3` environment declarations with no actual chain reads; postdeployment verifier omitted governance checks. Shared `verifyControlGovernance` now reads actual `eth_chainId`, checks each of three distinct nonzero control addresses has code, reads threshold exactly 2 and exactly 3 distinct nonzero owners, and records one common observed block. Deployment invokes it before its first transaction; read-only verification invokes the same function. Mock-based adversarial regressions cover wrong chain, EOA, one-of-three, two-of-four, duplicate and zero owners, duplicate roles and unavailable RPC. These are governance-interface checks, not proof that arbitrary code is a canonical Safe; implementation/proxy provenance and real controller independence remain externally unverified.
2. **HIGH / release candidate drift:** preflight accepted a valid historical bundle hash without comparison with current source/build artifacts, and candidate bundle omitted deployment/verifier/preflight scripts. It now hashes those inputs and compares current candidate hash during preflight; self-consistent but stale authorized bundles fail closed. Regression changes a deployment-script hash, recomputes bundle hash and rebinds fake fixture audit/authorization: readiness still rejects it. Fixture declarations are test data, not real approvals.
3. **RPC network verification:** direct `eth_chainId` prevents `staticNetwork` configuration from merely echoing an expected chain ID.

Nine source/test files changed; Solidity and dependency locks unchanged. Existing unrelated edits and historical audit artifacts were preserved.

## Fresh command evidence

Commands ran in `$AGORA_REPO/contracts/tokoin`. Complete stdout/stderr is in adjacent `tokoin-check-1.log` through `tokoin-check-7.log`; machine-readable exits are in `tokoin-checks.json`.

| Command | Observed result |
|---|---|
| `npx hardhat compile --build-profile production --force` | exit 0, actual clean recompilation |
| `npm run test:contracts` | exit 0, 21 EVM invariants; 1024-leaf claim gas 107843 |
| `npm run test:preflight` | exit 0, 7/7 tests |
| `npm run test:bundle` | exit 0, 18/18 tests, including 10 deployment verifier tests |
| `npm run audit:static` | exit 0 |
| `npm audit --json` | exit 1, 2 moderate, 0 high/critical |
| `npm run preflight:base-sepolia` | exit 1, expected NO-GO, explicit blockers in log |
| `npm run bundle:verify` | exit 1: historical candidate differs after fixes; intentionally preserved |

New `tokoin-candidate-bundle.json` was generated and read back, validated canonically and compared with current source/build artifacts. Bundle SHA-256: `5086bcb6efd63e6758a447e6ed5d7984171f293fa7a4f2c0b2120b49d83cf2b6`. It is an **undeployed unaudited replacement candidate**, not an approved release. Historical audit/authorization must never be silently rebound to this hash.

Dependency finding: `adm-zip` via Hardhat, advisory GHSA-vwc7-r8mq-g2x9, destination-symlink arbitrary overwrite during extraction (moderate). Live `npm view adm-zip version` returned 0.6.0, still affected. Inspected Hardhat downloader: extraction occurs only for Windows ZIP compilers; this Linux build follows chmod/native compiler path. No reachable exploitation reproduced here; retain a documented moderate Windows build-tool risk and use an isolated clean Linux build environment. Avoid unsupported forced Hardhat downgrade solely to make npm audit green.

## External release gates and residual risks

- Obtain real external audit, independence disclosure and operator acceptance bound to the exact fresh candidate. Current placeholder files do not meet these requirements.
- Establish and verify actual authorized Safe controls on Base Sepolia: canonical implementation/proxy bytecode provenance, threshold/owners, enabled modules/guards, and independently controlled signers. Interface-return values alone can be spoofed by arbitrary contracts. No supplied deployment receipt/on-chain governance was verified in this review.
- Provide actual hash-bound Base Sepolia authorization, release commit, test ETH budget, two distinct authorizers and configured role addresses. Current preflight fails closed for these absent facts.
- Independently verify deployed runtime bytecode against constructor-aware artifacts, receipts and block confirmations before accepting a future deployment. Existing verifier checks code existence, selected state and receipts, not full runtime equivalence; it must not serve as the sole authenticity attestation.
- NF-03 remains: settlement authority can pause indefinitely while deadlines advance. Acceptable only under explicitly disclosed valueless testing; economic launch needs a specified bounded-pause/deadline/appeal design and its own audit. No arbitrary governance policy was invented in this review.
- Mainnet/economic launch needs its own reviewed configuration, governance and incident policy, funded operational plan and real external compliance decisions. Deploying a token does not by itself create market value, research quality, institutional endorsement or liquidity.

The paper may accurately describe a locally tested, undeployed token mechanism and its limitations. It cannot claim an audited production currency, institutional validation or real economic rewards from this evidence.


## Final CI integration verification

`verify-candidate-bundle.mjs` accepts one explicit path (relative to the invoking working directory or absolute); absence of an argument retains the historical fail-closed default. CI can verify the replacement candidate with `npm run bundle:verify -- ../../audit/launch-2026-09-09/tokoin-candidate-bundle.json`. This returned exit 0 and the fresh hash shown above; output saved to `tokoin-bundle-verification.log`. Bundle binding also now covers the verifier entrypoint and `release-preflight.mjs`. Added a CLI regression covering a valid explicit relative candidate, tampering and a missing file; bundle tests 18/18 and preflight 7/7 passed after this integration. No deployment authorization was altered.
