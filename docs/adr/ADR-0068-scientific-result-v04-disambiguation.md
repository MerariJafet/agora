# ADR-0068 — Freeze V0.3 as-is; disambiguate the structured scientific result in V0.4

Status: accepted (2026-09-10)

## Context

The V0.3 networked-science campaign closed with a strict FAIL in scenario
LLM-SCI-005: the single structured field `claimed_count` was used by one
reviewer for the *rejected assertion* and by the evaluator for the *computed
result*. Both reviewers correctly identified the false assertion; the FAIL is
a defect of the structured response/evaluation interface, not of the chain
state, the review economics, or the reviewers' science.

Two pressures followed: (a) the temptation to "fix" V0.3 so the scoreboard
reads all-green; (b) the need to run further campaigns on a sound schema.

## Decision

1. **V0.3 is frozen.** LLM-SCI-005 remains a recorded FAIL forever. No V0.3
   artifact, verdict or evaluation criterion is rewritten after observation.
   The historical record intentionally reads:
   `V0.3 → LLM-SCI-005 = FAIL` → `V0.4 → schema ambiguity corrected`.
2. **`ScientificResultV04`** (packages/protocol/schemas/
   `scientific-result-v04.schema.json`) replaces the V0.3 structured result
   for all future campaigns. Design rule: *no field may carry two meanings*.
   The ambiguous `claimed_count` is abolished in favor of explicitly-roled
   fields: `reported_value` (what the submission asserted, verbatim),
   `computed_value` (what the reviewer's own computation produced),
   `expected_value` (frozen oracle, when one exists), `accepted_value`
   (written only by resolution), plus `comparison_operator`, `tolerance`,
   `unit` (mandatory on every value) and `evaluation_method` (citable,
   frozen procedure id).
3. `INCONCLUSIVE` is a first-class verdict, and `REJECT`/`INCONCLUSIVE`
   reviews remain payable when they meet protocol requirements — the
   V0.3 review-economics rule (rewarding verifiable epistemic work, not
   approval) is carried forward unchanged.
4. The first V0.4 regression campaign MUST re-run the LLM-SCI-005 scenario
   class under the new schema and report the outcome next to the frozen
   V0.3 FAIL.

## Consequences

- The paper can present the FAIL as a finding: the experiment surfaced a
  protocol deficiency and the protocol evolved — *protocol correctness ≠
  scientific correctness* becomes demonstrable with our own history.
- Evaluators and agents need a migration: any tooling reading
  `claimed_count` breaks loudly (field removed, schema_version bumped),
  which is intended.
- Open scenarios (no ground truth) are now expressible without abusing the
  oracle field (`expected_value` null + unit "none" + operator
  `not_applicable`).
