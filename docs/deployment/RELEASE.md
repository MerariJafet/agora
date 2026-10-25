# Pilot releases: one commit, provably served

Before 2026-10: releases were copied by hand into `/opt/agora-releases/<name>`
with a hand-written `receipt.json`, `/healthz` did not say which commit was
running, and `/opt/agora` (the original checkout used by `deploy.sh`) drifted
18 commits behind while looking like production.

Now:

| Step | Where |
|---|---|
| First install (env file, network, certificate, vhost) | `infra/deploy/sandbox/deploy.sh` (bootstrap only) |
| Every deploy | `sudo infra/deploy/sandbox/release.sh <git-ref>` |
| What is serving | `curl -s https://agora.datateologica.com/healthz` → `build.sha`, `build.release` |
| Evidence | `/opt/agora-releases/<date>-<sha12>.receipt.json` (written by the script) |
| Pre-migration backup | `/opt/agora-backups/<date>-<sha12>/pre-release.dump` |
| Rollback | `release.sh <previous sha>`; restore the dump only if a migration must be undone |

`release.sh` extracts the commit with `git archive` (no working copy, so no
edits can sneak into production), passes `AGORA_BUILD_SHA`/`AGORA_RELEASE_ID`
to the API, and refuses to report success until `/healthz` inside the
container returns the same sha. Run with `--dry-run` first.

Known limit: the stack still runs stock `python:3.12-slim` / `node:22-slim`
images with the release mounted, so dependencies install at boot and the web
rebuilds on each release (a few minutes of web downtime). Prebuilt, tagged
images are the next step once a registry is chosen (none is paid for today).

The legacy `/opt/agora` checkout is not used by the running stack; it can be
removed once the first `release.sh` deploy is verified (owner approval).
