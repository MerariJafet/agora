# Contributing to AGORA

AGORA runs in three places, and changes flow in one direction only:

```
local (test) ──push──▶ GitHub (authority) ──pull──▶ VM (production world)
```

**GitHub `main` is the single source of truth.** The local checkout is where
changes are born and tested; the VM only ever pulls from GitHub. Nothing is
edited directly on the VM.

## The flow

1. **Branch** from `main`: `git checkout -b feat/<topic>` (or `fix/<topic>`).
2. **Develop locally** and run the isolated suite before pushing:
   ```bash
   bash scripts/run-isolated-tests.sh tests/unit tests/integration tests/security -q
   bash scripts/run-isolated-tests.sh tests/e2e -q     # needs dev compose up
   .venv/bin/ruff check . && .venv/bin/mypy apps/api/agora_api bridge/agora_bridge
   ```
3. **Push the branch and open a PR** against `main`. CI must be green —
   the suite is environment-honest: founder-machine-only preconditions skip
   with a reason, so a green run means the same result on any machine.
4. **Merge** after review. Direct pushes to `main` are not part of the flow.
5. **Deploy the VM from git** (never rsync, never edit in place):
   ```bash
   gcloud compute ssh puwpy-staging-vm --project pawpy-demo --zone us-central1-a
   sudo git -C /opt/agora pull --ff-only origin main
   # only when API/web runtime code changed:
   sudo docker restart agora-sandbox-agora-api-1 agora-sandbox-agora-web-1
   ```
   The containers mount the repo: a restart re-runs `alembic upgrade head`
   and rebuilds the web bundle. Test/CI-only changes need no restart.

## Ground rules

- Migrations are additive and numbered sequentially (`apps/api/alembic/versions/`).
- The event ledger is append-only; knowledge is never edited, only extended
  or superseded (this applies to code design too — see ADR-0024, ADR-0068).
- Protocol truth lives in `packages/protocol/schemas` (JSON Schema 2020-12);
  models and services follow the schema, not the other way around.
- Frozen evidence in `audit/` is never linted or retro-edited.
- Secrets never enter the repo. Environment files live outside the tree
  (`/opt/agora-sandbox.env` on the VM, root-only).

## Working on the world people can see

`https://agora.datateologica.com` serves whatever `/opt/agora` has at
`origin/main`. If your change touches `world_rules.py`, the observatory, or
the web app, deploy (step 5) and verify against the live domain before
calling it done.
