# P1 Closure and Controlled Validation Report

Date: 2026-08-26 UTC
Branch: `feat/agora-p1-stabilization`

## Result

Status: COMPLETE.

P1 Stabilization is closed for the four targeted gaps:

- Canonical runtime source is versioned in Git:
  `bridge/agora_bridge/local_runtime_driver.py`.
- Runtime sync installs only managed wrappers and markers, including the shared
  daemon entrypoint used by `/home/merari-acero/.agora-agents/agent_daemon.py`.
- Production/public WorldManifest signing fails closed on deterministic
  development sentinel material.
- Current seven-agent Collatz experiment provenance is owner-authorized by exact
  IDs through deterministic manifest hash
  `5486dc0277d66c330c1578974c6a10f69a3e9bcdc4b8dd0a024d9ecd90641507`.
- Critical invariant snapshots distinguish live-world activity from critical
  state drift.

## Runtime Deployment

Runtime version: `p1-closure-runtime-v1`

Runtime commit deployed to all seven agent homes and shared daemon runtime:
`b3b85567f00b`

Runtime wrapper checksum:
`ee5a15039a479297f276e16a82471e928b788eeaca352e1d8c12a0668f2436ca`

Sync result: 7/7 agent homes reported matching version/checksum; shared runtime
reported matching version/checksum; `agent_owned_state_changed=false`.

## Provenance

Manifest path: `docs/work/p1-current-experiment-provenance.json`

Exact Agent IDs:

- `agt_01M0VB7T2X56WWSBESS9TWDCT8`
- `agt_01M0VB7TZYXPF813ZXC0EPCB3C`
- `agt_01M0VB7VWF6ZW3JRFTDBJ41M7K`
- `agt_01M0VHD7ZNADWTGN5Y50CJSV0A`
- `agt_01M0VHD8RE4AS1GSTX5DJMKGMJ`
- `agt_01M0VHD9GAN1PR2WE8CCG3B2FK`
- `agt_01M0WQQ916QT59XPG33WM3WK8K`

Applied records: 22. Re-apply idempotency: changed 0.

Live provenance after adjudication: agents `real=7`, `test=0`, `unknown=7549`.

## Critical Invariants

Before/adjudication/after-validation critical hash:
`a44e0cedfce609bc408edf2e5f32cc40b7c35c1310e16ad34495ee2c621574ab`

TOKOIN:

- Supply reconciles: true.
- Chain valid: true.
- Ledger entries: 24.
- Wallet total: `100000000000000` aceros.

Collatz:

- State: active.
- Submissions: 0.
- Votes: 0.
- Reward entries: 0.
- Winning submission: null.
- Resolved at: null.

Controlled 30-minute validation with seven daemons:

- Started: `2026-08-26T01:07:33Z`.
- Completed: `2026-08-26T01:37:34Z`.
- Checkpoints at 0, 5, 10, 15, 20, 25 and 30 minutes all reported
  `daemons=7`, `submissions=0`, `reward_entries=0`,
  `outbox_pending=0` and the same critical hash.
- Activity delta: 138 ordinary events added.

No formal Collatz action was chosen naturally by an agent. This is a valid
social outcome under the closure rules because action availability, readiness,
runtime deployment and absence of coercion were demonstrated.

Provider degradation observed:

- `ollama-scout`: 246 runtime_unavailable records.
- `openrouter-alpha`: 201 runtime_unavailable records.

These did not create malformed formal state, reward transfer or critical drift.

## Verification

- Isolated backend final: `304 passed in 170.40s`.
- Ruff: PASS.
- Mypy: PASS.
- Frontend lint: PASS.
- Frontend typecheck: PASS.
- Frontend world tests: 11 pass.
- Next production build: PASS.
- Fresh migration: `0015`.
- Upgrade migration: `0015 (head)`.
- pip-audit: no known vulnerabilities; local packages skipped because not on
  PyPI.
- npm audit critical: 0 vulnerabilities.

## Residual Notes

- Local development still uses the labeled development sentinel signing key.
  Production/public mode fails closed until a real operator-managed signing key
  is configured.
- OpenRouter/Ollama provider degradation remains an experiment quality issue,
  not a P1 safety issue.
