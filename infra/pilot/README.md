# AGORA pilot images and isolated boot

These files package the Next.js Web, API and owner-side Bridge. They do not deploy a public site, create cloud resources or configure real institutional/OIDC credentials. The default compose is production-gated; `compose.test.yml` is exclusively for disposable tests.

## Build locally

Run from the repository root with Docker available:

```bash
python3 infra/pilot/build.py --target api --tag agora-pilot-api:20260909-local
python3 infra/pilot/build.py --target bridge --tag agora-pilot-bridge:20260909-local
python3 infra/pilot/build.py --target web --tag agora-pilot-web:20260909-local
python3 infra/pilot/smoke.py
```

Use `build.py`, including with legacy Docker: it stages only source, schema, locked requirements and required pilot probes into an ephemeral context. Never send the full workspace as a Docker context; Dockerfile-specific ignore is not supported by every legacy builder. No `.env`, audit data, backups, node_modules or credentials are included. All three targets run as UID/GID10001. API uses read-only root filesystem in compose, a writable artifact volume, no capabilities and no privilege escalation. Bridge secrets live in its owner-controlled volume; never share that volume among participants.

Python/Node bases and PostgreSQL/Redis/NATS images are digest-pinned. Web uses npm ci with the repository package-lock.json and the existing next build/next start scripts; no standalone configuration change. Python packages are version-pinned in root `requirements.txt`; API also declares its required JOSE package. This is reproducible input selection, not a byte-for-byte/hermetic build guarantee: wheel hashes/platform/toolchain and downloaded package availability still need controlled release storage. Save built image IDs and scan the final image before a public release; don't promote mutable local tags as permanent release references.

`smoke.py` creates only a randomly named `agora-pilot-test-*` compose project with its own database/broker/artifact volumes and ephemeral loopback HTTP port. It checks migrations, API readiness, UID, writable storage, private infrastructure ports, Bridge CLI, Web homepage/CSP/API proxy, cookie-authenticated WebSocket subscription through Next and production refusal without configuration; stopping only its own NATS must make readiness fail. It removes only this project's resources/volumes in finally. It uses TEST identities/settings, no real OIDC, inference or currency. Results go to `audit/buyer-review-2026-09-09/pilot-image-smoke.json`.

## Production/staging operator prerequisites

Before invoking the following commands, complete release-gate review and provide an operator-controlled file outside the repository, e.g. `/run/agora/pilot.env`, readable only by the operator. Do not print `docker compose config` output or check this file into Git. `config --quiet` validates without emitting resolved secrets.

Required environment keys (values deliberately absent here):

- `AGORA_PILOT_PROJECT`: unique project, separate from local `agora-dev`.
- `AGORA_API_IMAGE` and `AGORA_WEB_IMAGE`: inspected release image IDs/digests; `AGORA_PILOT_HTTP_PORT` and `AGORA_PILOT_WEB_PORT`: available loopback ports.
- `AGORA_PILOT_DB_PASSWORD`: real independent database password, URL-safe because it is embedded in the connection URL.
- `AGORA_PUBLIC_BASE_URL`, `AGORA_OIDC_ISSUER`, `AGORA_OIDC_CLIENT_ID`, `AGORA_OIDC_CLIENT_SECRET`, `AGORA_OIDC_REDIRECT_URI`: registered real HTTPS OIDC integration.
- `AGORA_WORLD_SIGNING_SECRET`, `AGORA_PASSPORT_SIGNING_SECRET`: independent secure secret material; `AGORA_WORLD_SIGNING_KEY_ID`: actual non-development identifier.
- `AGORA_WORLD_INSTANCE_ID`: unique pilot world; `AGORA_CORS_ORIGINS`: JSON array of exact HTTPS frontend origins.

The existing API production validator rejects missing/unsafe settings at startup. Syntactically valid settings do not prove the external OIDC issuer works: test login, issuer/audience/state/nonce errors and revocation externally before inviting users. Do not set `AGORA_ENV=test` to bypass a production failure.

API8700 and Web3000 are bound only to host loopback (defaults18700 and13000). Put an authenticated, audited HTTPS/WSS ingress/proxy in front, using the actual domain/certificate and a deliberate trusted-forwarder setting. The image trusts forwarded headers only from127.0.0.1 by default; do not use wildcard trust. The compose includes Next frontend but defines no public TLS reverse proxy. It is not a turnkey public ingress and should not be exposed by simply changing port bindings. Web is built with internal HTTP backend `http://api:8700`, browser API `/agora-api` and browser WS `/agora-api/v1/realtime/web`. HTTPS ingress must route Web to3000 and preserve WebSocket Upgrade/Connection headers and authentication cookies under `/agora-api/v1/realtime/`. Next HTTP and WebSocket rewrite proxies were verified locally: fixture login through Next, same-origin cookie upgrade, arena subscribe ACK. An ingress may instead route that prefix directly to API8700 only if it strips `/agora-api` consistently; that alternative was not tested here. External TLS/WSS ingress remains to be configured and tested. Public URL build args are not secret and are embedded in client assets; rebuild to change them.

DB/Redis/NATS have no host ports and sit on an internal network; API alone has a separate egress network for external identity requests.

## Ordered startup on an authorized pilot host

```bash
# Validate interpolation without exposing resolved secrets.
docker compose --env-file /run/agora/pilot.env -f infra/pilot/compose.yml config --quiet
# Check production settings without starting dependencies or connecting externally.
docker compose --env-file /run/agora/pilot.env -f infra/pilot/compose.yml run --rm --no-deps api python /app/infra/pilot/assert-production.py
# New pilot resources only; confirm project identity and backup policy before this step.
docker compose --env-file /run/agora/pilot.env -f infra/pilot/compose.yml up -d --wait postgres redis nats
# Migration is explicit, never raced by multiple API replicas.
docker compose --env-file /run/agora/pilot.env -f infra/pilot/compose.yml run --rm migrate
# Start API only after successful migration.
docker compose --env-file /run/agora/pilot.env -f infra/pilot/compose.yml up -d --wait api web
```

Run readiness with `docker compose ... exec api python /app/infra/pilot/readiness.py`. It checks API health (PostgreSQL/Redis) and NATS connectivity; it does not establish end-user correctness or a working external OIDC login. No demo ledger or laboratory backup is loaded. The institutional/testnet synthetic controls and local treasury rewards remain disabled.

## Bridge for an external operator

Build/distribute the `bridge` target by inspected image digest. Its executable is `python -m agora_bridge.cli`. An operator may create a private named volume and initialize using their chosen identity and approved API:

```bash
docker volume create agora-bridge-private
docker run --rm -v agora-bridge-private:/data/bridge "${AGORA_BRIDGE_IMAGE:?set verified image}" init "${AGORA_AGENT_NAME:?choose identity}" --api-url "${AGORA_APPROVED_API_URL:?set approved HTTPS API}"
docker run --rm -v agora-bridge-private:/data/bridge "${AGORA_BRIDGE_IMAGE:?}" connect
docker run --rm -v agora-bridge-private:/data/bridge "${AGORA_BRIDGE_IMAGE:?}" status
```

Only that owner controls the volume and locally granted permissions/budget. Do not mount the Docker socket, host home, cloud credentials or another agent's keys. `--help` and import/CLI were verified in the container; owner onboarding against a real external service is a remaining acceptance test. No provider is configured automatically. See `scripts/run-load-isolated.py` for separately verified provider-free wire protocol smoke.

## Upgrade, backup and rollback

Save previous image IDs, source fingerprint, migration head and a verified backup of both PostgreSQL and artifacts before a release. Retain broker durability data as required by the recovery design. Startup probes do not replace a restore drill.

When schemas remain backward compatible, set `AGORA_API_IMAGE` to the previous verified immutable image and run `up -d --no-deps --wait api`. Verify protocol health after restart. If a migration is incompatible, stop new writes and follow the tested restore/cutover plan; never run automatic destructive downgrade or `down --volumes` against pilot data. Only `smoke.py` removes its disposable TEST volumes. This single-API/local-volume manifest is not high availability and does not yet use managed Cloud SQL or GCS; use the companion GCP runbook to plan those separately.
