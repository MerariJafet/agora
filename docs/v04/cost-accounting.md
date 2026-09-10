# V04-I — Cost Accounting

Mandatory from the next campaign on: every investigation produces a
machine-readable `CostReportV04`
(packages/protocol/schemas/`cost-report-v04.schema.json`).

## Captured per campaign

```
total_llm_tokens          (prompt + completion, per provider)
model_calls
tool_calls
wall_clock_duration_s
compute_cost_usd          (estimated, method recorded)
external_api_cost_usd
network_traffic_bytes
storage_growth_bytes
human_review_minutes
n_agents
n_experiments
n_replications
tokoin_test_awarded
```

## Derived metrics (the interesting part)

- cost per challenge
- cost per hypothesis
- cost per conclusion
- **cost per correct conclusion**
- cost per replication
- **cost per detected false hypothesis**

These turn AGORA into a measurable economic experiment and are the only
path to eventually answering: *does AGORA produce research at a
competitive cost?* Today the honest answer is UNKNOWN — which is exactly
why the measurement starts now, not after economics go live.

## Rules

1. Estimates are labeled as estimates with their method; unknown fields
   stay `null`, never guessed.
2. Cost reports ship inside the campaign evidence pack and are
   content-hashed with it.
3. No campaign result may be published without its cost report from
   V0.4 onward.
