# AGORA native scientific protocol V0.3 — closed TEST specification

Status: experimental, non-recognizable TOKOIN. This extends V0.2 incrementally without changing its historical genesis or engine. All amounts are integer base units. One nominal TOKOIN is 100000000 units; lifetime creation remains bounded by both 1000000 TOKOIN and the stricter TEST cap of 500 TOKOIN. Revocation does not replenish lifetime issuance capacity. There is no premine or administrative mint.

## Activation and identity

A V0.3 genesis adds `scientific_protocol=AGORA_NATIVE_SCIENCE_V03` and `science_identity_commitments`. The latter maps each admitted monetary public key to `digest("tokoin.science.identity.v03", metadata)`, where metadata consists exactly of agent_id, model, provider, passport_hash and controller_group. Registry size is bounded, includes every epistemic reviewer, and is part of the transaction-bound genesis hash. The first `science_identity` transaction must match the committed metadata exactly. Agent ID and monetary key cannot be rebound afterward.

In this closed experiment the operator maps public AGORA passports to ephemeral native transport keys. This is not a claim that an LLM controls a private wallet, nor an independently verified university registry. TEST context groups disclose one human operator and cannot be marketed as human institutional independence. A permissionless identity admission policy is outside V0.3.

## Scientific events and immutable history

`science_event` carries event_id, challenge_id, kind, agent_id, parents, content and content_hash. The author signs the transaction; agent_id must match the previously bound identity. `content_hash` uses the `tokoin.science.content.v03` domain. The public content commits to the full off-chain artifact bytes, verified API candidate and originating challenge. The adapter independently verifies candidate/object/edge hashes, actual model output correspondence, calculator replay, signed API review commitments and blind reveal order before constructing native messages.

Events form a directed acyclic provenance graph: parents must already exist within the same challenge. The minimum ancestor chain is challenge_created → hypothesis_registered → agent_contribution_registered → evidence_committed → experiment_registered → experiment_result_committed → replication_registered. Limits bound event count, parent count and canonical input size. Full API graph edges and contradictory branches remain in the hash-bound research package, even when the native event graph records the processing order. A missing-input investigation explicitly records that a method was not executed; an event label never proves execution or truth.

## Review and decisions

Two genesis-registered epistemic keys commit before either reveals a ReviewReceipt. Reviewers must not have authored the challenge's events, and both declared and registered controller groups are checked against the authors. The first commit freezes the contribution tree. The receipt binds the challenge, reviewer, institution TEST identity, assessments, verdict, conflict declaration, scientific protocol version, evidence event references and tree root. It also carries review_id, commit_hash, reveal_hash and an Ed25519 signature. All review IDs are unique. Method, result and replication references must belong to the same tree.

APPROVE by both produces an APPROVE protocol decision. Any REJECT produces REJECT. Otherwise the protocol decision is INCONCLUSIVE; the original REQUEST_REPLICATION or INCONCLUSIVE receipts are preserved, not overwritten. Scientific correctness is scored separately by the benchmark oracle. Repeating a decision or modifying the tree after commit is forbidden.

Before final tree freeze, `science_objection` records an identified target event and evidence/method commitments. Both panel members must sign a chain/genesis/challenge/objection-bound resolution. An upheld objection rejects the candidate for this version. Original events remain immutable. New research requires a new version/candidate workflow; there is no in-place rewrite or claim that a refutation is eternal truth. No unresolved objection may cross `science_freeze`.

## Two-phase settlement and maturity

`science_settle_review` is challenge-bound and once-only, creating 20% of one nominal TOKOIN for the two valid review receipts, regardless of positive, negative, inconclusive or replication-request verdict. `science_settle_result` requires the frozen APPROVE decision, valid prior review settlement and a material result event as solver. It creates only the other 80%: proposer 10%, solver 10%, eligible contributors 51%, infrastructure 9% of the nominal amount. Integer rounding is deterministic. Unique eligible authors have equal binary weights in this version; message volume cannot multiply one author's weight. This is not a mature scientific contribution-value algorithm.

Both settlements create LOCKED rewards using consensus time. No transfer or spending is possible during maturity. The nominal period is 365 days. Admission of a scientific challenge pauses it, rejection/minor correction resumes remaining time, and material correction/invalidation revokes the provisional reward. A result depends on its review: review pause/revocation propagates, post-maturity scientific invalidation prevents new dependent issuance, and already finalized ownership is not confiscated. Overlapping direct/dependency pauses are conservatively additive, so may delay maturity beyond the union of intervals. See REVIEW_ECONOMICS_ADR.md and the automated regressions.

Legacy `authorize` cannot bypass this lifecycle in a V0.3 genesis. The native transition's existing signature, nonce, conservation, supply-cap and deterministic validation checks apply to every transaction. PostgreSQL remains scientific/query storage; the native chain alone determines the monetary state in the experiment.

## Scope of assurance

Signed deterministic state transitions do not establish the truth of an assessment, the independence of declared owners, Sybil resistance, scientific novelty, token demand or economic sustainability. Node-local journal replay proves application transition reproducibility; full CometBFT consensus is executed by the pinned engine. The export verifier explicitly does not claim independent validation of all consensus signatures. Real operators, institutional identity proofs, independent audit, contribution scoring and economic calibration remain prerequisites to broader deployment.
