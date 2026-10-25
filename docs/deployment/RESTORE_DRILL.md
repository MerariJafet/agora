# Restore drill

`infra/deploy/sandbox/restore_drill.sh` restores the newest daily dump
(`/opt/backups/daily/agora-sandbox-agora-postgres-1_*.dump`, written 03:15 UTC
by `/opt/backups/bin/db-backup.sh`, 7-day rotation) into a throwaway
`postgres:16` container with **no network**, compares the alembic revision and
per-table row counts with the live database using read-only `SELECT`s, and
deletes the container. It never touches the live database or its volume.

```bash
sudo infra/deploy/sandbox/restore_drill.sh            # newest dump
sudo infra/deploy/sandbox/restore_drill.sh /path.dump # a specific one
```

Run it monthly and after any change to the backup job.

## Evidence — 2026-10-25 (puwpy-staging)

| Measure | Value |
|---|---|
| Dump | `agora-sandbox-agora-postgres-1_2026-10-25.dump` (20 MB) |
| Restore time (RTO for the database) | **14 s** |
| Alembic revision live / restored | `0046_validator_package_snapshot` / same |
| Tables live / restored | 149 / 149 |
| Rows restored | 455,884 |
| Row drift since the 03:15 backup | 6 tables, ≤ 48 rows each (world clock and forum activity after the dump) |
| Verdict | **PASS** (RPO ≤ 24 h) |

Not covered yet: the artifact volume (`agora-sandbox_agora_artifacts`) is not
in the daily dump; content-addressed artifacts are re-verifiable but not
backed up off the VM. Off-VM copies need a storage decision (no paid service
was added).
