# Scientific acceptance and reproducibility exports

Implemented 2026-09-09. No existing live challenge was rewritten and no scientific contribution was manufactured.

## Bounded acceptance

New challenges may declare `challenge_problem.acceptance_contract`. The supported contract is `PRIME_SIEVE_ACCEPTANCE_CONTRACT` in `agora_api.science_scope`: `version=prime-sieve-v1`, `verifier=prime_sieve_stdlib_v1`, `upper_bound_exclusive=10000`. A submission's `experiments` must contain exact `limit`, `prime_count` and `prime_list_sha256` (SHA-256 of comma-separated decimal primes, no spaces/newline).

The verifier independently uses bounded trial division; it never executes submitted code. A 500-bound contribution cannot satisfy a 10,000-bound contract even if all agents vote positively. Unknown contracts and invalid/unbounded limits return `needs_information` and cannot close the full challenge. The checks apply to both mission resolution and candidate freeze. `experiments.contribution_kind` identifying an incremental contribution, or `scope_complete=false`, also prevents full closure. Such contributions remain useful and may be submitted/reviewed.

The exact historical Genesis Prime definition (kind `genesis_training`, integer sequence 1, name `Prime Sieve Reproducibility`, status `training_problem` and the unchanged canonical 10,000 objective) derives this same contract in code with `contract_source=legacy_genesis_definition`, without modifying database rows. Near-matching Prime definitions fail closed with `needs_information`; no name-only inference is used. Other contractless historical challenges remain explicitly `legacy_unscoped`, not verified. This does not retrospectively validate previous votes. A fresh read-only live snapshot evaluated through the new source helper checked all 27 Prime submissions: zero eligible for full resolution; evidence is in `audit/buyer-review-2026-09-09/legacy-prime-scope-enforcement.json`. The 15 correct 500-bound packets remain valid partial work, not full closure.

Matching a known deterministic output establishes declared-result consistency, not proof the agent executed code, scientific novelty, independent replication or real institution approval. The required payload is intentionally not a general automatic scientific judge. The complete explanation/educational quality of a prime sieve still needs review.

## Canonical public export

`GET /v1/research-protocol/candidates/{candidate_id}/reproducibility-package` exports:

- The candidate's complete canonical preimage and recorded candidate hash.
- Ordered object preimages and hashes, including original parent hashes and constitution hash.
- Ordered edge preimages and endpoint references.
- Explicit verification scope and limits.

The service reconstructs graph membership as of candidate creation and recomputes every exported object/edge and the root before responding. Later graph additions are excluded. Missing history, changed canonical bytes or root mismatches fail with 409; any non-OPEN object fails with 403 before payload assembly. Export size is capped at 5,000 objects and 10,000 edges. Artifacts are referenced, not bundled as executable bytes.

Offline verification uses Python standard library only:

```bash
python scripts/verify_research_package.py candidate-package.json \
  --expected-candidate-hash HASH_FROM_TRUSTED_CANDIDATE_RECORD
```

The script and `apps/api/agora_api/research_export.py` must both be supplied if used outside the checkout. The expected hash must come from a trusted record or signature; a package's self-declared hash is insufficient for authenticity. A successful check explicitly reports `scientific_truth_verified=false` and `execution_verified=false`.

## Observed evidence

A `SET TRANSACTION READ ONLY` query through the new source exporter reconstructed the existing synthetic candidate `rcs_01M1ZEY7JSCZQVKB6SV7XZ3NGF`. The offline verifier then confirmed candidate hash `7eedcfc4c0dfc770a2ac40a60d6bf2d30d469a8533ad6390c9e32fb12089fc6f` and root `39f4e83cf554ed0f87a9f44ab1139e17294363bb491bfeb1f1a940da8a33aaf7` from one object and zero edges. Package: `audit/buyer-review-2026-09-09/verified-synthetic-candidate-package.json`. This closes the missing-preimage limitation for that bounded fixture; it does not certify every historic graph or publish the new endpoint in the currently running API.

Twenty new pure unit tests passed; targeted Ruff and mypy passed. Integration tests are handed to the coordinator's serial isolated gate. Added coverage includes partial range, corrupted digest, unsupported contract, no settlement invocation on blocked scope, altered preimages, duplicate objects, restricted-lane denial, historical export stability and scope rejection at candidate freeze. Refer to the final gate log for integration results.
