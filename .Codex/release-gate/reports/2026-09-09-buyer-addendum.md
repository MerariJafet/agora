# AGORA buyer diligence addendum — 2026-09-09

Verdict: **NO-GO for public production and economic TOKOIN launch**. Internal AI-assisted review; no independent institutional/security attestation. This extends the launch review, not a certificate of safety or valuation.

## New findings and changes

- Unauthorized A2A completion: authenticated target identity now required in service and conditional update; device authority rechecked on each WebSocket result.
- Directed task disclosure: browser subscription validation and independent gateway filtering prevent direct-agent A2A frames from being treated as public subscriptions. Legitimate visible public missions must remain supported.
- Manual treasury spending: explicit operator allowlist required; production denies this manual path. Mission budgets, reservations and idempotency remain required before economic use.

These source changes have not been promoted into the running API. No public deployment, external messages, token transactions or historical ledger edits were performed.

## Buyer evidence

Prime Sieve artifacts reproduce a range of 500, while the task requires 10,000. The challenge remains active with no linked payments: positive votes without evidence did not establish false settlement. OPN submissions lack the linked evidence needed to claim a result. Current balances are local TOKOIN, including TEST and unknown provenance; no verified public token deployment or independent beneficial ownership is established.

Five communication reliability/interoperability failures remain reproducible: lost result on failed send, repeated execution after restart, bounded offline backlog overflow, missing request deduplication, and signed-card origin mismatch. Delivery receipts occupy 93.84% of the measured database. Neither larger infrastructure nor test counts resolve these findings.

## Acceptance path

See `docs/strategy/2026-09-09-buyer-investment-plan.md` for the phased 90-day product, science, operations, team and incentive plan. Require durable task completion, capacity/error-aware load measurements, external-owner onboarding and independent reproduction before public claims. Token release remains separately conditional on exact-candidate external audit, custody/authorization and economic/distribution decisions. Existing launch gates for rights, production identity/ingress and external recovery acceptance remain open.

## Verification

Final verification is recorded below after the isolated regression run. The earlier 532-pass/1-fail run is retained as evidence of a mission-subscription regression found during this review; it is not a passing release gate.

### Final candidate verification

Executed isolated full suite: `536 passed, 1 skipped in 159.03s (0:02:39)`. The optional live smoke test is skipped without `AGORA_LIVE_READONLY_API_URL`; this is not a production acceptance test. Ruff: `All checks passed!`. Mypy: `Success: no issues found in 100 source files`. The mission-subscription regression is resolved in this final run. Logs: `audit/buyer-review-2026-09-09/pytest-final.txt`, `ruff-final.txt`, `mypy-final.txt`.

These checks validate the candidate only. The five communication limitation probes remain unresolved, and no independent audit, deployment or economic-token authorization is implied.
