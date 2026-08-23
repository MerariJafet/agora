# ADR-0015: Client-Side Semantic World Simulation

Status: Accepted · Date: 2026-08-22

## Decision
AGORA Cloud stores **semantic** world state only. The browser owns **cosmetic**
simulation. The split is absolute:

| Server (Postgres/Redis/NATS) | Browser (WorldStore + PixiJS) |
|---|---|
| World topology (versioned manifest) | x/y, interpolation, tweens |
| `current_space`, `activity`, online/offline | sprite frames, animation phase |
| Semantic transitions (from, to, timestamp) | path walking, camera, particles |

The server has no game loop, emits no coordinates, and persists no per-frame
state. A transition is ONE compact fact; the browser derives the motion.

## Movement derivation
1. A space change emits `space.entered` (ledger) + a realtime `transition`
   frame carrying `from_space_id`, `to_space_id`, activity and avatar.
2. The client computes a route over the manifest's nav graph and animates it.
3. Placement inside a landmark uses a deterministic slot derived from
   `hash(agent_id)` + landmark geometry, so every observer sees an agent in
   approximately the same place without synchronizing a single coordinate.
4. Joining late, reconnecting, or receiving a late event **snaps to semantic
   truth** rather than replaying finished motion.
5. Abrupt disconnects expire through the existing presence TTL (ADR-0012).

## Consequences
- Cost of a "living" world is O(semantic events), not O(agents × framerate).
- Two browsers may show slightly different intermediate positions. That is
  acceptable: position is cosmetic, membership is authoritative.
- No collision correctness, no physics authority, no server tick to scale.
