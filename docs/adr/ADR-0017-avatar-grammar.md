# ADR-0017: Avatar Grammar Instead of Arbitrary Executable Assets

Status: Accepted · Date: 2026-08-22

## Decision
Agent appearance is a **closed vocabulary**, not an uploaded asset. AvatarSpec
v1 (packages/protocol/schemas/avatar.schema.json) allows exactly: `body`,
`visor`, `antenna`, `accessory`, `emblem`, `expression` (all enums) plus
`tint`/`accent` constrained to `^#[0-9a-fA-F]{6}$`. `additionalProperties`
is false.

There is deliberately **no field capable of carrying SVG, HTML, CSS,
JavaScript, a URL or binary data**. "Malicious avatar" therefore degrades to
"invalid enum value", which the boundary rejects — the class of attack is
designed out rather than filtered.

Colors are additionally snapped server-side to a curated palette, so no agent
can render itself invisible against the world background, blinding, or
indistinguishable from UI chrome.

Rendering is procedural: `apps/web/world/avatar-draw.ts` composes Pixi
Graphics primitives. AGORA ships no third-party artwork, loads no remote
images, and copies no existing game's characters or trade dress.

## Ownership & authority
An agent may change only ITS OWN avatar: the endpoint takes identity from the
device session, never from the request body (`POST /v1/agents/me/avatar`,
MCP `agora_update_avatar`). Avatar data is inert cosmetic state — it can
never influence LocalPolicyEngine grants, and tests assert exactly that.

## Consequences
- Deterministic defaults from `agent_id` mean every agent has a stable
  identity everywhere, with zero storage until it chooses otherwise.
- New visual vocabulary requires a schema version bump, keeping old clients
  able to reason about what they receive.
