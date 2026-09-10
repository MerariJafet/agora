# Separating scientific review from monetary consensus: a local adversarial evaluation of AGORA/TOKOIN

**Internal draft — not submitted, not independently peer reviewed.** Human authorship, accountability, related-work review, licensing and disclosure decisions remain open. Quantitative results must be read together with RELEASE_MANIFEST.json and the final results report.

## Abstract

AGORA/TOKOIN explores a separation between scientific provenance and monetary settlement. AGORA records contributions, experiments and reviews; a deterministic application enforces signed authorizations, monetary caps and delayed transferability over an existing BFT engine. We evaluate an isolated TEST implementation through malformed transactions, monetary state sequences, process interruption, network partitions and scripted scientific workflows. The evaluation supports bounded claims about local deterministic execution and tested failure recovery. It does not establish scientific truth, real institutional adoption, economic value, permissionless security or readiness for mainnet.

## Architecture and method

The prototype uses the unmodified CometBFT 0.38.26 engine with a Python ABCI application. CometBFT supplies BFT state-machine replication; this work does not introduce a new consensus algorithm. See the [official CometBFT documentation](https://docs.cosmos.network/cometbft/latest/docs/README) and the pinned source commit in the release manifest.

Consensus validators order transactions, while epistemic validators sign review commitments and verdicts. TEST institutional identities are explicitly synthetic. A signed transaction commits to its protocol version, chain, genesis, sender, nonce and payload. Monetary values use integer atomic units. The protocol caps cumulative creation at one million TOKOIN and TEST issuance at 500, with zero premine. Revocation does not replenish already consumed issuance capacity.

Approved TEST rewards enter a locked state. A 365-day duration is expressed using consensus-derived timestamps, with a persisted unlock threshold. An admitted challenge pauses maturation; a material revision requires a new candidate and review. Post-maturity scientific invalidation records new evidence without confiscating transferred balances. These are rules of the prototype, not claims of permanent scientific truth.

## Evaluation

The evaluation uses one physical PC. Four local validator processes and separate applications exercise quorum loss, partitions, invalid proposals and recovery. Additional process controls and isolated network namespaces inject faults without changing the host's global clock or networking. A duplicate-vote experiment produces verifiable conflicting signatures and checks evidence inclusion in a block.

A seeded monetary corpus contains 100,000 sequences and 400,000 signed transition attempts per execution. Accepted operations and expected rejections are distinguished. Repeated executions use the same corpus and therefore are reproducibility checks rather than independent additional samples. Separate tests exercise boundary amounts, interrupted persistence, wallet corruption and malformed inputs.

Six scripted scientific scenarios traverse an isolated AGORA API, blind review commitments and provenance exports. Computation runs in Python workers, not autonomous language-model researchers. Two supported cases produce TEST authorizations; four negative or insufficient cases reject issuance. The bridge is tested at the native application layer with simulated maturation, not a real year of network operation.

## Results and artifact policy

The consolidated report and manifests provide exact versions, hashes, seeds, outcomes and limitations. Failed harness executions are preserved rather than replaced by successful reruns. The local hardening identified and repaired cross-genesis replay, journal-tail truncation acceptance, wallet workflow defects and path-dependent test-helper builds. Broad API regression testing also exposed and corrected test-state isolation defects.

The frozen native source is evaluated from a clean repository copy with a new Python environment. Reproducible engine/helper builds remain same-machine evidence. Public artifacts exclude private node homes and do not confer economic recognition on TEST balances.

## Limitations and open research questions

Four processes are not four independent operators. Modified vote timestamps do not constitute full validator clock virtualization. The review registry does not authenticate real universities. Similarity and common-owner signals support review but do not solve plagiarism, Sybil attacks or hidden collusion. Compensation for rigorous negative reviews independent of approval remains unresolved under the frozen economic policy.

Scientific workflows have not demonstrated autonomous research quality or broad factual reliability. Monetary scarcity does not establish demand or sustainable incentives. Admission governance, censorship resistance, external security review and economics after scientific invalidation require further work. No novelty or legal-priority claim follows from this draft.

## Reproduction and next validation

The accompanying reproduction guide identifies the frozen source, dependency versions, build procedure, corpus command and isolated API wrapper. A subsequent external study should require independently generated validator keys, separate administrative domains, repeated fault tests and accountable human review. Publication claims must remain limited to demonstrated properties until that evidence exists.
