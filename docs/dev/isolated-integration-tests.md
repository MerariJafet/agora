# Isolated integration + security tests

Mutating API tests fail closed unless:

- `AGORA_ENV=test`
- database name starts with `agora_test_`
- Redis is **not** the development URL `redis://localhost:6380/0` (use DB `/15`)
- `AGORA_RUN_ID` is unique (not `manual` / `dev` / `development`)

## Supported local command

Do **not** point tests at the live `agora` database on `:5434`. Use the
repo wrapper (creates a disposable `agora_test_*` DB on the existing
`agora-dev-postgres-1` container, migrates, runs pytest, drops the DB):

```bash
# full integration + security (Makefile)
make test-int

# or directly
scripts/run-isolated-tests.sh tests/integration tests/security -q

# unit (no DB mutation guard required, but fine under the wrapper too)
.venv/bin/python -m pytest tests/unit -q
```

Environment the wrapper exports (see `scripts/run-isolated-tests.sh`):

```text
AGORA_ENV=test
AGORA_DATABASE_URL=postgresql+asyncpg://agora:agora_dev_password@localhost:5434/agora_test_<run_id>
AGORA_REDIS_URL=redis://localhost:6380/15
AGORA_RUN_ID=<run_id>
AGORA_PROVENANCE_CLASS=test
AGORA_OUTBOX_ENABLED=false
AGORA_RESEARCH_SCHEDULER_ENABLED=false
```

## Optional fully separate Postgres

If you must not share the agora-dev Postgres process at all:

```bash
docker run -d --name agora-test-pg \
  -e POSTGRES_USER=agora \
  -e POSTGRES_PASSWORD=agora_dev_password \
  -e POSTGRES_DB=agora_test_local \
  -p 127.0.0.1:55460:5432 \
  postgres:16-alpine

export AGORA_TEST_POSTGRES_CONTAINER=agora-test-pg
# then either point AGORA_DATABASE_URL at :55460/agora_test_* yourself
# after CREATE DATABASE, or adapt the wrapper container name + port.
```

Never run `docker compose down` on `agora-dev-*` while other work depends on
postgres `:5434`, redis `:6380`, or nats `:4222`.
