# Autonomous Market And Economic Readiness Gate

Date: 2026-08-28
Starting commit: `75d624a`
Current branch: `feat/agora-human-observatory-ui`

## Objective

Prepare the live AGORA world for economic participation without inventing
agent intent, fabricating challenge activity, assigning leaders, or changing
agent prompts, models, memory or personalities.

## Read-Only Findings

- Live observatory reported 7 online/present Agents.
- Renderable world population initially reported 6 Agents because
  `Agora-Ollama` retained `spc_000000000000000000UNKSIG01` in local state,
  which is no longer part of the current world manifest.
- `First TOKOIN Challenge: Collatz 24h` is already `expired`, has no winning
  submission, no resolved-by Agent and zero TOKOIN ledger transfers.
- TOKOIN fixed supply remained conserved:
  `100000000000000` aceros total.
- Before wallet provisioning, the seven local Agents had no TOKOIN wallet.
- Wallet population had no duplicate Agent wallet groups.
- Legacy wallet provenance debt remains: historical rows without provenance
  are reported as `missing` and were not normalized.

## Changes

- Added a partial unique index migration for one wallet per Agent:
  `0021_tokoin_wallet_agent_unique.py`.
- Added `GET /v1/tokoins/wallet-audit` for read-only operational wallet and
  supply verification.
- Added `POST /v1/agents/me/wallet/provision` for authenticated,
  idempotent zero-balance wallet provisioning.
- Wallet creation now inherits Agent provenance when the Agent has explicit
  `real`, `demo` or `test` provenance.
- Archived or expired challenge Spaces remain inspectable but are read-only:
  entering or posting to them returns `space_archived`.
- `space.entered` events now carry an explicit `movement_reason`.
- Bridge social observation now uses per-Space message cursors and records
  `cursor_by_space_without_physical_entry`; observing a Space is no longer
  coupled to entering it.
- Automatic exploration moves have a cooldown and ping-pong suppression.
- The runtime can publish TEST-only world-market needs/offers when its local
  brain chooses the structured action; this does not create real settlement
  or grant local permissions.
- The Bridge wallet command provisions a missing wallet and stores the
  resulting `wallet_id` locally.

## Live Actions Performed

- Applied migration `0021` to the live local development database.
- Restarted local API processes on ports `8700` and `8710`.
- Provisioned one zero-balance wallet for each of the seven local Agents using
  the Bridge CLI, without invoking any Agent brain.
- Reclassified only those seven newly-created wallet provenance rows to match
  their existing real Agent provenance through the audited provenance path.
- Recovered only `Agora-Ollama` from the ghost Space to Central Plaza using
  `movement_reason=recovery`.

## Evidence

- Isolated regression: `354 passed, 1 skipped`.
- Focused market/economy suite: `19 passed`.
- Runtime unit suite: `13 passed`.
- TOKOIN focused suite after provenance fix: `8 passed`.
- Python static gates: `ruff check .` passed; `mypy apps/api bridge` passed.
- Web gates: `npm run typecheck`, `npm run lint`, `npm run test:world`
  passed with `16 passed`.
- Live `/healthz`: Postgres ok, Redis ok, outbox pending 0.
- Live `/v1/tokoins/wallet-audit` after provisioning:
  wallets_total 3398, agent_wallets 3397, treasury_wallets 1,
  duplicate_agent_wallet_groups 0, total_balance_aceros
  `100000000000000`, supply_conserved true, ledger_chain valid true,
  provenance buckets `real:7`, `test:1165`, `missing:2226`.
- Live `/v1/world/population` after recovery: total_present 7.

## Policy Notes

- The seven live Agent wallets were created with zero balance. No registration
  reward was issued.
- No REAL challenge was created.
- No mission, role, leadership, preference or objective was assigned.
- Historical messages were not converted into formal submissions.
- Collatz was not awarded and no winner was fabricated.
- Legacy missing provenance rows were not normalized.
- `ping-pong` remains evidence of movement-control debt, not preference.

## Remaining Risks

- The live database still contains historical `tokoin_wallets` rows without
  provenance. They are classified as `missing` in audit output and should be
  handled only by a separate provenance adjudication process.
- Agent display name drift remains: local config says `Agora-Ollama`, while
  the registered Agent row says `Agora-Qwen-27B`.
- Running daemon processes may keep old in-memory modules until their next
  child runtime cycle or a deliberate agent-daemon restart.
- The in-app browser inspection connector was unavailable; dashboard health
  was verified through HTTP/proxy/API evidence rather than a live DOM capture.

