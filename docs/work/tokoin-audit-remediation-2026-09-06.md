# TOKOIN audit remediation verification

Recorded: 2026-09-07T04:19:41Z

## Candidate identity

- Prior internally reviewed commit: `001e202`
- Prior bundle: `f283883379dffaa6cbe8b6498957b40a54f6283735e3c8f0b90395c836d165a5`
- New undeployed bundle: `3043f6345d00e3ff3da777f9094283789f6af661f4af8453869fbf8e8f8fc4db`
- Network authorized by this work: none
- Value moved: none

The Claude-assisted internal audit is retained as historical evidence for the
prior candidate. It does not approve this new candidate and does not satisfy the
independent human audit gate.

## Finding disposition

| Finding | Disposition |
| --- | --- |
| F-01 unclaimed funds lock | Fixed with bounded deadlines and permissionless expired-reserve release. |
| F-02 zero claim | Fixed with contract-level `ZeroAmount`. |
| F-03 no emergency control | Fixed narrowly: claim pause plus pre-claim cancellation; roots cannot be rewritten. |
| F-04 duplicate revocation | Fixed with `IdentityAlreadyRevoked`. |
| F-05 permissionless claim | Accepted design: proof-bound payment always goes to the leaf account. |
| F-06 immutable authority | Accepted with mandatory 2-of-3 Safe; Safe signers can rotate. |
| F-07 no tokenURI | Deferred; signed AGORA Agent profiles remain canonical metadata. |
| F-08 API authorization | Fixed with explicit local enablement, Owner/CSRF/rate limit and reservation-operator binding. |
| F-09 production guard SPOF | Strengthened with default-off config, production hard deny, route/service checks and independent preflight inputs. |
| F-10 immutable issuer | Accepted with a distinct mandatory 2-of-3 Safe and signer rotation inside Safe. |

## Verification evidence

- Isolated Python regression from migration zero: `471 passed, 1 skipped`.
- Focused TOKOIN API/security suite: `32 passed` before final full regression.
- Contract script: 21 invariants passed.
- Merkle properties: deterministic proofs at 1, 2, 3, 5, 17, 64, 257 and
  1024 leaves; tampered proofs rejected.
- Observed 1024-leaf-tree claim: 107,843 gas, 10 proof nodes on Hardhat.
- Release preflight: 6 tests passed; actual preflight remains blocked.
- Bundle/property/verifier: 9 tests passed.
- Ruff, mypy, TypeScript, ESLint and Next production build passed.
- `pip-audit` and both npm audits reported no known vulnerabilities.

## Remaining release gates

1. Independent human smart-contract audit of the exact new bundle.
2. Explicit auditor independence disclosure accepted by the operator.
3. Human decision on every medium/low disposition above.
4. Three distinct operational 2-of-3 Safe addresses for treasury, settlement
   authority and identity issuer.
5. Hash-bound Base Sepolia authorization for the final commit, audit report,
   bundle and capped test ETH budget.
6. Controlled no-value Base Sepolia deployment and read-only receipt verification.

Until these are complete, status is **internally validated, not deployable**.
