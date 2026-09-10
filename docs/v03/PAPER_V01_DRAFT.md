# AGORA Paper V0.1 — draft, not a publication authorization

## Title

Separating consensus, scientific procedure and evidence quality in a local multiagent research protocol with native monetary settlement

## Abstract

AGORA is an experimental research coordination system linked to the TOKOIN deterministic state machine through signed, content-bound protocol events. The design separates blockchain agreement over ordered state transitions from epistemic review of scientific evidence. We describe an evaluation methodology that measures consensus correctness, state-machine correctness, economic correctness, provenance correctness, scientific-protocol correctness and scientific-result accuracy independently. The V0.2 baseline evaluates local infrastructure hardening. V0.3 evaluates whether autonomous language-model agents can produce research artifacts whose provenance and reward derivation survive native-network inclusion and replay. Quantitative results are generated from machine-readable run artifacts; missing measurements remain UNKNOWN. This manuscript describes a local research prototype, not institutional validation, economic sustainability or production readiness.

## 1. Research questions

RQ1: Can separately identified autonomous agents complete the scientific workflow using public outputs and reproducible experimental artifacts?

RQ2: Can the network admit the derived reward exclusively through signed native transactions, with the scientific preconditions and immutable contribution root preserved?

RQ3: Can another clean local node reconstruct both monetary state and the provenance needed to explain the reward?

RQ4: Do adverse network and independent guest-clock conditions preserve state agreement and monetary maturity constraints, within the explicitly tested fault model?

RQ5: Can valid critical or inconclusive reviews obtain recognition without requiring a positive verdict?

## 2. System and threat model

AGORA stores scientific artifacts, persistent agent identities and research workflows. TOKOIN verifies transaction domains, signatures, nonces, scientific commitments and monetary transitions. CometBFT orders the transitions; epistemic validators evaluate evidence. These roles must never be conflated. An AppHash proves agreement on a state under the protocol and assumed validator trust, not the truth of a scientific assertion.

The local TEST environment uses non-recognizable experimental assets and synthetic institutional labels. Monetary policy remains the frozen protocol policy; this work does not introduce a new consensus algorithm or claim to have solved permissionless identity. Adversaries may replay transactions, submit false or persuasive claims, create conflicting branches, withhold votes, interrupt processes and manipulate isolated guest clocks. The capability and injected fault are recorded per experiment. Four processes, or several VMs on one PC, share important physical and administrative failure domains.

## 3. Experimental method

Freeze source, protocol specification, genesis and software dependencies before each campaign. Record run ID, seed where meaningful, exact model/provider identifiers, public prompts and outputs, tool calls, protocol events and intervention log. Private chain-of-thought is outside the experimental record. Model outputs are observations; exact regeneration of nondeterministic hosted-model sampling is not promised. Deterministic replay concerns recorded protocol transactions and state transitions.

Keep initial failures and their reproductions as separate evidence. A corrected rerun never overwrites the initial artifact or changes its reported status. V0.2 measurements remain explicitly historical; they cannot substitute for a V0.3 pass after the source changes.

The agent campaign covers known ground truth, a persuasive false hypothesis, inconclusive evidence, conflicting replication and attempted manipulation. Scenario ground truth and criteria must be frozen before scoring the observed result. Ground-truth disclosure to agents, scripted interventions and benchmark construction are recorded explicitly. A correct procedure may end inconclusively. A scientific error can coexist with correct consensus and monetary enforcement.

## 4. Independent outcome axes

| Axis | Measurement question | Evidence needed |
|---|---|---|
| consensus_correctness | Do honest nodes agree at the same canonical height? | Block identity, height and AppHash per node |
| state_machine_correctness | Were only permitted transitions applied? | Signed corpus, rejection events and replay |
| economic_correctness | Are cap, conservation, eligibility and locking rules preserved? | State balances, supply and invariant results |
| provenance_correctness | Can identities and artifact references be reconstructed? | Hashes, graph edges and referenced bytes |
| scientific_protocol_correctness | Was the declared research and review procedure followed? | Events, blind commitments/reveals, disputes and receipts |
| scientific_result_accuracy | Does the result match independently specified ground truth? | Ground-truth definition and result assessment |

PASS, FAIL, UNKNOWN and NOT_APPLICABLE are distinct. UNKNOWN is not counted as success. Disagreement does not automatically mean failure: the declared expected behavior controls scoring. Review-work compensation and research-success compensation must be analyzed separately.

## 5. Evidence generation

No experimental number is transcribed into this draft. Run:

```bash
.venv/bin/python native/tools/v03_evidence.py \
  --input /absolute/path/to/v03-run.json \
  --output /absolute/path/to/new-paper-evidence-directory
```

Inputs use `AGORA_V03_RUN_V1`. V0.2 data require an explicit `--historical` flag. The generated `PAPER_EVIDENCE_INDEX.json` binds dataset and figure bytes. The nine datasets are the authoritative quantitative appendix. The eight SVG figures distinguish conceptual architecture from observed data; missing event times are not replaced by invented timings.

The generated results section below references the frozen evidence directory and release manifest. Before inclusion, each statistical or experimental statement is checked against its source rows and scope. No aggregate pass rate should combine historical campaigns, unrelated tests or the six independent correctness axes.

## 6. Limitations

A single host cannot establish independent administration, geographic fault tolerance, real decentralization or permissionless security. TEST epistemic identities do not establish human institutional responsibility. Local LLM experiments do not prove general scientific discovery. Contribution scoring and review eligibility can be gamed beyond the tested attacks. Independent guest-clock tests characterize only the tested offsets and faults. Application export replay is not a substitute for verification of CometBFT consensus signatures or a trust-minimized light client. Monetary scarcity does not establish market value, adoption, utility demand or sustainable validator economics. A short experiment cannot demonstrate that a full maturity period elapsed in real time.

External operators must reproduce installation and recovery on independently administered machines. Their reports are an external dependency and may not be fabricated by the development team. No such participation is asserted here.

## 7. Reproducibility and artifact availability

Provide frozen source commit, protocol hashes, engine build metadata, public genesis, test-only public identities, per-run inputs and public outputs, signed transaction corpus, node logs, AppHash observations and machine-readable outcomes. Exclude private keys, credentials and private reasoning. Publish public artifacts only after explicit release review. The paper candidate is separate from an economic launch.

## 8. Related work and authorship

CometBFT implements deterministic state-machine replication through BFT consensus; AGORA does not introduce a new block-consensus algorithm. Its experimental addition is the separate, hash-linked scientific workflow and reward state machine. The underlying Tendermint design is described by Buchman, Kwon and Milosevic, [The latest gossip on BFT consensus](https://arxiv.org/abs/1807.04938). Protocol-level discussion must not be confused with a proof that this application or every engine deployment is correct.

The pinned engine uses the [CometBFT v0.38.26 BFT Time specification](https://github.com/cometbft/cometbft/blob/v0.38.26/spec/consensus/bft-time.md): block time derives from weighted commit timestamps under its fault assumptions. This motivates testing guest-clock faults separately from deterministic application maturity. The observed node failures are reported as operational limitations rather than generalized time tolerance.

The terminology follows the National Academies' [Reproducibility and Replicability in Science, Introduction](https://www.ncbi.nlm.nih.gov/books/NBK547530/): rerunning computational results with recorded inputs is distinct from new independent evidence. Our calculator replay and repeated network transitions primarily test the former. Multiple model contexts under one operator do not substitute for independently administered scientific replication.

These primary references were checked during preparation. This manuscript makes no priority, patentability, general discovery or institutional endorsement claim. Named human authors and corresponding responsibility must be supplied and reviewed before submission; automated reviewers do not confer institutional authorship. A paper candidate and permission to publish it are separate decisions.

<!-- BEGIN GENERATED V03 RESULTS -->
## Observed results from frozen V0.3 evidence

Source commit: `5bb0a27f74ad6a79567463156f16d5a599120088`. The final campaign contains 8 real model actors and 5 benchmark cases. Its recorded calculator artifacts passed 56 deterministic replays. The native network recorded 121 submissions, including expected rejections. These are submissions, not all successful payments.

The monetary state contains 6 locked reward records totaling 180000000 integer base units (1.80000000 TEST TOKOIN). Available supply in wallets is 0 units. These TEST allocations have no mainnet recognition or asserted market value. 4 separate application replay processes reconstructed height 216, state root `c5784a187e2255ad4dd11d6c3f6ee5671f73c47de7ee5474ae7f42d0545db952`. The replay tool explicitly does not claim independent CometBFT consensus-signature verification.

| Caso | Consenso | Estados | Economía | Provenance | Protocolo científico | Exactitud estricta |
|---|---|---|---|---|---|---|
| LLM-SCI-001 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-002 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-003 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-004 | PASS | PASS | PASS | PASS | PASS | PASS |
| LLM-SCI-005 | PASS | PASS | PASS | PASS | PASS | FAIL |

The final adversarial case retains a strict structured-result FAIL. Both reviewers identified the archived false assertion; one used the ambiguous `claimed_count` field for the rejected assertion rather than the computed result. No output or oracle criterion was rewritten after observation. This is a limitation of the structured response/evaluation interface, not evidence of a different canonical chain state. See the exact public conclusions and numerical artifacts in the source campaign.

| Suite | Aprobadas | Fallos | Omitidas |
|---|---:|---:|---:|
| Native | 182 | 0 | 0 |
| API unit/integration | 455 | 0 | 1 |
| E2E/security | 191 | 0 | 0 |

The opt-in provider campaign skipped by the general suite was executed separately and retained in the agent evidence. Its overlapping calculator unit tests are not added to these totals.

The independent-clock campaign tested 7 profiles using separate guest kernels and compared 104 common heights. The lagging node was unavailable under the documented large negative offsets; the remaining quorum progressed and the node recovered after guest-clock correction and restart. The finality jump is simulated elapsed consensus time, not a real calendar year. Its reward fixture is explicitly the compatible legacy monetary path, not proof that the complete scientific bridge ran inside those VMs.

All quantitative statements in this section were generated from `FINAL_METRICS.json` and the linked source records. The paper datasets and figures are bound by `audit/v03/paper/final-001/PAPER_EVIDENCE_INDEX.json`.
<!-- END GENERATED V03 RESULTS -->
