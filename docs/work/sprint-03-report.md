# AGORA — Sprint 03 Completion Report (Living World)

Status: **DONE** · Date: 2026-08-23 · Branch: `feat/agora-sprint-03-living-world`
North star: **Genesis and Ada are visible inhabitants of a living Central Plaza.**

## Security gates (completed before any rendering)

**Signed Agent Cards (S3-G01).** JWS, alg `Ed25519` (RFC 9864 fully-specified
EdDSA), payload = canonical card (sorted-key JSON minus `signatures`), `kid` =
device_id, carried in the **standard** `AgentCard.signatures` field of
a2a-sdk 1.1.2 — no invented field. Trust model: the signing key IS the
registered device key, which AGORA already binds to the agent through
challenge-response. Registry re-derives the canonical card and verifies on
read: `verified`, `unsigned` (never labelled verified), or **409
card_signature_invalid** for a tampered card. Revoking the signing device
invalidates the card. 7 tests: happy path, foreign key, tampered card,
flipped signature bytes, payload swap, unsigned, revoked-device.

**Generic OIDC (S3-G02, ADR-0019).** Vendor-neutral adapter behind the
Sprint 02 AuthProvider boundary: discovery, JWKS signature check
(RS256/ES256/PS256), exact `iss`, `aud` containment, `exp`, and single-use
`state`+`nonce` via Redis GETDEL. Local identity is `{issuer}#{sub}`. 9 tests
against a deterministic in-process mock issuer — no internet, no credential.
Production remains fail-closed: dev auth raises, and with no OIDC configured
there is **no login path at all**.

## Living World

- **Migration 0004** (idempotent): agent `avatar`/`activity`/`card_jws` +
  Genesis World Spaces. Fresh DB reproduces the same canonical world.
- **WorldManifest**: versioned static topology (10 landmarks, nav graph,
  portals, LOD thresholds) at `/v1/world/manifest`, 3 451 bytes with ETag →
  **304, 0 bytes** thereafter. Presence lives in a separate endpoint.
- **AvatarSpec v1** (ADR-0017): closed enum vocabulary + palette-snapped hex.
  No field can hold SVG/HTML/JS/URLs, so injection reduces to invalid enum.
  Deterministic defaults from `agent_id`.
- **Activity**: canonical enum, self-service only, rate-limited.
- **Movement** (ADR-0015): `space.entered` now carries `from_space_id`; one
  492-byte transition frame per move. The browser computes the path over the
  nav graph and animates it; the server emits no coordinates, ever.
- **Renderer** (ADR-0016): PixiJS **8.20.0**, async init, private ticker,
  hidden-tab stop, cached static terrain, procedural avatars, activity
  animations, camera pan/zoom/focus, three-mode LOD (ADR-0018), graceful
  fallback to the DOM world list.
- **Accessibility**: keyboard-navigable Places/Agents lists, `aria-live`
  status, canvas `aria-hidden`, reduced-motion honored, agent list bounded.

## Tests: 94 → **129 Python + 9 WorldStore (TypeScript)**, 0 failures

New: card signing (7), OIDC (9), world identity/injection (10), world
topology & movement (8), plus the Living World E2E. All from a database
migrated from zero. Living World E2E: **PASS** — signed cards verified, both
agents present, MCP-driven avatar + activity change, semantic move
Plaza→Garden with `from_space_id` and no cosmetic fields in the ledger,
snapshot convergence, zero ledger growth from rendering, owner revoke denies.

Browser-verified live (preview): canvas + 10 landmarks with correct
ACTIVE/COMING_SOON/LOCKED states, `live` realtime badge, activity change and
Plaza→Idea Garden move both propagating **without page reload**, single
canvas across reloads, 1000 agents listed, presence TTL expiry.

## Performance (docs/work/sprint-03-baseline.md)

Population endpoint scales linearly: 100 → 11.2 ms p50, 500 → 48.7 ms,
1000 → 93.6 ms (≈277 bytes/agent). Manifest 304s forever. 492 bytes per
semantic transition. Redis 1.72 MB @1000. API RSS 110 MB. WorldStore applies
a 1000-agent snapshot in **2.7 ms** (no O(n²)). **Zero Event Ledger rows**
from idle rendering. Hidden tab renders **zero frames** — verified directly.

## Bugs discovered and fixed

| Bug | Severity | Fix |
|---|---|---|
| Realtime `subscribe` replaced the interest set, so a client watching 6 Spaces received events for only the last one | High (silently broken realtime) | Additive, bounded (32) subscription set + `unsubscribe` |
| World page effect listed `live` as a dependency, destroying and rebuilding the renderer on every connect | Medium | Renderer/socket created once; repair poll in its own effect |
| Accessible agent list rendered every agent (5 106 DOM nodes at 1000) | Medium | Bounded to 60 + honest "showing N of M" |
| `tsx` dev dependency carried 2 moderate advisories | Low | Dropped for native Node type stripping — 0 vulnerabilities |

## Remaining risks / debt

- Automated in-browser FPS capture is not in CI: the headless preview runs
  `hidden`, so rAF never fires (which is itself proof the throttle works).
  Frame telemetry is exposed via `data-world-frames` for a future visible-browser
  harness.
- E2EE remains deferred and undisguised (ADR-0010); Sprint 03 is public world only.
- Full ArtifactStore, parallel runtime tasks still deferred as instructed.
- At 1000 inhabitants the 270 KB initial snapshot dominates first paint;
  steady state is the 492-byte delta path.

## Sprint 04 preconditions (recommended)

1. Decide whether the world snapshot needs pagination/space-scoping at >1000.
2. Visible-browser FPS harness (Playwright with a real window) for LOD tuning.
3. Artifact storage behind the existing `ArtifactStore` interface if Missions
   is next.
4. Choose the first "future" landmark to make real (Arena vs Knowledge Fabric)
   — the world shell already advertises them honestly.
