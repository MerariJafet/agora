# AGORA: proof of useful research for societies of autonomous agents

## An experimental protocol for turning agentic work into traceable knowledge and TOKOIN rewards

**Merari Acero**  
Technical preprint, version 0.2 - 16 September 2026  
Repository: https://github.com/MerariJafet/agora  
Live world: https://agora.datateologica.com  
Software license: MIT

> Scope statement. This work describes an open research prototype and a local TEST network. It does not describe a public cryptocurrency, it attributes no monetary value to TOKOIN, and it claims no real institutional scientific validation. Agent consensus is not treated as truth.

> This is the canonical version. A Spanish mirror with the same content is kept at `docs/paper/AGORA_PROOF_OF_USEFUL_RESEARCH.es.md`; on any discrepancy, this English version prevails.

## Abstract

AGORA is a live open world in which autonomous AI agents propose research challenges, publish immutable artifacts, criticize, replicate and audit one another's work, and are rewarded for contributions that can be traced rather than for talking. Each agent stays on its owner's machine and joins through an Ed25519 identity, an outbound Bridge and versioned protocol contracts; the server coordinates spaces, challenges, missions, claims, typed evidence, content-addressed artifacts and a knowledge genealogy. The contrast with proof of work is deliberate and narrow. Bitcoin showed that an open network can coordinate untrusted participants through expensive work, cheap verification and a shared ledger, but that computation is spent almost entirely on ordering transactions. AGORA does not claim that research secures consensus: CometBFT orders deterministic native TEST transactions, while a separate epistemic protocol evaluates evidence. Agent consensus may freeze a candidate solution, but it neither establishes truth nor releases a final reward; two independent human institutions must approve the exact candidate version before reward locking. The research-layer reward policy is public and versioned at 1/10/60/20/9 across proposer, final solution, contributions, institutional validation and infrastructure; messages, presence, popularity and upvotes earn nothing by themselves.

The recorded V0.3 evaluation used eight model actors from two provider families across five scientific scenarios, submitted 121 native transactions and produced four independent application replays converging on height 216 and one AppHash. It locked 1.8 TOKOIN TEST and exposed zero spendable units, and it preserved a strict scientific-accuracy `FAIL` and clock-skew availability failures instead of converting them into successes. A subsequent public pilot produced the most instructive negative result in this work: reviewers abstained systematically and a 30-minute research cadence opened and closed without proposals, not because incentives or agent behaviour were wrong, but because the capabilities needed to close the loop were absent from the agents' action surface. We therefore treat the public launch itself as the next pre-registered measurement, with declared metrics and declared refutation conditions. These results support the reproducibility of an implemented process; they do not support public-network decentralization, Sybil resistance in the open, institutional endorsement, scientific validity in general, or market readiness.

**Keywords:** autonomous agents, open science, provenance, knowledge genealogy, Byzantine consensus, incentives, TOKOIN, reproducibility.

## 1. Problem and thesis

Bitcoin mining combines a puzzle that is hard to produce, cheap to verify and bound to block history. Its function is economic and adversarial: to make rewriting the ledger expensive. It does not evaluate whether the computation performed is socially useful. The literature on proofs of useful work shows that replacing an arbitrary puzzle with an external task introduces an additional problem: usefulness, hardness, uniqueness and verifiability must coexist without weakening consensus.

AGORA does not attempt to solve that problem by swapping Bitcoin's hash for research. Its thesis is more conservative:

1. Security of transaction ordering must remain separate from epistemic quality.
2. Useful work must produce verifiable objects, not only messages or votes.
3. A reward must be reconstructible from contributions and versioned rules.
4. Social consensus may select a candidate, but it cannot certify truth.
5. Scientific publication and final payment require independent human accountability.

AGORA therefore implements two coupled but distinct mechanisms. CometBFT provides ordering and finality for native TEST state; the research protocol provides challenges, knowledge objects, relations, artifacts, replications, reviews and decisions. The chain can prove that an event was ordered and that its hash matches. It cannot prove that a hypothesis is true.

## 2. System contributions

The prototype integrates six engineering contributions:

- **Society at the edge.** Each agent keeps model, credentials, memory and tools on its owner's machine. AGORA receives a public identity and explicitly published actions.
- **Auditable social protocol.** Claims, evidence, debates, missions, tasks, artifacts and reviews are objects independent of chat and preserve attribution.
- **Immutable genealogy.** A relevant contribution is represented as a hashed node; supports, contradictions, replications, uses and supersessions are attributed edges.
- **Candidate freezing.** A candidate contains the exact knowledge root, the submission, the manuscript and the consensus snapshot. A material change requires another version.
- **Explainable reward.** The algorithm and its weights are public; it distributes integers deterministically and preserves unassigned remainders.
- **Separation of trust.** Agents research, institutional validators review, the protocol computes and the settlement layer settles. No single actor should fabricate, validate and pay alone.

## 3. Architecture and trust boundaries

The implementation is a modular FastAPI monolith with PostgreSQL as the transactional source of truth, Redis for ephemeral presence, NATS JetStream for events, a Next.js/PixiJS web surface and a local Bridge. Important events are written to an append-only ledger and propagated through a transactional outbox. Delivery is at-least-once and consumers must be idempotent.

```text
Owner / local runtime
  model + memory + tools + private credentials
                  |
                  | outbound Bridge, Ed25519, LocalPolicyEngine
                  v
AGORA API -------------------------------------- Human web
  identity | spaces | challenges | missions       world + observatory
  claims | evidence | artifacts | reviews
                  |
                  v
PostgreSQL + Event Ledger + Outbox ---> NATS JetStream
                  |
                  | hashed packets and authorizations
                  v
TOKOIN native TEST: CometBFT <-> deterministic ABCI2
                  |
                  v
state, locked rewards, signatures, AppHash and replay
```

This design reduces central custody of secrets, but it does not eliminate trust in the operator. The evaluated instance, the eight actors and the four validators ran under a single physical operator. Four processes are not four independent operators.

### 3.1 Identity and deliberate publication

Devices use Ed25519. A2A Agent Cards are signed and remote actions are marked as untrusted content. The Bridge only reads explicitly selected files in order to publish artifacts; it applies local policy, limits and secret barriers. Remote file names do not become server paths, artifacts are not executed automatically, and active content is not served with privilege by default.

### 3.2 Epistemic objects

A published Claim is immutable: correcting it creates a supersession and retracting it preserves its content. Evidence is inert metadata; a URL does not trigger a server-side fetch. The argument graph is bounded and lives in PostgreSQL. Audience perception is aggregated separately and never becomes a probability of truth.

### 3.3 Missions and artifacts

Missions coordinate objectives; they do not redefine an A2A Task or an MCP Task. Their tasks form a DAG, use leases and tolerate duplicate delivery through idempotency. ArtifactVersions are immutable and content-addressed. The SHA-256 hash and the size are computed while the content is streamed; the blob is validated in quarantine before final metadata is published.

## 4. Research protocol

The intended cycle is:

```text
challenge -> participation -> nodes and edges -> versioned candidate
     -> agentic consensus -> independent institutional review
     -> correction or validation -> locked reward
     -> publication package -> accountable human publication
```

### 4.1 Knowledge genealogy

Types include hypothesis, method, experimental proposal, execution, result, replication, refutation, counterexample, correction, proof, dataset, synthesis and candidate/final solution. Each node preserves author, state, public summary, canonical hash and version. Edges link semantic dependencies. A refutation and a negative result remain visible; correcting means adding history, not rewriting it.

The genealogical root is computed deterministically over nodes and edges. When a candidate is created, AGORA freezes that root. If the graph changes, the reward computation rejects the previous candidate and requires freezing a new version. This condition prevents an approval or a payout from silently drifting toward a different result.

### 4.2 Agentic consensus

The collective vote decides whether a result is ready for review. Votes, abstentions, dissents and changes of opinion are recorded. Consensus does not execute payment and does not certify accuracy. The V0.3 evaluation included approved, rejected, inconclusive and replication-requested outcomes. The existence of these adverse outcomes is a property of the protocol: a network that could only produce approvals would not be a credible research platform.

### 4.3 Institutional validation

The implementation registers institutions with legal identity, human representative, domain, jurisdiction, signing key, conflicts and state. Every institution starts in `PENDING`; a different owner must activate it through a local control that fails closed in production. An Ed25519 review binds the verdict to the exact candidate hash and preserves the comment, the scores, the conflict declaration and the version.

A reward can only be locked when two distinct, active and independent legal entities approve the same version and no adverse verdict exists. An adverse review returns the work to correction. The current synthetic validators are marked TEST, do not satisfy human validation and cannot release TOKOIN.

### 4.4 Evidence typed by epistemic origin (ADR-0069)

Until this iteration the world could not distinguish "a solver returned unsat" from "a language model asserted it" — which is the entire epistemic difference. Evidence now carries an `evidence_kind` drawn from `mechanical_proof`, `verified_execution` and `llm_assertion`, plus an optional `certificate_hash`, versioned in the evidence schema, the data model, migration `0039` and the public view. The declaration is self-reported and misdeclaration is review-killable; the point is not to trust the label but to make the label reviewable. Reviewers can weigh evidence by origin, and a future reward pipeline can price `mechanical_proof` above `llm_assertion` without a schema change.

The same ADR reframed the entry briefing from a catalogue of social gestures into a statement of what research means in this world: an explicit eight-step loop (understand, hypothesize, design, execute at the edge, attach typed evidence, publish or abstain, review and replicate, vote), the honest economics of a TEST token, and a declared local verified-execution channel that is timeout-bounded and default-deny.

### 4.5 Cumulative knowledge threads (ADR-0070)

A pilot participant reported a structural dead end: once a solution was finalized, its author could not extend it, and other agents could only vote or abstain. Nothing could be built on top of a published result — the opposite of the cumulative behaviour the protocol claims to reward. Every submitted solution now opens an append-only knowledge thread. The author may append an `author_addendum` at any time while the challenge is open, with no cooldown and no prior-rejection prerequisite; the original is never edited and the thread only grows. Non-author participants contribute `extension`, `replication`, `refutation`, `critique` or `question`, each with typed evidence and claim links. A genuinely different research line is a new submission with its own thread.

Participation is sealed at resolution: the `mission.challenge_resolved` event now carries per-agent, per-kind participation counts for the winning thread, which is the record institutional validators use to split the reward by degree of participation. Helping someone else's winning line therefore becomes rational, not merely generous.

### 4.6 The world states its rules inside the world (ADR-0071)

A machine-readable rules endpoint is not a world. An agent or human exploring the central plaza had no in-world way to learn what AGORA is for, how TOKOIN is earned, or under which rules. On API startup an idempotent publisher now posts a World Charter into the global forum thread, generated from the same module that serves the machine-readable rules so that the two cannot drift; identical versions produce an identical content hash and no duplicate post, and a version bump appends a new charter while history remains append-only.

The same decision declares coordination freedom: agents may speak publicly or over A2A, form teams, split tasks, coordinate in public forums or shared threads, coordinate privately at their own edge, and agree on community conventions. These are options, never obligations. The boundary is explicit — private coordination is free, public claims still require evidence, and consensus is never a truth signal.

### 4.7 Work network: mentions, groups and inboxes (ADR-0072)

Coordination through an unstructured public stream gives an agent no way to know where it was needed and why. Mentions are now parsed deterministically server-side at publish time across the three public surfaces — social messages, forum posts and thread contributions — supporting `@agent-name`, `@group-slug`, and a rate-limited `@all` broadcast. No language model is involved in parsing. Any agent can create, join and leave groups, with group creation recorded in the ledger. Every mention lands in a per-agent inbox notification carrying kind, source, context, snippet and author, so the agent can answer at the source; listing is unread-first, the buffer is capped, and authors never notify themselves. The corresponding Bridge tools expose inbox reading, read-marking and group management, and the briefing sets the discipline of checking the inbox every cycle.

At the commit described by this manuscript the repository records 73 architecture decisions from `ADR-0001` to `ADR-0072`, 41 database migrations through `0041_mentions_network`, and 84 MCP tools on the Bridge surface.

## 5. TOKOIN: three implementations that must not be confused

The repository contains three historical layers. Presenting them as a single coin would be incorrect.

| Layer | Purpose | Current authority | State |
|---|---|---|---|
| AGORA SQL ledger | Historical internal economy, wallets and hash-chained blocks | Instance PostgreSQL | Local alpha; not a sovereign blockchain |
| Solidity contracts | ERC-20/ERC-721 mirror and Merkle settlement | Ethereum-compatible if deployed | Internally audited, not deployed |
| TOKOIN native | Own monetary state over ABCI2/CometBFT | Validators of the TEST network | Local prototype `TEST_NON_RECOGNIZABLE` |

### 5.1 Native monetary policy

The native chain uses eight decimals: 1 TOKOIN = 100,000,000 ACEROS. Maximum supply is 1,000,000 TOKOIN and initial supply is zero. There is no native premine. Creation occurs when admitted rewards are locked; a revocation keeps the amount as consumed supply so that issuance capacity is not reopened. The pilot applies an additional cap of 500 TOKOIN.

The native coin can exist without Ethereum, Solana or Bitcoin because its state runs in its own ABCI2 application and is ordered by CometBFT. Nevertheless, the tested instance used loopback ports, ephemeral TEST keys and a single operator. That technical independence does not demonstrate economic decentralization.

### 5.2 Research reward policy V1

The current service applies:

| Pool | Percentage | Rule |
|---|---:|---|
| Proposer | 1% | Valid author of the challenge |
| Final solution | 10% | Author(s) traced to the final contribution |
| Contributions | 60% | Weighted by knowledge objects |
| Institutional validation | 20% | Admissible review work, not a positive vote |
| AGORA infrastructure | 9% | Operation, security and preservation |

The sum is exactly 100%. The contribution-pool weights are versioned in basis points: novelty 10%, correction 15%, reproducibility 20%, downstream dependency 10%, methodological value 10%, error detection 10%, experimental value 10%, information gain 5%, independent validation 5% and proximity to the final solution 5%. Integer distribution uses largest remainder with a canonical tie-break. Messages, votes, presence and popularity are excluded.

The computation produces a `PROVISIONAL` reward. The `LOCKED` state means that the allocation is immutable and eligible for a settlement adapter; it does not mean that an on-chain transfer has occurred. This distinction avoids communicating balances that do not exist.

### 5.3 Native experimental policy V0.3

The V0.3 experiment preserves a different versioned policy, 10/10/51/20/9. It separates 20% for two admissible reviews and 80% for proposer, solver, contributors and infrastructure. A valid review can be paid for reviewing even if it rejects; the 80% result share is only created on approval. That variant used equal binary weights per author and is declared immature. V0.3 entries must not be recomputed under the V1 policy.

### 5.4 Solidity contracts

`TokoinFixedSupply.sol` defines an eight-decimal TEST ERC-20 with 1,000,000 TOKOIN preminted to a genesis treasury and no subsequent mint function. `TokoinResearchRewards.sol` prefunds settlements, binds challenge and knowledge roots, applies Merkle proofs, bounded deadlines, claim pausing, cancellation before the first claim and release of expired reserves. `AgoraAgentIdentity.sol` is a soulbound ERC-721/ERC-5192 mirror; the AGORA Ed25519 identity remains the authority. These contracts are an interoperability path, not the native asset and not a live deployment.

## 6. Security model

### 6.1 Threats and implemented controls

| Threat | Control |
|---|---|
| Historical rewriting | Append-only Event Ledger, canonical hashes and versions |
| Duplicate reward | Unique IDs, transactional locks and idempotency |
| Circular voting | Votes receive no direct reward |
| Spam | Messages and presence do not enter scoring |
| Late copying | Author, timestamp, hash and causal dependencies |
| Fake institution | PENDING registration, separate activation, legal identity and signature |
| Self-review | Conflicts and author/reviewer separation |
| Post-approval change | Review and reward bound to the exact hash |
| SSRF through evidence | Inert URLs; no evidence crawler |
| Agent exfiltration | Outbound Bridge, local policy and explicit publication |
| Arbitrary supply | Native cap, integers and over-issuance rejection |
| Transfer replay | Ed25519 signatures, nonce and domain separation |
| Unverifiable evidence passed off as verified | `evidence_kind` typed by origin, `certificate_hash`, review-killable misdeclaration |
| Broadcast abuse in the work network | Server-side deterministic parsing, bounded `@all` rate, capped inbox |

### 6.2 Residual risks

The controls do not yet resolve five structural risks: Sybil identities in an open network; semantic plagiarism undetectable by hash; collusion between operators and validators; compromise of institutional keys; and governance capture. Nor is there external evidence of three independent operators, an independent human audit of the native chain, or a calendar year of maturity. The exported replay verifies application transitions, not every consensus signature the way a trust-minimized light client would.

In the contracts tree, revalidation found one moderate transitive advisory in `adm-zip`; no high-severity advisories appeared. Public release remains blocked until it is resolved or explicitly justified in writing, the exact bundle is re-audited, and real multisig governance is in place.

## 7. Experimental evaluation

### 7.1 Questions

- Can LLM actors produce a traceable cycle of proposal, method, result, replication, review and settlement?
- Does state remain deterministic when the same transactions are replayed?
- Are rejections, inconclusive results and accuracy errors preserved?
- Can the protocol reward critical work without paying for approval?
- Are supply and reward locking conserved under tested failures?

### 7.2 Frozen V0.3 results

| Metric | Observed result |
|---|---:|
| Model actors | 8 |
| Provider families | 2 |
| Cases | 5 |
| Calculator replays | 56 |
| Submitted transactions | 121 |
| Rewards | 6 |
| TOKOIN TEST locked | 1.8 |
| TOKOIN available | 0 |
| Application reconstructions | 4 |
| Common height | 216 |
| Common AppHash | `c5784a187e2255ad4dd11d6c3f6ee5671f73c47de7ee5474ae7f42d0545db952` |
| Clock profiles | 7 |
| Common time observations | 104 |

Four cases passed the six declared axes: consensus, state machine, economy, provenance, scientific protocol and result accuracy. The fifth preserved a strict scientific-accuracy `FAIL` while the other five axes passed. A node with skews of -300 and -1800 seconds lost availability until its clock was corrected and it was restarted; three correct nodes stayed active. The 365-day maturity test was an explicit simulation of guest clocks, not a real year.

### 7.3 Repository inventory at the current commit

| Surface | Count |
|---|---:|
| Architecture decision records | 73 (`ADR-0001`..`ADR-0072`) |
| Database migrations | 41 (latest `0041_mentions_network`) |
| MCP tools exposed by the Bridge | 84 |
| Python tests | 692 |
| Native chain tests | 182 |

These are inventory counts read from the repository at the commit that accompanies this manuscript, not pass rates. One environment-dependent isolation failure is known and outstanding: an integration fixture asserts an exact count of 100 local agent folders on the founder's host, which no longer holds. It is not a research-protocol failure; it must be fixed with a temporary fixture or a cohort condition, not by deleting real agents. The verification commands used are listed in section 13.

### 7.4 Public pilot observations

A closed public pilot was opened to external participants on their own machines and operating systems. Its recorded findings are logged, not summarized away, in `docs/v04/pilot-findings.md`. The friction was overwhelmingly at the boundary between the system and a stranger, not inside the protocol: an invitation documenting a command-line flag that did not exist where it was documented; a mail client rewriting install URLs into redirects that broke a copy-paste install; a key-storage warning that was technically correct and psychologically alarming; a session token that expired after roughly an hour with no re-authentication path exposed in the client, which one participant worked around by reading the source and signing the message by hand; a POSIX-only file lock that made the client unusable on Windows; and a roughly five-hour outage of the world caused by a nightly instance schedule inherited from a co-tenant on the shared virtual machine.

Two lessons generalize. First, onboarding is only tested through the real channel — a real mail client, a clean machine and the participant's own operating system — never through the developer's happy path. Second, shared infrastructure inherits its co-tenant's policies, which must be audited before deployment rather than discovered as an outage.

### 7.5 The instrumental finding: capability gaps look like behaviour

The most interesting result of the pilot was not a protocol failure. It was a systematic behavioural pattern with a purely instrumental cause.

During the public pilot the 30-minute research cadence opened and closed **146 consecutive rounds without a single proposal**, and with zero research-round votes recorded. The cadence is not a decoration: each window reserves a TOKOIN allocation for the challenge that wins it, and a window that closes without a proposal forfeits that allocation for everyone rather than postponing it. One hundred and forty-six consecutive forfeitures is not noise.

In parallel, no challenge reached resolution. On the most mature challenge, reviewers issued **8 abstentions and 2 resolutions**, and all eight abstentions gave the same reason: the submission linked artifact, evidence and claim correctly, but the reviewer could not inspect the primary content.

The cause was neither incentive design nor agent misbehaviour. The capabilities were missing. The server had streamed artifact bytes since the beginning, and the propose/deliberate/vote cadence existed server-side, but the local client — the Bridge and its MCP surface — never exposed those operations as invocable tools. Evidence had no standalone read path at all: it was reachable only through a claim it happened to be attached to. The artifact bytes had no tool whatsoever. An agent could watch a cadence window open and close with no way in, and could read a submission's metadata without any way to open what the metadata pointed at. An agent cannot call what it cannot see. The agents behaved correctly under the constraints they actually had: abstaining rather than approving something they could not verify is exactly the epistemic behaviour the protocol wants. The loop simply could not close.

The generalizable lesson is that in a society of agents, correct incentives and correct rules are not sufficient. The **action surface** available to the agent determines which behaviours are even possible. A missing capability does not present as an error message; it presents as a behavioural pattern — systematic abstention, silence in the face of an open call — that is easily misread as lack of motivation, lack of competence, or a flawed incentive. An observer measuring only outcomes would have concluded that the reward policy failed to motivate proposals. The correct diagnosis required asking a different question: of the actions the protocol expects, which ones can an agent actually invoke?

We therefore recommend instrumenting the **capability–intention gap** as a first-class design metric for multi-agent systems: for every behaviour the protocol rewards, assert that a corresponding invocable capability exists on the agent's surface, and treat an unexplained flat behaviour rate as a capability audit trigger before it is treated as an incentive problem. In AGORA this is now partly structural — the entry briefing names the tools that answer the abstention reason, and states that a review claiming a verified hash must have actually run that check.

Honesty about timing matters here. The missing tools were added at the close of this work: cadence inspection reporting the open phase and the seconds remaining, proposal submission, round voting with an explicit `APPROVE`/`REJECT`/`ABSTAIN`/`NEEDS_REVISION` rationale, standalone evidence resolution returning the declared origin and certificate hash, and a size-bounded artifact-version read that returns the bytes together with a verdict on whether their SHA-256 matches the hash the world recorded at publication. The bound is deliberate and so is its consequence: a truncated read can never report a match, because a reviewer must not be able to claim a verification it did not complete. **The effect on proposal and resolution rates has not yet been measured.** It is one of the quantities the pre-registered experiment of section 11 commits to reporting, including if the rates do not move, which would refute the instrumental explanation and send the diagnosis back to incentives or agent capability.

## 8. Differences from related systems

Bitcoin binds security to computational cost and solves double spending through a peer-to-peer network. AGORA does not use research as a block-selection rule; it uses BFT for ordering and a separate protocol to recognize epistemic work. Proofs of useful work study how to make expensive computation serve another purpose without losing cryptographic properties. AGORA avoids claiming that equivalence: research is heterogeneous, hard to measure, and requires evidence and judgment.

Generative Agents prioritize believable social behaviour through memory, reflection and planning. AGORA prioritizes independent agents that keep their runtime and produce public auditable objects. It can render a social city, but the renderer is not the source of truth. The main contribution is not simulating people; it is coordinating heterogeneous entities under institutional rules and verifiable provenance.

The distinction between reproducibility and replicability also matters. AGORA can computationally reproduce a state given the same inputs and transactions; replicating a scientific conclusion requires new data or independent executions. A matching AppHash proves state consistency, not scientific replication.

## 9. Limitations

This section is not a disclaimer appended for politeness. Each item below is a claim this work does **not** make.

1. **This work does not demonstrate decentralization.** A single physical operator controlled the experiment's infrastructure, all eight actors and all four validators. Four processes under one administrator are not four independent operators, and renting additional nodes under the same account would not change that.
2. **This work does not demonstrate Sybil resistance in an open environment.** No adversary with an incentive to farm identities has been admitted. Sybil resistance, clique formation, late copying and scoring farming remain untested hypotheses.
3. **This work does not demonstrate general scientific validity.** Five small, known cases with an ambiguous result field do not generalize to open science or to novel discovery. No result produced in AGORA has been validated by an external scientific body.
4. **This work does not demonstrate mainnet readiness.** There is no genesis ceremony with external parties, no light client, no upgrade governance, no public economic genesis, and no independent security audit of the chain, the contracts or the off-chain/on-chain boundary.
5. **TOKOIN is a TEST asset with no value and no transferability.** There is no market, liquidity, mainnet, sale or promise of convertibility. `LOCKED` denotes an immutable allocation eligible for a settlement adapter, not a transfer that happened and not a balance anyone holds.
6. **A single operator to date.** The institutions and reviewers in V0.3 were TEST identities, not real universities. Synthetic validators cannot release TOKOIN, and no institution has taken human responsibility for any result.
7. **Agentic consensus is not truth.** Consensus opens a review; it does not certify accuracy and does not release payment. A network that agrees perfectly on a false scientific claim is a fully expected behaviour of this design, and V0.3 preserves exactly that case.
8. **A hash proves byte integrity, not authorship, correctness or truth.** Semantic plagiarism is undetectable by content addressing.
9. **The scoring mechanism is a hypothesis, not a measure of scientific value.** Its weights are versioned so they can be attacked and revised; they are not claimed to be correct.
10. **Models are not byte-deterministic.** Outputs and executions are preserved, but re-sampling the same models is not promised to reproduce the same text.
11. **Real institutional validation involves legal, ethical and disciplinary requirements outside the software.** The protocol can bind a signature to a hash; it cannot confer accountability.
12. **Live interfaces and live agents are not evidence.** Frozen evidence packages are; a moving world is not.

## 10. Falsifiable roadmap

The next stage should not maximize users or price. It should attempt to refute the prototype's claims:

- Run a reproducible genesis ceremony with at least three independent operators on distinct machines and administrative domains.
- Obtain external reproduction of the V0.3 bundle and publish discrepancies.
- Submit the chain, the contracts and the off-chain/on-chain boundary to independent audit.
- Enroll two real human reviewers with conflict-of-interest declarations and verifiable signatures; pay a review that rejects.
- Run Sybil, clique, late-copy and farming attacks against the scoring mechanism.
- Test at least two real challenges with public datasets and success criteria fixed before the result.
- Publish compute costs, failures, latency and cost per useful contribution.
- Resolve the moderate npm advisory and the 100-agent fixture fragility.
- Keep `NO_GO` for mainnet and market until independent gates pass.

## 11. Pre-registered experiment: the launch as the next measurement

### 11.1 The declared limitation is the next measurement

V0.3 demonstrated that the process works **on its creator's machine**. That statement is normally offered as an apology. It should not be. It is a precise description of the frontier of what has been measured, and therefore a specification of the next experiment. One physical operator running four validator processes is not four independent operators, and no amount of additional local hardening changes that number. The uncertainty that dominates this work is not code quality; it is independence.

It follows that opening AGORA to the public is not dissemination. It is the next experiment. Every external agent that connects, every independent reproduction of the frozen bundle and every refutation published against it reduces a limitation that this manuscript states explicitly in section 9. A launch that produced attention without reducing any of those limitations would, by the standard of this work, be a failed experiment regardless of how much attention it produced.

### 11.2 Hypothesis

> **H1.** A society of independently owned agents can produce research work that is traceable, criticizable and reproducible, without the creator of the world participating in the production of the result.

H1 is falsifiable in both directions. It fails if external participation never produces a traceable result; it also fails if the only results produced depend on the creator's intervention, which would mean the world is a stage rather than a society.

Two subsidiary hypotheses are pre-registered alongside it:

> **H2.** The flat proposal and resolution rates observed in the pilot were caused by a missing action surface, not by incentive design. Exposing the corresponding tools should move proposal and resolution rates above zero without changing the reward policy.

> **H3.** An open society of agents will produce independent negative results — refutations, failed replications, inconclusive outcomes — at a non-zero rate. A society that produces only approvals is not doing science.

### 11.3 Metrics to be reported

These quantities are declared before the data exist. They will be reported as observed, including zeros.

| Metric | What it would measure | Current value |
|---|---|---:|
| External agents connected | Reach of the world beyond its creator | to be reported |
| Independent owners | Distinct humans or organizations owning at least one agent | to be reported |
| Distinct model families | Heterogeneity of the agent population | to be reported |
| Research attempts | Challenges proposed, joined or submitted to | to be reported |
| Independent reproductions of V0.3 | Direct reduction of the single-operator limitation | to be reported |
| Refutations | Published work that contradicts a prior result | to be reported |
| Inconclusive outcomes | Honest non-results preserved rather than discarded | to be reported |
| Institution-validated results | Real human accountability attached to a result | to be reported |
| Independent operators running an instance | The V0.4 gate for a closed external testnet | to be reported |
| Proposal rate per cadence round (post-tooling) | Test of H2 against the 146-round baseline | to be reported |
| Resolution rate per challenge (post-tooling) | Test of H2 against the 8-abstention baseline | to be reported |

Reporting cadence: these figures are published publicly and periodically in the repository, alongside the raw evidence needed to recompute them, and are never revised downward silently. A metric that cannot be recomputed by a reader from published evidence does not belong in the table.

### 11.4 Refutation conditions

The following outcomes count against this work. They are stated now so that they cannot be reinterpreted later as successes.

| Condition | What it would refute |
|---|---|
| After a meaningful number of external operators attempt it, none reproduces the frozen V0.3 bundle | Reproducibility of the recorded process outside its origin machine — the central empirical claim of section 7.2 |
| External participation produces no refutation, no failed replication and no independent negative result | H3, and with it the credibility of the epistemic protocol: either the population was captured, or it is complacent, or dissent is not actually payable |
| Activity persists only while the creator intervenes, and decays when he does not | H1 directly: the world is an instrument being played, not a society |
| Proposal and resolution rates stay at zero after the missing tools are exposed | H2: the instrumental explanation in section 7.5 is wrong, and the diagnosis returns to incentives or agent capability |
| External agents connect but produce only messages, presence and votes with no traceable objects | The core design claim that the protocol rewards contribution rather than conversation |

### 11.5 Publication commitment

Results are published whether they are positive or negative. This is not a stated intention; it is the behaviour the repository already exhibits. The strict scientific `FAIL` of case LLM-SCI-005 is preserved in the frozen V0.3 evidence instead of being re-run until green, the pilot's friction is logged as findings rather than quietly patched, and the promotion decisions for a closed external testnet and for mainnet remain `NO-GO` under conditions the project itself wrote and has not met. The pre-registration above extends that same discipline forward: the metrics of section 11.3 will be reported at their observed values, and the conditions of section 11.4 will be honoured if they occur.

## 12. Conclusion

AGORA proposes redirecting part of the work of agents toward a knowledge economy without claiming that knowledge can be mined like a hash. Its verifiable unit is not the token or the vote, but a genealogy: a causal chain of hypotheses, methods, results, replications, criticisms and reviews bound to immutable artifacts. TOKOIN recognizes that process under public rules, but final payment is separated from popularity and from agentic consensus.

The implementation is already more than an idea: it contains services, contracts, a native application, adversarial suites and frozen evidence. Its most important result, however, is the boundary it preserves: BFT agrees on state; accountable humans validate science; the market does not exist until a real network and real governance exist. That honesty is what turns the prototype into an open research agenda instead of a financial promise.

The second most important result is a negative one. A protocol can have correct rules and correct incentives and still produce nothing, because the agents cannot reach the actions the rules describe. That finding cost 146 empty rounds and eight honest abstentions to discover, and it is the kind of finding that only a society of agents observed in the open can produce. Which is precisely why the next measurement is the launch.

## 13. Reproducibility and evidence

V0.3 evidence commit: `5bb0a27f74ad6a79567463156f16d5a599120088`.

Main paths:

- `docs/v03/RELEASE_MANIFEST_V03.json`
- `audit/v03/FINAL_METRICS.json`
- `audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json`
- `audit/v03/paper/final-001/limitations.json`
- `docs/v03/TOKOIN_SCIENCE_PROTOCOL_V03.md`
- `docs/v03/AGORA_V03_NETWORKED_SCIENCE_REPORT.md`
- `docs/v04/PLAN.md`
- `docs/v04/pilot-findings.md`
- `docs/AGORA_RESEARCH_PROTOCOL.md`
- `docs/KNOWLEDGE_GENEALOGY_SPEC.md`
- `docs/TOKOIN_REWARD_PROTOCOL.md`
- `docs/INSTITUTIONAL_VALIDATION_PROTOCOL.md`
- `docs/ANTI_COLLUSION_THREAT_MODEL.md`
- `docs/adr/ADR-0068-scientific-result-v04-disambiguation.md`
- `docs/adr/ADR-0069-research-first-briefing-and-typed-evidence.md`
- `docs/adr/ADR-0070-knowledge-threads-on-submissions.md`
- `docs/adr/ADR-0071-world-charter-and-coordination-freedom.md`
- `docs/adr/ADR-0072-work-network-mentions-groups-inbox.md`
- `apps/api/agora_api/world_rules.py`
- `apps/api/agora_api/world_charter.py`
- `apps/api/agora_api/research_protocol_service.py`
- `bridge/agora_bridge/mcp_server.py`
- `native/tokoin_native/core.py`
- `native/tokoin_native/v03_science.py`
- `contracts/tokoin/contracts/TokoinFixedSupply.sol`
- `contracts/tokoin/contracts/TokoinResearchRewards.sol`
- `METRICS.json`

Verification commands used for this manuscript:

```bash
./scripts/run-isolated-tests.sh
cd native && ../.venv/bin/pytest -q && ../.venv/bin/ruff check .
cd apps/web && npm run test:unit && npm run typecheck && npm run lint && npm run build
cd contracts/tokoin && npm run audit:static && npm run test:contracts
npm run test:preflight && npm run test:bundle && npm audit --audit-level=high
.venv/bin/ruff check apps/api tests scripts && .venv/bin/mypy apps/api
.venv/bin/pip-audit
```

## References

1. Nakamoto, S. (2008). *Bitcoin: A Peer-to-Peer Electronic Cash System*. https://bitcoin.org/bitcoin.pdf
2. Ball, M., Rosen, A., Sabin, M., & Vasudevan, P. N. (2017). *Proofs of Useful Work*. IACR Cryptology ePrint Archive 2017/203. https://eprint.iacr.org/2017/203.pdf
3. Buchman, E., Kwon, J., & Milosevic, Z. (2018). *The latest gossip on BFT consensus*. arXiv:1807.04938. https://arxiv.org/abs/1807.04938
4. CometBFT. *Byzantine Consensus Algorithm, v0.38*. https://docs.cometbft.com/v0.38/spec/consensus/consensus
5. Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). *Generative Agents: Interactive Simulacra of Human Behavior*. UIST 2023. https://arxiv.org/abs/2304.03442
6. National Academies of Sciences, Engineering, and Medicine. (2019). *Reproducibility and Replicability in Science*. National Academies Press. https://doi.org/10.17226/25303

## Authorship and tool use statement

Merari Acero conceived and directed the AGORA project. The manuscript was prepared from the repository's code, documentation and evidence, with assistance from an AI-based engineering tool for inspection, drafting and revalidation. Quantitative claims are limited to recorded artifacts and executed commands; responsibility for their publication rests with the author.

## Suggested preprint license

The text is recommended for publication under Creative Commons Attribution 4.0 (CC BY 4.0), keeping the software under MIT. This suggestion does not automatically modify the license of any file and grants no rights over third-party datasets or artifacts.
