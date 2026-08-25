#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="${AGORA_TEST_RUN_ID:-$(date +%Y%m%d%H%M%S)-$RANDOM}"
DB_NAME="agora_test_${RUN_ID//[^A-Za-z0-9_]/_}"
POSTGRES_CONTAINER="${AGORA_TEST_POSTGRES_CONTAINER:-agora-dev-postgres-1}"
REDIS_CONTAINER="${AGORA_TEST_REDIS_CONTAINER:-agora-dev-redis-1}"

if [[ "$DB_NAME" != agora_test_* ]]; then
  echo "refusing unsafe database name: $DB_NAME" >&2
  exit 2
fi

cleanup() {
  docker exec "$POSTGRES_CONTAINER" psql -U agora -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME';" \
    -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" >/dev/null
}
trap cleanup EXIT

docker exec "$POSTGRES_CONTAINER" psql -U agora -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS \"$DB_NAME\";" \
  -c "CREATE DATABASE \"$DB_NAME\" OWNER agora;" >/dev/null

export AGORA_ENV=test
export AGORA_ENVIRONMENT_ID="isolated-local"
export AGORA_RUN_ID="$RUN_ID"
export AGORA_PROVENANCE_CLASS=test
export AGORA_DATABASE_URL="postgresql+asyncpg://agora:agora_dev_password@localhost:5434/$DB_NAME"
export AGORA_REDIS_URL="${AGORA_TEST_REDIS_URL:-redis://localhost:6380/15}"
export AGORA_NATS_URL="${AGORA_TEST_NATS_URL:-nats://localhost:4222}"
export AGORA_OUTBOX_ENABLED=false
export AGORA_ARTIFACT_STORE_ROOT="$(mktemp -d -t agora-test-artifacts-XXXXXX)"

docker exec "$REDIS_CONTAINER" redis-cli -n 15 FLUSHDB >/dev/null

cd "$ROOT"
.venv/bin/alembic -c apps/api/alembic.ini upgrade head
.venv/bin/pytest "$@"
