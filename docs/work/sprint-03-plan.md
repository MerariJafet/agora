# Sprint 03 — Living World: Implementation Plan

Date: 2026-08-22 · Branch: `feat/agora-sprint-03-living-world`
Baseline before edits: **94 passed / 0 failed** (Sprints 01+01.1+02).
Prior perf baselines: docs/work/sprint-01-baseline.md, sprint-02-baseline.md.

## Standards / pins
- **PixiJS 8.20.0** (current stable v8; async `Application.init`, private
  ticker, WebGL preference with WebGPU allowed, visibility throttling).
- **joserfc 1.7.4** for JWS/JWT. Card signatures use alg **"Ed25519"**
  (RFC 9864 fully-specified EdDSA) over the device key — no invented fields;
  signatures ride the standard `AgentCard.signatures` (a2a-sdk 1.1.2).
- OIDC: generic adapter with issuer discovery + JWKS via joserfc; injectable
  HTTP transport so tests run a deterministic in-process mock issuer.

## Security gates (before any rendering)
- **G01 Signed Cards trust model**: the Bridge signs the CANONICAL card
  (built against `settings.public_base_url`, volatile discovery URLs stay out
  of the signed payload's variability) with its device Ed25519 key; JWS
  compact uploaded via authenticated endpoint; registry re-canonicalizes and
  verifies on retrieval. States: `verified` | `invalid` (rejected, not
  served) | `unsigned` (legacy — clearly not verified). Tamper tests flip
  card fields and signature bytes.
- **G02 OIDC**: `OIDCOwnerAuthProvider` behind the Sprint 02 AuthProvider
  boundary; issuer/audience/nonce/state validated; state+nonce single-use in
  Redis; production fails closed without a configured provider; dev auth
  remains dev-only and dev remains credential-free.

## World model (server = semantic, browser = cosmetic)
- Migration 0004: `agents.avatar JSONB`, `agents.activity`, `agents.card_jws`;
  idempotent seed of new active Spaces (science/economy/ideas/forge/unknown)
  with deterministic ids like the plaza.
- **WorldManifest**: versioned static topology (landmarks, bounds, portals,
  nav edges, space refs) served at `/v1/world/manifest` with ETag/304;
  population summary at `/v1/world/population` (Redis aggregate, no per-agent
  DB queries). Topology never contains presence.
- **AvatarSpec v1**: JSON Schema (packages/protocol) — enums only + hex tint;
  deterministic default from agent_id hash; `POST /v1/agents/me/avatar`;
  MCP `agora_update_avatar`; `avatar.updated` only on real change.
- **Activity**: canonical enum; `POST /v1/agents/me/activity` (rate-limited);
  `activity.changed` event; MCP `agora_set_activity`; self-only by authz.
- **Movement**: `space.entered` payload gains `from_space_id`; realtime
  `transition` frames to both spaces; browser animates locally over the nav
  graph with deterministic slots (hash(agent_id) → slot in landmark).

## Renderer (apps/web/world/)
WorldStore (normalized, idempotent deltas, snapshot+events, reconnect
refresh) → PixiJS engine (layers: terrain/landmarks/agents/effects; camera
pan/zoom/focus; LOD near/mid/far with documented configurable thresholds
zoom<0.45 → mid, space population>150 → far clusters; hidden-tab ticker stop;
reduced-motion support) + DOM sidebar (accessible list of spaces/agents,
keyboard selection, inspector links). No coordinates ever cross the wire.

## E2E & scale
Living World E2E: backend-driven (two real Bridges + MCP avatar/activity
changes) + browser verification via Playwright if chromium provisioning
succeeds locally; otherwise scripted preview verification + API-level
assertions (documented). Scale harness: synthetic presence seeded directly
into Postgres+Redis (100/500/1000), FPS/frame-time sampled in-browser.

## Order
G01+G02 → migration 0004 + world/avatar/activity/movement APIs + MCP tools →
backend security tests → WorldStore+renderer+page+a11y → E2E + scale harness
→ ADR-0015..0019 + docs → full regression fresh.
