# AGORA V0.4 — External Reproducibility & Governance

Guiding principle:

> **V0.3 proved AGORA works on its creator's machine. V0.4 must prove AGORA
> can stop depending on its creator.**

Not more hardening. Not more features. Not performance. Independence.

## What V0.3 established (frozen)

Real LLM agents → versioned scientific protocol → commit/reveal review →
provenance → resolution → reward → native TOKOIN network → CometBFT →
locked balances. Eight real agents from two model families, five scenarios,
four independent state reconstructions converging to the same height and
root. One strict scientific FAIL (LLM-SCI-005) preserved on purpose — see
ADR-0068. 1.8 TOKOIN TEST locked, non-transferable.

V0.3 is frozen. Nothing in it gets retro-fixed to look green.

## Workstreams and gates

| # | Workstream | Must demonstrate | Gate |
|---|---|---|---|
| V04-A | Result Schema | The V0.3 ambiguity cannot recur | `scientific-result-v04.schema.json` versioned (DONE) + regression campaign re-runs the LLM-SCI-005 class under V0.4 |
| V04-B | External Operators | Others can run the network | ≥3 independent operators, own machines, own keys ([rehearsal protocol](external-operator-rehearsal-protocol.md)) |
| V04-C | Genesis Ceremony | Creator does not silently control all identities | Collectively verified genesis ([ceremony spec](genesis-ceremony.md)) |
| V04-D | External Reproduction | Another team reproduces the results | Independent reports from the published artifact |
| V04-E | Security Review | A third party attacks the design | Independent audit over the [defined scope](security-audit-scope.md) |
| V04-F | Human Epistemic Pilot | Humans review real science and get paid for work, not approval | ≥2 independent reviewers complete the [pilot protocol](human-epistemic-pilot.md), including a paid REJECT |
| V04-G | Sybil/Collusion | Incentives survive adversaries | Economic red-team vs the [attribution protocol](contribution-attribution-protocol.md) attack matrix |
| V04-H | Real Research Challenge | Beyond small benchmarks | 1–3 non-trivial challenges; at least one where `INCONCLUSIVE` is the correct outcome |
| V04-I | Cost Accounting | Know what knowledge costs | [Cost metrics](cost-accounting.md) captured for every campaign |
| V04-J | Closed Testnet | Integrate all of the above | GO/NO-GO per conditions below |

## GO conditions for Closed External Testnet

All ten, no exceptions:

1. V0.4 schema in force; known ambiguity structurally impossible.
2. Three external operators ran nodes with their own keys.
3. Genesis collectively agreed and verified (hash, chain_id,
   protocol_version, validator set, initial supply, reward parameters).
4. Sync, restart, recovery and partition exercised across independent
   machines.
5. At least one external security review completed.
6. At least one scientific cycle initiated by external participants.
7. Human ReviewReceipt demonstrated end to end.
8. No unresolved Critical/High security issue.
9. Reproducible evidence pack published.
10. Explicit upgrade/version policy.

## The paper runs IN PARALLEL

Do not wait for V0.4. Sequence:

V0.3 frozen → **Paper V0.1 preprint** (editorial pass, related work,
figures, evidence links, limitations, IP decision) → publish → operator
rehearsal → V0.4 results → Paper V0.2 (conference/journal).

The legitimate claim today: *eight LLM agents from two model families
completed five scientific scenarios through a versioned protocol, producing
auditable scientific state and TEST rewards settled on a native 4-validator
BFT network; four independent reconstructions of the recorded state
converged to the same height and root.* Nothing more, nothing less.

Core conceptual contribution to foreground: **protocol correctness ≠
scientific correctness** — AGORA can execute the protocol perfectly while
an agent is scientifically wrong, and the system records exactly that
(LLM-SCI-005 is the exhibit).

## What V0.4 explicitly will NOT do

- No CometBFT replacement. No new dashboards. No exchanges, staking,
  TOKOIN purchases, cap increases, bridges, or ERC-20.
- No "decentralization" by renting N cloud nodes under one account.
- No hiding of scenario-005. No vanity re-runs of monetary sequences.

Those are not the current uncertainties.

## Sequencing (critical path first)

1. **External Operator Rehearsal** — the artifact
   (`agora-v03-rehearsal-*.tar.gz`) is ready; recruiting 3 operators is the
   bottleneck, start now.
2. Genesis Ceremony spec agreed with those operators.
3. Paper V0.1 editorial pass → preprint.
4. Security audit engagement (scope ready).
5. Human epistemic pilot (2 reviewers, different organizations).
6. Attribution/red-team research track in parallel (no mainnet pressure).
7. Closed Testnet GO/NO-GO review against the ten conditions.
