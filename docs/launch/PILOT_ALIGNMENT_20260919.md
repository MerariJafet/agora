# Pilot alignment release — 19 September 2026

This release aligns the public application with the tested runtime and validator-owner safeguards. It does not authorize a public cryptocurrency, economic native testnet, institutional impersonation or recognition of TEST balances in genesis. Previous monetary NO-GO reports remain applicable to those targets.

Changes: rules compatibility is wired into the runtime; control envelopes cannot fall back into public chat; Next.js page exports build cleanly; wallet readiness tests are independent of the founder's folders; validator recommendations require owner approval and cannot erase a declared conflict or reopen a closed candidate. Migration 0042 adds proposal/decision records and owner binding; 0045 joins the migration branches. Existing balances and research history are preserved.

Production keeps synthetic-validator, institutional-registry and TOKOIN local control planes disabled. The synthetic review context still includes current conversation data: concurrent messages may invalidate its hash. This known availability limitation requires a persisted package snapshot before claiming reliable unattended synthetic reviews in an active world. It is not solved by approving or refreshing an unseen hash.

Deployment requirements: green CI at the exact candidate SHA, private PostgreSQL backup successfully restored to a separate database, migration tested on that restore, and previous release available. Prefer code rollback with the additive schema retained; do not downgrade away recorded owner decisions. The deployment receipt records source SHA, schema head, health and non-mutating public checks.

The public SQL ledger, its optional block sealing and the native TEST chain are different systems. Do not enable sealing, alter balances or bypass institutional gates as an incidental deployment step. Monitor pending entries and investigate the intended sealing policy separately.

Release approvals are host-local source-bound records. `pass.json` is intentionally no longer tracked, preventing an old approval from being shipped as reusable source and preventing the approval file from changing its own source fingerprint. Historical gate reports remain committed. A new approval is produced only after checks for its stated target; this change grants no approval by itself.

Editorial corrections are documented in [the dated erratum](../paper/ERRATA_20260919.md). The archived Zenodo v0.3 artifacts and scientific measurements are not rewritten.
