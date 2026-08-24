# Sprint 10 Runbooks

## Identity Recovery

1. Verify owner identity through the configured production AuthProvider.
2. Revoke lost device sessions before rotating keys.
3. Register a replacement device through challenge-response.
4. Publish a new signed Agent Card and archive the old signature status.

## Device Key Rotation

1. Generate a new Ed25519 key on the owner machine.
2. Authorize it with owner control; never upload old or new private keys.
3. Revoke the old device after the new device confirms realtime connectivity.

## Backup and Restore

1. Back up PostgreSQL logical dump, object-store metadata and world manifests.
2. Restore into a clean database.
3. Run Alembic to head.
4. Verify Event Ledger row count and ArtifactStore hashes.

## Local Chaos Drill

Sprint 10 drills are deterministic records, not destructive operations. They
document expected behavior for Postgres restart, Redis latency, NATS outage,
outbox redelivery, object-store outage, Knowledge source outage and 10k
synthetic realtime baseline.

## Staging Deploy

Deployment is documented but not performed. Staging must use production-like
TLS/OIDC, disabled development auth in production mode, full migrations and
smoke tests before traffic.
