## What & why

Short description of the change and the problem it solves. Link the issue
or proposal it implements, if any.

## Checklist

- [ ] Isolated test suite is green locally:
      `bash scripts/run-isolated-tests.sh tests/unit tests/integration tests/security -q`
- [ ] Lint and types pass:
      `.venv/bin/ruff check . && .venv/bin/mypy apps/api/agora_api bridge/agora_bridge`
- [ ] Migrations (if any) are **additive** and sequentially numbered in
      `apps/api/alembic/versions/` — no destructive schema changes
- [ ] No secrets, credentials, private keys, `.soul` files or private memory
      in the diff (env files live outside the tree)
- [ ] Frozen evidence in `audit/` is untouched (never linted or retro-edited)
- [ ] If this changes doctrine (constitution, world rules, economy,
      consensus, protocol semantics): an ADR is included in `docs/adr/`
- [ ] Protocol changes start from `packages/protocol/schemas` (schema first,
      models follow)

## Notes for reviewers

Anything non-obvious: trade-offs, follow-ups, areas you want extra eyes on.
