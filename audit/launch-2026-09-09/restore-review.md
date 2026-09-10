# AGORA database restore rehearsal — 2026-09-09

**PASS for one full local PostgreSQL backup/restore rehearsal. Production disaster recovery remains only partially verified.**

Source ownership checked: `agora` database owned by `agora` in `agora-dev-postgres-1` (PostgreSQL 16). Source size was 8,295,898,135 bytes and free local filesystem space 292 GB before operation.

## Executed procedure

1. Connected read-only under REPEATABLE READ; exported a PostgreSQL transaction snapshot with `pg_export_snapshot()`.
2. Counted each application table and captured ordered column-schema metadata in that same snapshot. Inventory contained 143 tables and 17,332,513 rows.
3. Ran `docker exec agora-dev-postgres-1 pg_dump -U agora -d agora -Fc --no-owner --snapshot=<exported snapshot>` into a newly created private temp directory outside the repository. Directory mode 0700, dump 0600. Dump contained real data and was never printed or added to the repository.
4. Closed the source read-only transaction after successful dump. Created a unique `agora_test_restore_*` database owned by the confirmed role. Piped the dump to `pg_restore --exit-on-error --no-owner` in that database only.
5. Restored successfully and independently re-read table counts and ordered column-schema metadata. Every individual table count matched; both totals were 143 tables / 17,332,513 rows. Column metadata hashes matched. No row contents, identities or credentials appear in the saved evidence.
6. Dropped only the database created by this rehearsal; deleted only its private temporary dump/directory and temporary runner. A separate PostgreSQL catalog query confirmed zero databases remaining under the exact created name.

Machine-readable evidence: `restore-checks.json`. Dump size **548,105,870 bytes**; measured end-to-end dump, restore and comparison **116.43 seconds**. Successful pg_restore includes restoration of the dump's schema/data/index definitions; the explicit comparison covered column schema and all per-table row counts, not cryptographic equality of every cell.

The live database was not modified; no Redis operation, isolated-test wrapper, restart, migration, token operation or live-write test was used. Concurrent application writes were allowed; snapshot export ensures comparison against the same logical point in time instead of drifting live counts.

## Remaining operational release gates

This proves local restore feasibility with this dataset. It does not establish off-host encrypted backups, retention/access controls, scheduled backup monitoring, recovery after host loss, measured external RPO/RTO, application/artifact-store recovery, infrastructure recreation, secrets recovery, or a full production cutover exercise. A repository search located the isolated-test DB helper, but no dedicated tracked backup/restore script; this one-off rehearsal does not create a recurring backup policy. Keep these requirements explicit before public production operation.

## Source-only redacted secret scan

Executed six signature families across **390 tracked current source/config files** (selected code/config text extensions, maximum 2 MB/file; audit/backups/vendor excluded). One candidate in a security test was inspected structurally: exactly a 27-character BEGIN PRIVATE KEY marker literal with no body or END marker, not private-key material. Confirmed credential material from these rules: **0**. Full redacted rule/scope/triage evidence: `source-secret-scan.json`.

This bounded regex scan is not an entropy scanner and does not inspect git history, ignored runtime files, historical audit evidence, arbitrary password assignments or the complete filesystem. It cannot support a claim that the repository/history contains no secrets. No secret values were printed by the scan.
