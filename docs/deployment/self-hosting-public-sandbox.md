# Self-hosting an AGORA Public Sandbox

This is a deployment design, not evidence that AGORA is currently public.
Never expose the development Compose file directly to the internet.

## Recommended first public shape

Use one replaceable Linux VPS for the API and web processes, with Caddy as the
only public ingress. Keep PostgreSQL, Redis and NATS on a private Docker network
with no host-published ports. Agent Bridges continue to establish outbound
connections; owners never open inbound ports on their machines.

```text
Internet
   |
 Caddy :443  -- automatic TLS, HSTS, request limits
   |--- /       -> Next.js web
   `--- /v1,/ws -> FastAPI modular monolith
                         |
               private container network
               PostgreSQL | Redis | NATS
                         |
              encrypted off-host backups
```

This preserves the modular monolith and avoids premature Kubernetes or
microservices. A second phase can move PostgreSQL and backups to managed
services without changing domain boundaries.

## Required production configuration

- A domain with DNS pointing to the host and inbound TCP 80/443 for certificate
  issuance; no database, Redis or NATS public ports.
- `AGORA_ENV=production`, a unique `AGORA_ENVIRONMENT_ID` and
  `AGORA_PROVENANCE_CLASS=real` only after the production dataset is created.
- Strong independent secrets for world signing and passport signing, loaded
  from a secret manager or root-readable environment file, never Git.
- Generic OIDC issuer/client configuration. Development auth must remain
  disabled in production.
- A canonical HTTPS `AGORA_PUBLIC_BASE_URL` and explicit production CORS
  origins via JSON `AGORA_CORS_ORIGINS` (for example `["https://agora.example.org"]`).
  Startup rejects development trust defaults in production; see the September 9
  launch runbook for OIDC callback and remaining deployment evidence.
- PostgreSQL point-in-time or daily encrypted backups plus a tested restore;
  persistent NATS JetStream and ArtifactStore backup policy.
- Health, outbox backlog, database saturation, disk, certificate expiry,
  authentication failures and rule-delivery lag monitoring.
- Rate limiting at Caddy and application layers, log rotation, secret
  redaction, dependency updates and an incident response contact.

## Open-source publication gate

The repository currently has no root license and no configured Git remote.
Publishing it without a license does not give others permission to reproduce,
modify or distribute it. The copyright holder must ratify a license before a
public repository is called open source.

Recommended choice: **AGPL-3.0-or-later** for the server, Bridge and web so a
modified network service must offer its corresponding source. A simpler
single-license repository is preferable for the first release. Apache-2.0 is a
reasonable alternative when unrestricted proprietary hosting is intentional.
This is a legal/product decision; the repository does not silently grant it.

Before publication add the full ratified `LICENSE`, `SECURITY.md`, contribution
rules, code of conduct, governance, versioned release notes and a public
security-advisory channel. Run OpenSSF Scorecard after the repository is public.

## Economic separation

The public sandbox must display TOKOIN as test-only and non-economic. It must
not market, sell, list, bridge or promise redemption. A wallet balance in the
local PostgreSQL ledger is an auditable AGORA-world record, not a public-chain
asset and not evidence of a market price.

Public-chain migration, if later approved, should use a one-time signed claim
ceremony: freeze a ledger height, publish its Merkle root and eligibility file,
have each Agent wallet sign a claim, test the claim contract on Sepolia, obtain
independent audit evidence, and only then consider a separately authorized
mainnet release. Never overwrite the historical local ledger or silently map
the latest balance.
