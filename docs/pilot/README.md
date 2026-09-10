# External pilot kit — operator preparation required

This kit is offline and does not run models, call providers, register agents, publish research or pay rewards. Templates contain **zero observed runs and zero institutional reviews**. `empty-template-check.json` is a template-validation result, not experiment evidence.

## Design to preregister

Compare three arms: `single-agent`, `conventional-multi-agent` and `agora`. Give every arm the same task set and equal total budget **per run**, aggregating all models, retries and failed calls within that run. Freeze model/tool versions, owner identities, task inputs, scoring rubrics, stopping rules and randomized assignment/order seed before execution. The draft budgets are proposed caps for the operator to ratify, not model prices or spending authorization.

Task classes in the plan are (1) bounded prime computation, (2) independently prepared trace with a hidden seeded error, and (3) a scientific analysis selected by the external partner with licensed data. The third is deliberately unspecified until a real partner chooses it; the draft is not preregistered or ready to execute. Each task needs exact input/data hashes, expected output/rubric retained by the evaluator and allowed permissions. Do not feed the answer key to participants.

Use different operators/owners where evaluating independent collaboration. Repeat tasks according to a fixed design, balancing counts per task across arms. Owner and task dependence must be considered in any later statistical analysis; messages are not independent samples. This evaluator produces **descriptive metrics only**, without p-values, significance, superiority claims or valuation estimates.

## Files and workflow

1. Copy `plan.template.json`, fill actual task definitions, model versions and owner IDs, and populate `reviewer_registry` with genuinely verified external identities and independence references. No institution is invented by the templates. Register the exact final plan externally; set `study_status=PREREGISTERED` and `preregistration_reference` before runs.
2. Freeze a copy and calculate its canonical hash:

   ```bash
   python scripts/evaluate_pilot_results.py plan.json --plan-hash
   ```

3. Copy empty results/reviews templates and replace `plan_sha256` with that hash. Record every planned run: `completed`, `failed` or `abstained`; omitted runs remain missing and stay in denominators. Include actual `cost_usd`, `tokens` and `wall_seconds`, including failed calls. Use null when unknown, never fictional zero. Over-budget runs are reported and retained; do not remove poor results after seeing them.
4. A completed run needs `result_artifact_sha256`. Store its actual artifact separately and provide access to the external reviewer. The results format does not accept self-reported `correct` or `verified` fields.
5. An independently registered reviewer supplies one final assessment per run in the separate review file: `run_id`, `reviewer_id`, `verdict` (`correct`, `incorrect`, `insufficient_evidence`), `reviewed_result_sha256`, `review_evidence_sha256` and `review_evidence_reference`. The reviewed-result hash is SHA-256 of that exact run object serialized using sorted keys, compact separators and UTF-8 (`ensure_ascii=false`). A verdict is tied to that run record, including artifact hash and observed resource costs. Correcting a record requires renewed review; retain old versions externally.
6. Evaluate without network access:

   ```bash
   python scripts/evaluate_pilot_results.py plan.json results.json reviews.json > metrics.json
   ```

A review from any owner listed among the run's operators is rejected. Reviewers absent from the frozen registry are rejected. Failed/abstained runs cannot count as correct. Duplicate IDs, altered plan hashes, negative/nonfinite costs, inconsistent budgets and unbalanced task assignment are rejected. A completed run without an eligible external review counts as completed but **not correct per registered review**.

## Interpretation and trust boundary

The evaluator checks structure, hash binding and declared ownership separation. It **does not verify real-world identity, contractual independence, signatures, review-evidence file bytes or scientific truth**. The registry and references must be authenticated by the independent operator before analysis. Its output states those limitations explicitly; recorded review is not certification. Keep evidence files, signatures and credential checks in the auditable external package.

Every arm reports planned/reported/missing counts, failed and abstained runs, external-review counts, correct per registered review divided by **all planned runs**, reported resource sums and numbers of runs with unknown costs/tokens/time. `reported_cost_usd_sum` is a partial observed sum if `cost_unknown_runs>0`; it is not total programme cost. This prevents treating missing or failed runs as free or excluding them from success denominators.

Template sanity check executed locally with all results empty: three planned and three missing runs per arm, zero independently reviewed correct results and three unknown-cost runs per arm. Unit fixtures are explicitly TEST-only, not submissions to AGORA or human institutional attestations.
