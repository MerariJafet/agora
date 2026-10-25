#!/usr/bin/env bash
# Restore drill: prove the latest AGORA backup can actually be restored.
#
#   sudo infra/deploy/sandbox/restore_drill.sh [dump-file]
#
# Restores the newest /opt/backups/daily/agora-sandbox-agora-postgres-1_*.dump
# (or the given file) into a throwaway postgres:16 container with no network,
# then compares per-table row counts and the alembic revision against the live
# database (read-only SELECTs). Never touches the live database or its volume.
# Prints a JSON report; exit 1 if the restore fails or the schema revision differs.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/daily}"
LIVE_DB="${LIVE_DB:-agora-sandbox-agora-postgres-1}"
DUMP="${1:-$(ls -1t "$BACKUP_DIR"/agora-sandbox-agora-postgres-1_*.dump 2>/dev/null | head -1)}"
[ -n "$DUMP" ] && [ -f "$DUMP" ] || { echo "no AGORA dump found in $BACKUP_DIR"; exit 1; }

NAME="agora-restore-drill-$$"
cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

started=$(date +%s)
docker run -d --rm --name "$NAME" --network none --memory 512m \
  -e POSTGRES_USER=agora -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=agora postgres:16 >/dev/null
for _ in $(seq 1 60); do
  docker exec "$NAME" pg_isready -h 127.0.0.1 -U agora -d agora >/dev/null 2>&1 && break
  sleep 1
done
docker exec "$NAME" pg_isready -h 127.0.0.1 -U agora -d agora >/dev/null
# TCP readiness above only answers once the entrypoint has finished its
# socket-only init server and started the final one.

# --no-owner: the drill database has a single role; ownership is not under test.
docker exec -i "$NAME" pg_restore -U agora -d agora --no-owner --exit-on-error < "$DUMP"
restored_at=$(date +%s)

COUNT_SQL="SELECT string_agg(format('%s=%s', c.relname, c.n), ',' ORDER BY c.relname) FROM (
  SELECT relname, (xpath('/row/n/text()', query_to_xml(format('SELECT count(*) AS n FROM %I', relname), false, true, '')))[1]::text::bigint AS n
  FROM pg_stat_user_tables WHERE schemaname = 'public') c;"
REV_SQL="SELECT version_num FROM alembic_version;"

live_user=$(docker exec "$LIVE_DB" printenv POSTGRES_USER)
live_db=$(docker exec "$LIVE_DB" printenv POSTGRES_DB)
q_live() { docker exec "$LIVE_DB" psql -U "$live_user" -d "$live_db" -At -c "$1"; }
q_drill() { docker exec "$NAME" psql -U agora -d agora -At -c "$1"; }

live_rev=$(q_live "$REV_SQL"); drill_rev=$(q_drill "$REV_SQL")
live_counts=$(q_live "$COUNT_SQL"); drill_counts=$(q_drill "$COUNT_SQL")

python3 - "$DUMP" "$live_rev" "$drill_rev" "$live_counts" "$drill_counts" \
  "$((restored_at - started))" <<'PY'
import json, sys
dump, live_rev, drill_rev, live_raw, drill_raw, seconds = sys.argv[1:]
parse = lambda raw: dict(kv.split("=", 1) for kv in raw.split(",") if kv)
live, drill = parse(live_raw), parse(drill_raw)
diff = {t: {"live": int(live.get(t, -1)), "restored": int(drill.get(t, -1))}
        for t in sorted(set(live) | set(drill)) if live.get(t) != drill.get(t)}
report = {
    "dump": dump,
    "restore_seconds": int(seconds),
    "alembic_live": live_rev, "alembic_restored": drill_rev,
    "tables_live": len(live), "tables_restored": len(drill),
    "rows_restored": sum(int(v) for v in drill.values()),
    "tables_with_row_drift_since_backup": diff,
    "verdict": "PASS" if live_rev == drill_rev and len(drill) == len(live) else "FAIL",
}
print(json.dumps(report, indent=2))
sys.exit(0 if report["verdict"] == "PASS" else 1)
PY
