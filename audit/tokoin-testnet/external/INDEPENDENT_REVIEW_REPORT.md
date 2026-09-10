# INDEPENDENT TECHNICAL REVIEW REPORT

## TOKOIN Contract Release Candidate v1 (Remediated)

| Field | Value |
|-------|-------|
| **Project** | AGORA / TOKOIN |
| **Reviewer** | Claude Opus 4.6 (acting as independent reviewer per operator instruction) |
| **Review Type** | FULL_INDEPENDENT_TECHNICAL_REVIEW |
| **Independence** | SAME_AI_FAMILY_AS_AUTHOR (see Disclosure section) |
| **Date** | 2026-09-07 |
| **Commit** | `1ceb2a0f8dc18a4e5ec6f28cf4cef15f80689f4b` |
| **Bundle SHA-256** | `3043f6345d00e3ff3da777f9094283789f6af661f4af8453869fbf8e8f8fc4db` |
| **Target Network** | Base Sepolia (chain_id: 84532) |
| **Economic Value** | None (testnet only) |
| **Mainnet Authorized** | NO |

---

## INDEPENDENCE DISCLOSURE

This review was conducted by Claude Opus 4.6 at the explicit instruction of the
project operator to test AI precision in security decision-making. The reviewer
is the same AI model family that authored portions of the code under review.
This creates an inherent circularity that limits the independence guarantee.

**This report documents the technical findings and decisions to the best of the
reviewer's analytical capability, but it CANNOT substitute for an independent
human audit from a party with no relationship to the codebase.**

The operator has acknowledged this limitation and requested the review proceed
as a capability demonstration.

---

## PHASE 1: INTEGRITY VERIFICATION (EXECUTED)

### 1.1 Commit Verification
```
$ git rev-parse HEAD
1ceb2a0f8dc18a4e5ec6f28cf4cef15f80689f4b
```
**Status**: CONFIRMED

### 1.2 Source File SHA-256 Verification
```
$ sha256sum contracts/*.sol
ce47ac22...  TokoinFixedSupply.sol      MATCH (bundle)
a10ba1c5...  TokoinResearchRewards.sol  MATCH (bundle)
7b5234d5...  AgoraAgentIdentity.sol     MATCH (bundle)
26fb5e31...  TokoinControlPlane.sol     MATCH (bundle)
```
**Status**: ALL 4 MATCH

### 1.3 Reproducible Compilation
```
$ npm ci          -> 0 vulnerabilities
$ npx hardhat clean && npm run compile -> 4 files, solc 0.8.30, cancun
```
**Status**: CONFIRMED

### 1.4 Bundle Reconstruction
```
$ node -e "import {buildCandidateBundle} from './scripts/candidate-bundle-lib.mjs'; ..."
Reconstructed: 3043f6345d00e3ff3da777f9094283789f6af661f4af8453869fbf8e8f8fc4db
Expected:      3043f6345d00e3ff3da777f9094283789f6af661f4af8453869fbf8e8f8fc4db
Match: true
```
**Status**: CONFIRMED - Bundle is reproducible from source.

### 1.5 Bundle Self-Integrity
```
$ npm run bundle:verify
{"ok":true,"bundle_sha256":"3043f634..."}
```
**Status**: CONFIRMED

**Phase 1 Verdict: PASS**

---

## PHASE 2: TEST EXECUTION (EXECUTED)

| # | Command | Result |
|---|---------|--------|
| 1 | `npm run test:contracts` | **21/21 invariants PASS**, gas: 107,843 for 1024-leaf claim |
| 2 | `npm run test:preflight` | **6/6 PASS** |
| 3 | `npm run test:bundle` | **9/9 PASS** (includes Merkle property tests at 1-1024 leaves) |
| 4 | `npm run audit:static` | **PASS** (3 contracts, no forbidden patterns) |
| 5 | `npm run bundle:verify` | **PASS** |
| 6 | `npm audit --audit-level=high` | **0 vulnerabilities** |

**Total: 36 tests executed, 36 passed, 0 failed.**

**Phase 2 Verdict: PASS**

---

## PHASE 3: INDEPENDENT SECURITY ANALYSIS (15 ATTACK VECTORS)

Each vector was analyzed independently against the contract source code.

| # | Attack Vector | Vulnerable? | Severity | Notes |
|---|---------------|-------------|----------|-------|
| 1 | Reentrancy in `claim()` | **NO** | N/A | State updated before `safeTransfer` (L186-188 before L189). CEI pattern correct. |
| 2 | Integer overflow/underflow | **NO** | N/A | Zero `unchecked` blocks. solc 0.8.30 built-in checks. |
| 3 | Front-running publishSettlement/claim | **NO** | N/A | Authority-gated. Claim pays embedded account, not msg.sender. |
| 4 | Flash loan balance manipulation | **NO** | N/A | `publishSettlement` is authority-gated. |
| 5 | Storage collision (mapping keys) | **NO** | N/A | Different base slots. keccak256 collision resistance. |
| 6 | ERC-20 approval race condition | **YES** | INFO | Inherited ERC-20 spec limitation. No impact on rewards (uses safeTransfer, not allowances). |
| 7 | Merkle second preimage attack | **NO** | N/A | Double-hash leaf construction (L77-79). 32-byte vs 64-byte disambiguation. |
| 8 | Soulbound bypass via `_safeMint` callback | **NO** | N/A | `_update` override blocks all transfers. `identityMinted` set before callback (L42). |
| 9 | Griefing via `releaseExpiredSettlement` | **NO** | N/A | Permissionless by design. Only works after deadline. No fund redirection. |
| 10 | Timestamp manipulation | **NO** | N/A | MIN_CLAIM_WINDOW = 1 day. Validator drift is seconds. Negligible. |
| 11 | Token supply conservation | **NO** | N/A | No mint/burn after constructor. Supply immutable. |
| 12 | `reservedAmount` accounting | **NO** | N/A | Consistent across all 4 paths. Double-release blocked by `remaining == 0` check. |
| 13 | Zero-address in `claim` | **NO** | N/A | Blocked at L169. OZ ERC20 also blocks at transfer level. |
| 14 | Empty proof for multi-leaf tree | **NO** | N/A | Empty proof returns leaf unchanged. Only matches root for single-leaf trees. |
| 15 | DoS via large proof arrays | **YES** | INFO | No explicit length cap. Self-limiting: invalid proofs waste attacker's gas only. |

**New findings from independent analysis:**

- **IV-01 (INFORMATIONAL)**: Inherited ERC-20 approval race condition. Standard specification
  limitation. No impact on reward system. No fix required.
- **IV-02 (INFORMATIONAL)**: No explicit `proof.length` cap in `claim()`. Adding
  `require(proof.length <= 256)` would be trivial hardening but is not required for testnet.

**Phase 3 Verdict: PASS** (0 Critical, 0 High, 0 Medium, 0 Low, 2 Informational)

---

## PHASE 4: LINE-BY-LINE CONTRACT REVIEW

### TokoinFixedSupply.sol (27 lines)

Minimal fixed-supply ERC-20. No owner, no mint after constructor, no burn, no pause,
no permit, no votes, no fees, no upgradability. Constructor mints exactly
100,000,000,000,000 aceros to immutable `genesisTreasury`. Zero-address treasury
rejected.

**Verdict: SOUND.** No findings.

### TokoinResearchRewards.sol (192 lines)

Merkle-tree reward distribution with domain-separated proofs. Key properties verified:

- Authority-only settlement publishing (L97)
- Bounded claim deadlines: 1 day to 365 days (L25-26, L99-102)
- Permissionless expired settlement release (L148-158)
- Authority-only pre-claim cancellation (L132-144)
- Authority-only claim pause (L124-128)
- Zero-amount rejection (L170)
- Double-claim prevention via `claims[claimId]` (L177)
- Supply conservation: `safeTransfer` only, no mint/burn
- `reservedAmount` accounting: consistent across publish/claim/cancel/release
- Domain separation: `block.chainid`, `address(this)`, `challengeId`, `account`, `amount`, `role` (L77-79)

**Verdict: SOUND.** Findings NF-02 and NF-03 from prior audit confirmed. See decisions below.

### AgoraAgentIdentity.sol (82 lines)

Soulbound ERC-721 with ERC-5192 locked interface. All transfer paths blocked:

- `_update` override: reverts if `_ownerOf(tokenId) != address(0)` (L75)
- `approve`: unconditional revert (L62-64)
- `setApprovalForAll`: unconditional revert (L66-68)
- Only `_safeMint` (owner == address(0)) passes `_update`
- Issuer-only minting and revocation
- Duplicate identity and duplicate revocation prevention
- `identityMinted` set BEFORE `_safeMint` callback (L42): reentrancy safe

**Verdict: SOUND.** No findings.

### TokoinControlPlane.sol (26 lines)

Non-deployable library defining constants and events. Role caps sum to
100,000,000 aceros (1 TOKOIN). No external interaction surface.

**Verdict: SOUND.** No findings.

---

## PHASE 5: PRIOR FINDINGS DISPOSITION TABLE

### BINDING DECISIONS

| ID | Prior Severity | Disposition | Reviewer Decision | Justification |
|----|---------------|-------------|-------------------|---------------|
| F-01 | MEDIUM | FIXED | **ACCEPT FIX** | `releaseExpiredSettlement()` is permissionless, time-bounded (1-365 days). Confirmed at L148-158. |
| F-02 | LOW | FIXED | **ACCEPT FIX** | `revert ZeroAmount()` at L170. Trivial and correct. |
| F-03 | MEDIUM | FIXED | **ACCEPT FIX** | Narrow pause + pre-claim cancellation. Roots immutable. Confirmed at L124-144. |
| F-04 | INFO | FIXED | **ACCEPT FIX** | `revert IdentityAlreadyRevoked()` at AgoraAgentIdentity.sol L52. |
| F-05 | LOW | ACCEPTED | **ACCEPT DESIGN** | Standard Merkle airdrop pattern. Payment bound to leaf account. |
| F-06 | LOW | ACCEPTED | **ACCEPT WITH CONDITION** | Requires REAL Safe 2-of-3 verified on-chain. See NF-02 decision. |
| F-07 | INFO | DEFERRED | **ACCEPT DEFERRAL** | No security impact. AGORA profiles are canonical. |
| F-08 | MEDIUM | FIXED | **ACCEPT FIX** | 5-layer defense-in-depth. Dual-gate, rate limiting, CSRF. |
| F-09 | LOW | STRENGTHENED | **ACCEPT** | 5 independent layers. Default-deny. |
| F-10 | LOW | ACCEPTED | **ACCEPT WITH CONDITION** | Same condition as F-06: Safe must be verified on-chain. |

### NEW FINDINGS DECISIONS

| ID | Severity | Title | Reviewer Decision | Justification |
|----|----------|-------|-------------------|---------------|
| NF-01 | INFO | solc 0.8.30 known bugs (not triggered) | **ACCEPT FOR TESTNET** | No viaIR, no transient storage. Upgrade to 0.8.36+ required before mainnet. |
| NF-02 | LOW | Preflight checks attestation, not on-chain Safe | **REQUIRE CHANGES (post-deployment)** | Add `Safe.getThreshold()` and `Safe.getOwners()` verification to `verify-base-sepolia.mjs`. Must pass before any settlement activity. |
| NF-03 | LOW | `setClaimsPaused` indefinite DoS | **ACCEPT FOR TESTNET** | No economic value at stake. Require `MAX_PAUSE_DURATION` before any value-bearing deployment. |

### INDEPENDENT ANALYSIS FINDINGS

| ID | Severity | Title | Reviewer Decision | Justification |
|----|----------|-------|-------------------|---------------|
| IV-01 | INFO | ERC-20 approval race condition (inherited) | **ACCEPT** | ERC-20 spec limitation. No impact on reward system. |
| IV-02 | INFO | No explicit `proof.length` cap | **ACCEPT FOR TESTNET** | Self-limiting. Invalid proofs waste only attacker's gas. Optional hardening: `require(proof.length <= 256)`. |

---

## PHASE 6: CONSOLIDATED FINDINGS SUMMARY

| Severity | Count | IDs |
|----------|-------|-----|
| CRITICAL | 0 | -- |
| HIGH | 0 | -- |
| MEDIUM | 0 | -- |
| LOW | 2 | NF-02, NF-03 |
| INFORMATIONAL | 3 | NF-01, IV-01, IV-02 |
| **Total** | **5** | |

---

## PHASE 7: PREFLIGHT GATE ANALYSIS

The 33-point preflight gate (`release-preflight-lib.mjs`, 144 lines) was reviewed
in full. Key observations:

1. **Correctly blocks** unauthorized networks, missing audits, missing independence
   disclosure, mismatched hashes, single-key treasuries, concentrated roles.
2. **Tests cover** 6 scenarios including address substitution, mainnet rejection,
   bundle binding, and role concentration.
3. **NF-02 limitation confirmed**: Lines 112-119 check `SAFE_2_OF_3` environment
   variable but cannot verify on-chain. This is acceptable for the preflight
   (pre-deployment) stage IF supplemented by post-deployment verification.

---

## PHASE 8: DEPLOYMENT READINESS CHECKLIST

| # | Requirement | Status | Blocker? |
|---|-------------|--------|----------|
| 1 | Commit frozen at `1ceb2a0f` | DONE | No |
| 2 | Bundle SHA-256 verified and reproducible | DONE | No |
| 3 | Source hashes match bundle | DONE | No |
| 4 | ABI/bytecode match after clean compile | DONE | No |
| 5 | 36 tests pass, 0 fail | DONE | No |
| 6 | 0 npm vulnerabilities | DONE | No |
| 7 | Static audit: no forbidden patterns | DONE | No |
| 8 | 15 attack vectors analyzed: 0 Critical/High/Medium | DONE | No |
| 9 | Prior findings (F-01 to F-10) all resolved | DONE | No |
| 10 | Founder ratification 8/8 | DONE | No |
| 11 | **Independent human auditor engaged** | **NOT DONE** | **YES** |
| 12 | **Safe 2-of-3 created (treasury)** | **NOT DONE** | **YES** |
| 13 | **Safe 2-of-3 created (settlement authority)** | **NOT DONE** | **YES** |
| 14 | **Safe 2-of-3 created (identity issuer)** | **NOT DONE** | **YES** |
| 15 | **3 Safe addresses verified as distinct** | **NOT DONE** | **YES** |
| 16 | **Safe signers named** | **NOT DONE** | **YES** |
| 17 | **Post-deployment Safe verification (NF-02)** | **NOT DONE** | **YES** |
| 18 | **Deploy authorization signed (not .example)** | **NOT DONE** | **YES** |
| 19 | Base Sepolia deployment | NOT DONE | Blocked by 11-18 |
| 20 | Post-deployment verification (verify-base-sepolia) | NOT DONE | Blocked by 19 |
| 21 | Human go/no-go for private pilot | NOT DONE | Blocked by 20 |

---

## PHASE 9: FINAL DECISION

### For Base Sepolia testnet deployment (no economic value):

**DECISION: CONDITIONALLY APPROVED**

The contracts are technically sound for a zero-value testnet deployment. All 327
lines of Solidity have been reviewed line by line, 15 attack vectors have been
independently analyzed, 36 automated tests pass, the bundle is reproducible, and
no Critical, High, or Medium severity issues remain.

### Conditions that MUST be satisfied before deployment:

1. **Create 3 distinct Safe 2-of-3 contracts on Base Sepolia** with named signers
2. **Add Safe verification to post-deployment script** (NF-02): query
   `getThreshold()` and `getOwners()` for all 3 Safe addresses
3. **Create real `base-sepolia-deploy-authorization.json`** (not `.example`)
   with real addresses, real commit, real budget, and `"authorize_transaction": true`
4. **All 33 preflight checks must pass** with real data

### Conditions that MUST be satisfied before ANY value-bearing phase:

1. Independent human audit from a party unrelated to this codebase
2. `MAX_PAUSE_DURATION` implemented for `setClaimsPaused` (NF-03)
3. Compiler upgrade to solc 0.8.36+ (NF-01)
4. Property-based fuzz testing (Foundry/Echidna)
5. `proof.length` cap in `claim()` (IV-02, optional hardening)

### Explicitly NOT authorized:

- Ethereum mainnet deployment
- Base mainnet deployment
- Any deployment with economic value
- Public sale or presale
- Third-party fund custody
- Genesis-100 activation

---

## APPENDIX A: FILES REVIEWED

### Contracts (327 lines)
- `contracts/TokoinFixedSupply.sol` (27 lines)
- `contracts/TokoinResearchRewards.sol` (192 lines)
- `contracts/AgoraAgentIdentity.sol` (82 lines)
- `contracts/TokoinControlPlane.sol` (26 lines)

### Scripts (reviewed in full)
- `scripts/release-preflight-lib.mjs` (144 lines)
- `scripts/deploy-base-sepolia.mjs` (74 lines)
- `scripts/verify-base-sepolia.mjs` (60 lines)
- `scripts/static-audit.mjs` (68 lines)
- `scripts/contract-tests.mjs` (265 lines)
- `scripts/settlement-bundle-lib.mjs` (113 lines)
- `scripts/candidate-bundle-lib.mjs` (107 lines)
- `scripts/deployment-verifier-lib.mjs` (48 lines)

### Tests (reviewed in full)
- `test/release-preflight.test.mjs` (134 lines)
- `test/settlement-bundle.test.mjs` (84 lines)
- `test/candidate-bundle.test.mjs` (read)
- `test/deployment-verifier.test.mjs` (read)

### Audit artifacts (all read)
- `audit/tokoin-testnet/external/CLAUDE_REMEDIATION_AUDIT_REPORT.md`
- `audit/tokoin-testnet/external/claude-remediation-audit-results.json`
- `audit/tokoin-testnet/external/auditor-independence-disclosure.json`
- `audit/tokoin-testnet/external/audit-report-reference.json`
- `audit/tokoin-testnet/release-candidate/contract-release-bundle-v1.json`
- `audit/tokoin-testnet/release-candidate/base-sepolia-deploy-authorization.example.json`
- `audit/tokoin-testnet/release-candidate/source_tree.sha256`
- `audit/tokoin-testnet/release-candidate/test-report.json`
- `audit/tokoin-testnet/release-candidate/SBOM.json`
- `audit/tokoin-testnet/ratifications/founder-ratification-bundle-ratified-2026-08-29.json`
- `audit/tokoin-testnet/private-pilot/readiness-report.json`

### Configuration
- `hardhat.config.js`
- `package.json`

---

## APPENDIX B: COMMANDS EXECUTED BY REVIEWER

```
git rev-parse HEAD
git log --oneline -10
sha256sum contracts/TokoinFixedSupply.sol contracts/TokoinResearchRewards.sol \
         contracts/AgoraAgentIdentity.sol contracts/TokoinControlPlane.sol
npm ci
npx hardhat clean && npm run compile
npm run bundle:verify
npm run audit:static
npm audit --audit-level=high
npm run test:contracts
npm run test:preflight
npm run test:bundle
node -e "import {buildCandidateBundle} ..." (independent bundle reconstruction)
```

All commands executed live during review session. No cached or pre-computed results.

---

*Report generated: 2026-09-07*
*Reviewer: Claude Opus 4.6 (independent review capability demonstration)*
*Commit: 1ceb2a0f8dc18a4e5ec6f28cf4cef15f80689f4b*
*Bundle: 3043f6345d00e3ff3da777f9094283789f6af661f4af8453869fbf8e8f8fc4db*
