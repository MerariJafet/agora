# CLAUDE INTERNAL TECHNICAL AUDIT REPORT

## TOKOIN Contract Release Candidate v1

| Field | Value |
|-------|-------|
| **Project** | AGORA / TOKOIN |
| **Auditor** | Claude Opus 4.6 (AI Internal Technical Review) |
| **Type** | AI_INTERNAL_TECHNICAL_REVIEW |
| **Independent External Audit** | NO |
| **Date** | 2026-09-06 |
| **Commit** | `001e202aee63b991d22ead591580584c6341f0c0` |
| **Bundle SHA-256** | `f283883379dffaa6cbe8b6498957b40a54f6283735e3c8f0b90395c836d165a5` |
| **Target Network** | Base Sepolia (chain_id: 84532) |
| **Economic Value** | None (testnet only) |
| **Mainnet Authorized** | NO |

---

## DISCLAIMER

This report is an AI-generated internal technical review. It is **NOT** a substitute
for an independent external human audit. The auditor is an AI model with no legal
standing, no financial liability, and no ability to verify runtime behavior on live
networks. This report must not be cited as a "security certification" or "audit
clearance" for any deployment, including testnet.

---

## EXECUTIVE SUMMARY

The TOKOIN release candidate (`001e202`) was audited across five phases: integrity
verification, smart contract analysis, automated and manual testing, control plane
review, and threat modeling. The candidate demonstrates a disciplined, minimal design
appropriate for a controlled testnet trial on Base Sepolia.

**No CRITICAL or HIGH severity findings were identified in the on-chain contracts.**

The on-chain contracts are well-constructed: fixed supply with no post-genesis minting,
immutable authority addresses, domain-separated Merkle claims with replay protection,
and soulbound ERC-721 identities. The primary contract-level concern is the permanent
locking of unclaimed settlement funds (MEDIUM).

The off-chain control plane contains appropriate production safeguards
(`require_local_control_plane()`) but has authorization gaps that should be remediated
before any production-grade deployment.

**Recommendation: `READY_FOR_HUMAN_EXTERNAL_AUDIT`**

---

## PHASE 1: INTEGRITY VERIFICATION

### 1.1 Commit Verification
- **Result**: CONFIRMED
- HEAD is `001e202aee63b991d22ead591580584c6341f0c0`
- Matches the specified audit target commit

### 1.2 Bundle SHA-256 Verification
- **Result**: CONFIRMED
- The bundle uses a self-referential hash scheme: `bundle_sha256` is the SHA-256 of
  `canonicalJson(payload)` where `payload` excludes the `bundle_sha256` field itself
- Computed: `f283883379dffaa6cbe8b6498957b40a54f6283735e3c8f0b90395c836d165a5`
- Expected: `f283883379dffaa6cbe8b6498957b40a54f6283735e3c8f0b90395c836d165a5`
- **MATCH**

### 1.3 Source File Hash Verification
All four source files match the bundle-recorded SHA-256 values:

| File | Bundle Hash (prefix) | Status |
|------|---------------------|--------|
| `contracts/AgoraAgentIdentity.sol` | `3cf5b8ec...` | MATCH |
| `contracts/TokoinControlPlane.sol` | `26fb5e31...` | MATCH |
| `contracts/TokoinFixedSupply.sol` | `ce47ac22...` | MATCH |
| `contracts/TokoinResearchRewards.sol` | `0864d3e0...` | MATCH |

### 1.4 Reproducible Compilation
- `npm ci`: 73 packages, 0 vulnerabilities
- `npx hardhat clean && npm run compile`: Compiled 4 Solidity files with solc 0.8.30 (cancun)
- Build is fully reproducible from `package-lock.json`

### 1.5 ABI and Bytecode Verification
All three deployable contracts match the bundle after clean recompilation:

| Contract | ABI | Creation Bytecode | Deployed Bytecode |
|----------|-----|-------------------|-------------------|
| TokoinFixedSupply | MATCH | MATCH | MATCH |
| TokoinResearchRewards | MATCH | MATCH | MATCH |
| AgoraAgentIdentity | MATCH | MATCH | MATCH |

### 1.6 Git Working Tree
- Two modified files outside contract scope: `bridge/agora_bridge/local_research_context_template.py` and `bridge/agora_bridge/local_runtime_driver.py`
- **Contract sources and build inputs are clean (unmodified)**

**Phase 1 Verdict: PASS -- No differences found. Evaluation continues.**

---

## PHASE 2: SMART CONTRACT AUDIT

### 2.1 TokoinFixedSupply.sol (27 lines)

**Design**: Minimal non-upgradeable ERC-20. Inherits only OpenZeppelin `ERC20`.
No owner, no mint after constructor, no burn, no pause, no permit, no votes, no fee.

| Check | Result |
|-------|--------|
| Fixed supply (100,000,000,000,000 aceros = 1,000,000 TOKOIN) | CONFIRMED |
| 8 decimals | CONFIRMED |
| No post-genesis mint function | CONFIRMED |
| No burn function | CONFIRMED |
| No pause/unpause | CONFIRMED |
| No permit/votes extensions | CONFIRMED |
| No owner/admin role | CONFIRMED |
| No upgradeability (no proxy, no delegatecall) | CONFIRMED |
| Immutable genesisTreasury | CONFIRMED |
| ZeroTreasury guard on address(0) | CONFIRMED |
| Full supply minted to genesisTreasury in constructor | CONFIRMED |
| Standard OpenZeppelin ERC-20 transfer/approve/allowance | CONFIRMED |
| Overflow/underflow protected by Solidity 0.8.30 | CONFIRMED |

**Findings**: None.

### 2.2 TokoinResearchRewards.sol (122 lines)

**Design**: Immutable Merkle-based claim contract. Settlement authority publishes
roots; users claim with proofs. Uses OpenZeppelin `SafeERC20` and `MerkleProof`.

| Check | Result |
|-------|--------|
| Immutable tokoin address | CONFIRMED |
| Immutable settlementAuthority | CONFIRMED |
| Authority-only publishSettlement | CONFIRMED |
| Settlement uniqueness per challengeId | CONFIRMED |
| Balance reservation tracking (reservedAmount) | CONFIRMED |
| Balance validation before publication | CONFIRMED |
| Domain-separated claim leaves (chainid, address(this), challengeId, account, amount, role) | CONFIRMED |
| Double-hash leaf construction (OZ standard) | CONFIRMED |
| OpenZeppelin MerkleProof.verifyCalldata | CONFIRMED |
| Double-claim prevention (claims mapping) | CONFIRMED |
| Cross-deployment replay prevention (address(this) in leaf) | CONFIRMED |
| Cross-chain replay prevention (block.chainid in leaf) | CONFIRMED |
| CEI pattern (state changes before safeTransfer) | CONFIRMED |
| No reentrancy vulnerability | CONFIRMED |
| Front-running: not exploitable (tokens go to specified account) | CONFIRMED |
| No delegatecall/selfdestruct/tx.origin | CONFIRMED |
| No unbounded loops (no DoS vector) | CONFIRMED |
| Overflow/underflow protected | CONFIRMED |
| Events: SettlementPublished, RewardClaimed (properly indexed) | CONFIRMED |
| Root immutability (no replacement after publish) | CONFIRMED |
| No emergency pause/freeze | SEE F-03 |
| No expiration/recovery for unclaimed funds | SEE F-01 |

### 2.3 AgoraAgentIdentity.sol (80 lines)

**Design**: Soulbound (non-transferable) ERC-721 implementing ERC-5192.
Issuer-only minting with identity uniqueness enforcement.

| Check | Result |
|-------|--------|
| Immutable issuer | CONFIRMED |
| Issuer-only minting | CONFIRMED |
| Identity uniqueness (identityMinted mapping) | CONFIRMED |
| Deterministic tokenId = uint256(agentIdentityHash) | CONFIRMED |
| Soulbound: _update rejects all post-mint transfers | CONFIRMED |
| approve() reverts Soulbound | CONFIRMED |
| setApprovalForAll() reverts Soulbound | CONFIRMED |
| ERC-5192: locked() always returns true | CONFIRMED |
| supportsInterface includes IERC5192 | CONFIRMED |
| Revocation without erasure (revoked mapping) | CONFIRMED |
| No burn function (token persists) | CONFIRMED |
| No upgradeability | CONFIRMED |
| IdentityRevoked event properly indexed | CONFIRMED |
| Duplicate revocation emits redundant event | SEE F-04 |

### 2.4 TokoinControlPlane.sol (26 lines)

**Design**: Pure library. Constants, events, and role cap policy.

| Check | Result |
|-------|--------|
| ONE_TOKOIN_ACEROS = 100,000,000 | CONFIRMED |
| Role caps sum to 100,000,000 aceros (= 1 TOKOIN per settlement) | CONFIRMED |
| Events properly indexed | CONFIRMED |
| No state, no deployable code | CONFIRMED |

---

## FINDINGS

### F-01: Unclaimed Settlement Funds Locked Permanently

| Field | Value |
|-------|-------|
| **ID** | F-01 |
| **Severity** | MEDIUM |
| **Component** | `TokoinResearchRewards.sol` lines 72-95 (publishSettlement), 97-121 (claim) |
| **Status** | CONFIRMED |

**Description**: Once a settlement is published via `publishSettlement()`, the
`totalAmount` is added to `reservedAmount`. Individual claims decrement both
`claimedAmount` and `reservedAmount`. However, there is no mechanism to expire,
cancel, or recover funds from partially or fully unclaimed settlements.

**Preconditions**: A settlement is published but one or more allocations are never
claimed (user loses key, user abandons claim, or invalid Merkle leaf).

**Impact**: TOKOIN tokens remain permanently locked in the contract. The
`reservedAmount` stays inflated, reducing the effective balance available for future
settlements.

**Scenario**: Settlement authority publishes settlement with totalAmount=50000000
for 5 accounts. 3 accounts claim. 2 accounts never claim. 20000000 aceros are
locked forever.

**Evidence**: No expiration timestamp, no admin recovery function, no
`unreserve()` mechanism exists in the contract.

**Recommendation**: Add a time-bounded recovery mechanism callable only by the
settlement authority after a sufficient expiration period (e.g., 180 days).
Alternatively, accept this as a design decision for testnet and document it.

**Test for correction**: Deploy contract, publish settlement, wait past expiration,
call recovery function, verify reservedAmount decreases.

---

### F-02: claim() Permits Zero-Amount Claims

| Field | Value |
|-------|-------|
| **ID** | F-02 |
| **Severity** | LOW |
| **Component** | `TokoinResearchRewards.sol` line 97-121 (claim) |
| **Status** | CONFIRMED |

**Description**: The `claim()` function does not require `amount > 0`. If a
zero-amount leaf exists in a Merkle tree, the claim succeeds: `claims[claimId]`
is set to true, `safeTransfer` transfers 0 tokens, and events are emitted.

**Preconditions**: A Merkle tree containing a leaf with amount=0 must be published.
The off-chain `buildSettlementBundle()` rejects `amount <= 0`, so this can only
occur if the settlement authority publishes a manually crafted root.

**Impact**: No economic impact. Wastes gas. Emits a misleading RewardClaimed event
with amount=0.

**Evidence**: Manual code inspection of `claim()` -- no `require(amount > 0)`.
Application-layer guard in `settlement-bundle-lib.mjs:69` (`if (amount <= 0n)`).

**Recommendation**: Add `if (amount == 0) revert ZeroAmount();` to `claim()` for
defense in depth. Low priority.

**Test for correction**: Attempt to claim with amount=0 and verify revert.

---

### F-03: No Emergency Pause or Root Correction Mechanism

| Field | Value |
|-------|-------|
| **ID** | F-03 |
| **Severity** | MEDIUM |
| **Component** | `TokoinResearchRewards.sol` lines 72-95 |
| **Status** | CONFIRMED |

**Description**: Once a settlement root is published, it cannot be corrected, paused,
or invalidated. If the settlement authority publishes an incorrect root (e.g., wrong
amounts, wrong accounts), the incorrect claims can be executed and cannot be stopped.

**Preconditions**: Settlement authority publishes an incorrect Merkle root due to
off-chain computation error.

**Impact**: Incorrect token distribution. No on-chain mechanism to halt or correct.
Requires deploying a new contract and migrating remaining funds.

**Scenario**: Off-chain bug computes wrong amounts. Root is published. Attacker with
a valid proof for an inflated amount claims before the error is detected.

**Evidence**: No `pause()`, no `freezeSettlement()`, no `invalidateRoot()` function.
The `SettlementAlreadyPublished` error prevents overwriting.

**Recommendation**: For testnet, this is an acceptable risk given the multisig
requirement on the settlement authority. For any future mainnet consideration, add
a time-locked pause mechanism or a two-phase commit (propose + finalize after delay).

**Test for correction**: Publish root, call freeze, attempt claim, verify revert.

---

### F-04: Duplicate Revocation Emits Redundant Events

| Field | Value |
|-------|-------|
| **ID** | F-04 |
| **Severity** | INFORMATIONAL |
| **Component** | `AgoraAgentIdentity.sol` lines 48-53 (revoke) |
| **Status** | CONFIRMED |

**Description**: The `revoke()` function does not check whether `revoked[tokenId]`
is already true. Multiple calls to `revoke()` for the same token each emit an
`IdentityRevoked` event and set `revoked[tokenId] = true` redundantly.

**Preconditions**: Issuer calls `revoke()` on an already-revoked token.

**Impact**: No security impact. May cause confusion in event indexers that count
revocations.

**Evidence**: No `if (revoked[tokenId]) revert AlreadyRevoked();` guard.

**Recommendation**: Add an already-revoked guard, or accept as intentional
(allows re-revocation with different reason hashes).

**Test for correction**: Revoke token, attempt second revoke, verify revert.

---

### F-05: Permissionless claim() Allows Third-Party Forcing

| Field | Value |
|-------|-------|
| **ID** | F-05 |
| **Severity** | LOW |
| **Component** | `TokoinResearchRewards.sol` lines 97-121 |
| **Status** | CONFIRMED |

**Description**: Any address can call `claim()` with a valid proof. The tokens are
transferred to the `account` specified in the leaf, not to `msg.sender`. This means
a third party can force a claim on behalf of any account without their consent.

**Preconditions**: Attacker has a valid Merkle proof for a victim's allocation.

**Impact**: The victim receives tokens they may not want (e.g., regulatory concerns).
No financial loss. This is standard behavior in Merkle airdrop patterns.

**Evidence**: `claim()` has no `require(msg.sender == account)` check. This is by
design in most Merkle distributors (e.g., Uniswap, OpenZeppelin).

**Recommendation**: For testnet, accept as-is. For mainnet, consider adding an
opt-in mechanism or allowing `msg.sender == account` enforcement.

**Test for correction**: Call claim from non-account address, verify revert.

---

### F-06: Settlement Authority Single Point of Trust

| Field | Value |
|-------|-------|
| **ID** | F-06 |
| **Severity** | LOW |
| **Component** | `TokoinResearchRewards.sol` line 69 |
| **Status** | CONFIRMED |

**Description**: The `settlementAuthority` is immutable. It cannot be rotated,
upgraded, or transferred. If the authority key is compromised, a new contract must
be deployed and remaining funds migrated. If the key is lost, no new settlements
can be published (but existing claims remain valid).

**Preconditions**: Key compromise or key loss of the settlement authority.

**Impact**: Key compromise: attacker can publish arbitrary settlements and drain
all unreserved funds. Key loss: no new settlements possible.

**Evidence**: `address public immutable settlementAuthority` -- no setter, no
transfer function.

**Recommendation**: Mitigated by requiring SAFE_2_OF_3 multisig. For testnet,
acceptable. Document key rotation procedure (redeploy + migrate).

**Test for correction**: N/A -- design decision. Verify multisig enforcement
at deployment.

---

### F-07: No tokenURI Implementation

| Field | Value |
|-------|-------|
| **ID** | F-07 |
| **Severity** | INFORMATIONAL |
| **Component** | `AgoraAgentIdentity.sol` |
| **Status** | CONFIRMED |

**Description**: `AgoraAgentIdentity` inherits the default `ERC721.tokenURI()`
which returns an empty string (no `_baseURI` override).

**Preconditions**: NFT explorer or frontend queries token metadata.

**Impact**: No metadata displayed. Purely cosmetic.

**Recommendation**: Implement `_baseURI()` or override `tokenURI()` if metadata
display is desired.

---

### F-08: Off-Chain Control Plane Authorization Gaps

| Field | Value |
|-------|-------|
| **ID** | F-08 |
| **Severity** | MEDIUM |
| **Component** | `apps/api/agora_api/magna_tokoin_testnet.py`, `routes/magna_tokoin.py` |
| **Status** | SUSPECTED |

**Description**: The off-chain control plane has several authorization gaps:

1. Settlement plan allocations are validated for wallet-binding/agent-id consistency,
   but there is no verification that the API caller controls the referenced agents.
2. Rate limiting is absent on settlement and reservation creation endpoints.
3. `POST /deployment/guard` lacks boundary schema validation.

**Preconditions**: Authenticated device or browser session in development mode.

**Impact**: In devnet context, an authenticated user could create allocations
referencing arbitrary agents. Mitigated by `require_local_control_plane()` which
blocks all mutations in production.

**Evidence**: Code review of `magna_tokoin_testnet.py` lines 827-926 (settlement
creation) and `routes/magna_tokoin.py` lines 123-240.

**Recommendation**: Add agent-ownership validation to settlement creation. Add rate
limiting to settlement and reservation endpoints. Add schema validation to the
deployment guard endpoint.

**Test for correction**: Attempt to create settlement with allocations for agents
not controlled by the caller, verify rejection.

---

### F-09: Production Guard Single Point of Failure

| Field | Value |
|-------|-------|
| **ID** | F-09 |
| **Severity** | LOW |
| **Component** | `apps/api/agora_api/magna_tokoin_testnet.py` lines 89-92 |
| **Status** | CONFIRMED |

**Description**: All mutation endpoints depend on `require_local_control_plane()`
which checks `get_settings().is_production`. This is a single function guarding
the entire off-chain to on-chain boundary. If `is_production` returns false
incorrectly, all mutations are enabled in production.

**Preconditions**: Configuration error or environment variable misconfiguration
causing `is_production` to return false in a production environment.

**Impact**: Off-chain mutations (reservations, settlements, wallet bindings) would
be enabled in production, potentially allowing unauthorized state changes.

**Evidence**: All mutation functions call `require_local_control_plane()` as their
first statement.

**Recommendation**: Add defense-in-depth: secondary environment checks,
database-level guards, or deployment-time assertions.

---

### F-10: Issuer Cannot Be Rotated in AgoraAgentIdentity

| Field | Value |
|-------|-------|
| **ID** | F-10 |
| **Severity** | LOW |
| **Component** | `AgoraAgentIdentity.sol` line 19 |
| **Status** | CONFIRMED |

**Description**: The `issuer` address is immutable. Same pattern as F-06 but for
identity minting. If the issuer key is lost, no new identities can be minted.
If compromised, an attacker can mint arbitrary identities (but cannot transfer them).

**Preconditions**: Key loss or compromise of the issuer.

**Impact**: Key loss: no new identities. Key compromise: arbitrary identity minting
(but tokens are soulbound, limiting damage).

**Recommendation**: Mitigated by SAFE_2_OF_3. Acceptable for testnet.

---

## PHASE 3: TEST RESULTS

### 3.1 Commands Executed

| # | Command | Result | Duration |
|---|---------|--------|----------|
| 1 | `npm ci` | 73 packages, 0 vulnerabilities | ~1s |
| 2 | `npx hardhat clean && npm run compile` | 4 files compiled (solc 0.8.30, cancun) | ~5s |
| 3 | `npm run test:contracts` | PASS (13 invariants) | ~15s |
| 4 | `npm run test:preflight` | PASS (6/6 tests) | ~48ms |
| 5 | `npm run test:bundle` | PASS (8/8 tests) | ~135ms |
| 6 | `npm run audit:static` | PASS (3 contracts, no forbidden patterns) | ~50ms |
| 7 | `npm run bundle:verify` | PASS (bundle_sha256 match) | ~100ms |
| 8 | `npm audit --audit-level=high` | 0 vulnerabilities | ~1s |

**Total: 27 tests passed, 0 failed, 13 invariants verified.**

### 3.2 Invariants Verified (On-Chain Tests)

1. `fixed_supply` -- Total supply is exactly 100,000,000,000,000 aceros
2. `eight_decimals` -- Token has exactly 8 decimals
3. `authority_only_settlement` -- Only settlement authority can publish
4. `immutable_challenge_root` -- Cannot overwrite published settlement
5. `invalid_proof_rejected` -- Invalid Merkle proofs are rejected
6. `claim_replay_rejected` -- Double claims are rejected
7. `claim_cross_deployment_replay_rejected` -- Cross-contract replay rejected
8. `multi_leaf_settlement_bundle_compatible` -- Multi-account settlements work
9. `settlement_overcommit_rejected` -- Over-reservation rejected
10. `reward_transfer_does_not_mint` -- Claims transfer, don't mint
11. `agent_identity_unique` -- Duplicate identity minting rejected
12. `agent_identity_non_transferable` -- Transfer reverts Soulbound
13. `agent_identity_revocable_without_erasure` -- Revocation preserves token

### 3.3 Coverage Gaps Identified

- No fuzz testing of Merkle proof edge cases
- No test for zero-amount claim (F-02)
- No test for duplicate revocation (F-04)
- No test for `_safeMint` callback reentrancy in `AgoraAgentIdentity.mint()`
- No test for ERC-20 `approve` + `transferFrom` flow with TokoinFixedSupply
- No gas limit stress test for large Merkle trees

### 3.4 npm Audit
```
found 0 vulnerabilities
```

---

## PHASE 4: CONTROL PLANE AND API REVIEW

### 4.1 Authentication

| Check | Result |
|-------|--------|
| Device session tokens (opaque, SHA-256 hashed) | CONFIRMED |
| Session expiration (TTL-based) | CONFIRMED |
| Revocation enforcement (immediate) | CONFIRMED |
| Fail-closed (no dev bypass tokens) | CONFIRMED |
| HttpOnly cookies for owner session | CONFIRMED |

### 4.2 CSRF Protection

| Check | Result |
|-------|--------|
| Per-session CSRF tokens | CONFIRMED |
| X-CSRF-Token header required for mutations | CONFIRMED |
| Constant-time comparison | CONFIRMED |

### 4.3 Security Headers

| Header | Value | Status |
|--------|-------|--------|
| X-Content-Type-Options | nosniff | PRESENT |
| X-Frame-Options | DENY | PRESENT |
| Referrer-Policy | no-referrer | PRESENT |
| Cache-Control | no-store | PRESENT |
| Strict-Transport-Security | -- | ABSENT (assumed at load balancer) |

### 4.4 Separation Between Agent and Owner

- Owner endpoints require browser session + CSRF
- Device endpoints use opaque Bearer tokens
- `MutatingOwner` dependency enforces browser authentication for state changes
- `require_local_control_plane()` blocks all mutations in production

### 4.5 Idempotency

| Endpoint | Mechanism | Status |
|----------|-----------|--------|
| Reservations | `idempotency_key` unique constraint | CONFIRMED |
| Settlement Plans | `challenge_id` uniqueness | CONFIRMED |
| Wallet Bindings | `agent_id + chain_id` uniqueness | CONFIRMED |
| Knowledge Root Anchors | `merkle_batch_id` uniqueness | CONFIRMED |

### 4.6 Settlement Plan Integrity

- Resolution receipt binding (challenge_id match, accepted + RESOLVED_VERIFIED)
- Role cap validation (100M aceros max per settlement)
- Shared controller rejection (independent_replication vs review_and_adjudication)
- Wallet binding verification (agent_id consistency)

### 4.7 Secret Exposure

- No private keys stored in application
- No secrets in API responses
- Session tokens hashed before storage
- `.env.example` contains only placeholder values

### 4.8 Internal Balance to EVM Token Conversion

- `require_local_control_plane()` prevents all mutations in production
- Off-chain ledger is separate from on-chain state
- No automated bridge from internal balances to EVM tokens
- Settlement publication requires separate multisig authorization

---

## PHASE 5: THREAT MODEL

### 5.1 Compromise of Settlement Authority
- **Risk**: HIGH
- **Mitigation**: SAFE_2_OF_3 multisig required at deployment gate
- **Residual**: If 2-of-3 signers collude, arbitrary settlements can drain all unreserved TOKOIN
- **Testnet Impact**: Loss of testnet tokens only (no economic value)

### 5.2 Compromise of Treasury
- **Risk**: HIGH
- **Mitigation**: SAFE_2_OF_3 multisig, immutable in contract
- **Residual**: Treasury holds initial supply. If compromised before funding rewards contract, all tokens at risk
- **Testnet Impact**: Loss of testnet tokens only

### 5.3 Compromise of Identity Issuer
- **Risk**: MEDIUM
- **Mitigation**: SAFE_2_OF_3 multisig
- **Residual**: Can mint arbitrary soulbound identities. Cannot transfer or steal existing ones
- **Testnet Impact**: Fake identities on testnet

### 5.4 Auditor Malicioso (Malicious Auditor)
- **Risk**: MEDIUM
- **Mitigation**: Audit report hash bound to authorization and preflight gates
- **Residual**: Auditor could falsely approve a flawed candidate. Preflight requires additional authorization steps
- **Defense**: Multiple authorization layers (audit + authorization + multisig + deploy ACK)

### 5.5 Bundle Substituted After Audit
- **Risk**: HIGH
- **Mitigation**: `bundle_sha256` integrity binding, `bundle:verify` recompilation check
- **Defense**: Authorization binds `contract_release_bundle_hash`, audit binds same hash.
  Substituting the bundle requires forging both audit and authorization files

### 5.6 Deployer Comprometido (Compromised Deployer)
- **Risk**: MEDIUM
- **Mitigation**: Preflight gates validate bundle, audit, authorization, and multisig attestations
- **Residual**: Deployer with valid authorization can deploy. Post-deployment verification confirms bytecode matches

### 5.7 RPC Malicioso (Malicious RPC)
- **Risk**: MEDIUM
- **Impact**: Could provide false transaction receipts, block numbers, or chain state
- **Mitigation**: Post-deployment verification script checks deployed bytecode
- **Residual**: Deployment could appear successful but be on wrong network

### 5.8 Proof Replay
- **Risk**: LOW (after domain separation)
- **Mitigation**: Claim leaf includes `block.chainid` and `address(this)`
- **Residual**: Not exploitable across contracts or chains. Test confirms invariant

### 5.9 Sybil Attacks
- **Risk**: MEDIUM
- **Mitigation**: Identity uniqueness per `agentIdentityHash`, off-chain research adjudication
- **Residual**: Sybil at the off-chain research level (creating fake research contributions)
  is outside contract scope

### 5.10 Censorship
- **Risk**: LOW
- **Mitigation**: Base Sepolia is a public testnet
- **Residual**: Block producers could censor transactions but cannot steal funds

### 5.11 Loss of Keys
- **Risk**: MEDIUM
- **Impact**: Immutable authority addresses mean loss = permanent inability to publish/mint
- **Mitigation**: SAFE_2_OF_3 reduces single-key-loss risk
- **Recovery**: Requires new contract deployment and fund migration

### 5.12 Forks and Reorganizations
- **Risk**: LOW (testnet)
- **Mitigation**: Deployment script waits for 2 block confirmations
- **Residual**: Deep reorgs could undo deployments or claims. Testnet-acceptable risk

### 5.13 Centralización Operativa (Operational Centralization)
- **Risk**: MEDIUM
- **Observation**: Three immutable authority addresses (treasury, settlement, issuer) control
  all privileged operations. Preflight requires distinct addresses, but the same entity
  could control multiple Safe multisigs
- **Mitigation**: SAFE_2_OF_3 with distinct addresses enforced at deployment

### 5.14 Dependencia de Base/Ethereum
- **Risk**: LOW
- **Impact**: If Base Sepolia goes offline, contracts are inaccessible
- **Mitigation**: Testnet-only deployment, no economic value at risk

### 5.15 Discrepancias Ledger Interno vs ERC-20
- **Risk**: MEDIUM
- **Observation**: Off-chain ledger (TokoinLedgerEntry) tracks balances independently of
  on-chain ERC-20 state. These can diverge
- **Mitigation**: `require_local_control_plane()` blocks production mutations. Settlement
  publication is the only bridge to on-chain state
- **Residual**: Off-chain ledger could show balances that don't match on-chain reality

---

## FINDINGS SUMMARY

| ID | Severity | Component | Title | Status |
|----|----------|-----------|-------|--------|
| F-01 | MEDIUM | TokoinResearchRewards | Unclaimed settlement funds locked permanently | CONFIRMED |
| F-02 | LOW | TokoinResearchRewards | Zero-amount claim not rejected at contract level | CONFIRMED |
| F-03 | MEDIUM | TokoinResearchRewards | No emergency pause or root correction mechanism | CONFIRMED |
| F-04 | INFORMATIONAL | AgoraAgentIdentity | Duplicate revocation emits redundant events | CONFIRMED |
| F-05 | LOW | TokoinResearchRewards | Permissionless claim allows third-party forcing | CONFIRMED |
| F-06 | LOW | TokoinResearchRewards | Settlement authority single point of trust | CONFIRMED |
| F-07 | INFORMATIONAL | AgoraAgentIdentity | No tokenURI implementation | CONFIRMED |
| F-08 | MEDIUM | Control Plane API | Off-chain authorization gaps | SUSPECTED |
| F-09 | LOW | Control Plane API | Production guard single point of failure | CONFIRMED |
| F-10 | LOW | AgoraAgentIdentity | Issuer cannot be rotated | CONFIRMED |

**Totals: 0 CRITICAL, 0 HIGH, 3 MEDIUM, 5 LOW, 2 INFORMATIONAL**

---

## DECISION

### **READY_FOR_HUMAN_EXTERNAL_AUDIT**

The TOKOIN release candidate demonstrates disciplined minimal design with no critical
or high severity vulnerabilities in the on-chain contracts. The medium findings are
acceptable for a controlled testnet trial but should be evaluated by a human external
auditor before any consideration of broader deployment.

---

## MANDATORY HUMAN EXTERNAL AUDITOR REVIEW ITEMS

A human external auditor **must** independently verify:

1. **Merkle proof construction correctness** -- Verify that the off-chain
   `buildSettlementBundle()` produces trees compatible with on-chain
   `MerkleProof.verifyCalldata()` under all edge cases (single leaf, power-of-2,
   non-power-of-2, maximum depth)

2. **Domain separation completeness** -- Confirm that `claimLeaf()` parameters
   are sufficient to prevent all cross-context replay scenarios

3. **ERC-721 soulbound enforcement** -- Verify that no ERC-721 transfer path
   bypasses the `_update()` override (including `safeTransferFrom` variants)

4. **OpenZeppelin 5.6.1 dependency** -- Verify no known vulnerabilities in the
   specific OZ version used

5. **Solidity 0.8.30 compiler** -- Verify no known compiler bugs affecting the
   generated bytecode

6. **Gas analysis** -- Profile worst-case gas costs for `claim()` with maximum
   Merkle proof depth

7. **Unclaimed fund recovery policy** -- Evaluate F-01 and decide whether a
   recovery mechanism is needed for testnet

8. **Off-chain to on-chain boundary** -- Verify that the `require_local_control_plane()`
   guard is sufficient and cannot be bypassed

9. **Multisig governance model** -- Verify that the SAFE_2_OF_3 requirement
   adequately distributes trust for the three authority roles

10. **Fuzz testing** -- Conduct property-based fuzz testing of all contract
    entry points

---

## LIMITATIONS OF THIS AUDIT

1. This is an AI-generated review, not an independent human audit
2. No formal verification was performed
3. No fuzz testing was conducted
4. No live network testing was performed (all tests ran on hardhatOp simulator)
5. Gas profiling was not performed
6. The API control plane analysis was based on code review, not runtime testing
7. The auditor cannot verify runtime behavior of external dependencies (OpenZeppelin, Hardhat, solc)
8. The auditor has no access to the Safe multisig configuration or signer identities
9. This review does not constitute legal, financial, or regulatory advice
10. The `SUSPECTED` status on F-08 indicates code review without runtime reproduction

---

*Report generated: 2026-09-06*
*Auditor: Claude Opus 4.6 (AI Internal Technical Review)*
*Commit: 001e202aee63b991d22ead591580584c6341f0c0*
