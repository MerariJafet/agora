# AGORA Sprint 01 — developer commands. See README.md quickstart.
COMPOSE := docker compose -f infra/docker/docker-compose.yml
PY := .venv/bin/python
VENV := .venv/bin

.PHONY: setup infra-up infra-down migrate api web bridge-help test test-unit test-integration test-e2e lint typecheck audit teardown

setup:            ## venv + python deps + editable installs + web deps
	python3 -m venv .venv
	$(VENV)/pip install --upgrade pip
	$(VENV)/pip install -r requirements.txt
	$(VENV)/pip install -e apps/api -e bridge
	cd apps/web && npm install --no-audit --no-fund

infra-up:         ## boot postgres + redis + nats with health checks
	$(COMPOSE) up -d --wait

infra-down:
	$(COMPOSE) down

migrate:          ## apply database migrations
	$(VENV)/alembic -c apps/api/alembic.ini upgrade head

api:              ## run AGORA API on :8700
	$(VENV)/uvicorn agora_api.main:app --host 127.0.0.1 --port 8700

web:              ## run AGORA web on :3000
	cd apps/web && npm run dev

test: lint typecheck test-unit test-integration test-e2e  ## full gate

test-unit:
	$(PY) -m pytest tests/unit -q

test-integration: ## needs infra-up + migrate
	$(PY) -m pytest tests/integration tests/security -q

test-e2e:         ## needs infra-up + migrate (boots its own API)
	$(PY) -m pytest tests/e2e -q

lint:
	$(VENV)/ruff check .
	cd apps/web && npx eslint .

typecheck:
	$(VENV)/mypy apps/api/agora_api bridge/agora_bridge
	cd apps/web && npx tsc --noEmit

cleanup:          ## purge expired challenges/sessions + published outbox (never the ledger)
	$(PY) -m agora_api.cleanup

perf:             ## 100-connection realtime load harness (records baseline)
	$(PY) scripts/load_harness.py

audit:            ## dependency security scan
	$(VENV)/pip-audit -r requirements.txt
	cd apps/web && npm audit --audit-level=high

teardown:         ## stop everything and remove volumes (destroys local data)
	$(COMPOSE) down -v
