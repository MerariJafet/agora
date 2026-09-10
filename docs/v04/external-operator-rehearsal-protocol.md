# V04-B — External Operator Rehearsal Protocol

Research question:

> Can a reasonably competent operator reproduce AGORA/TOKOIN **solely from
> the published artifact**, with no help from the creator?

Artifact under test: the frozen V0.3 rehearsal bundle
(`agora-v03-rehearsal-<hash>.tar.gz`) plus its public documentation.
Nothing else. If the artifact is not enough, that is a *finding*, not a
support ticket.

## Operator topology (target)

```
Merari ───────── Validator A
External Org 1 ─ Validator B   (own machine/cloud, own network, own key)
External Org 2 ─ Validator C   (different person, different provider, own key)
External Org 3 ─ Validator D   (different administration, own infra, own key)
```

Three genuinely independent operators minimum. Different people, different
infrastructure, different administrative domains. Renting three VMs under
the creator's account does not count and will not be labeled as counting.

## The hard rule: NO SILENT INTERVENTION

During the rehearsal, the AGORA team must not SSH into an operator's
machine, hot-patch their node, or fix their configuration silently. Doing
so destroys the experiment.

Every operator difficulty is data:

- "I don't understand how to generate the key" → finding.
- "This parameter is undocumented" → finding.
- "The node can't find peers" → finding.
- Twenty unexpected steps → twenty findings.

Allowed: answering questions **in a public, logged channel**, where every
answer is itself recorded as a documentation gap. Forbidden: touching their
machines, shipping private patches, or editing the artifact mid-rehearsal.

## Metrics (mandatory, per operator)

```
time_to_first_block
installation_failures
documentation_questions
manual_interventions        (must be 0 from our side; count theirs)
restart_success
recovery_success
sync_success
hash_verification           (genesis + AppHash convergence)
operator_errors
wall_clock_total
```

Outcome is not just PASS/FAIL — the metric vector and the question log are
the product. Publish them.

## Procedure

1. Operator receives ONLY: artifact URL + hash, public docs URL, and the
   reporting template below. No calls, no screen-shares.
2. Operator generates their own validator key (never shared; only the
   public key leaves their machine).
3. Genesis ceremony per [genesis-ceremony.md](genesis-ceremony.md).
4. Network bring-up: first block, then scripted drills — restart one node,
   kill and recover one node, partition and heal, verify all four report
   the same height/AppHash.
5. Each operator independently reconstructs the V0.3 evidence pack state
   and reports the height/root they obtained.
6. Reports collected verbatim; discrepancies are findings, not
   embarrassments.

## Reporting template (per operator)

```
operator_id / org:
hardware + OS + provider:
artifact hash verified: yes/no
time_to_first_block:
steps that did not match the docs: [...]
questions asked (public log links): [...]
drills: restart / recovery / sync / partition → outcomes
final height + AppHash:
verdict: could you run this without the creator? yes/no/partially
```

## Recruiting note

Candidates: technically competent peers who are NOT collaborators on
AGORA — other engineers, university lab staff, community operators. The
ask is bounded (an evening to a weekend), the artifact is small, and their
name (or org) appears in the paper's acknowledgements and the published
rehearsal report if they wish.
