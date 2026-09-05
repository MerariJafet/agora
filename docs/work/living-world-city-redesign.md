# AGORA Living World City Redesign

Date: 2026-09-05

## Scope

Implemented a frontend-first vertical slice of **AGORA: Ciudad del Pensamiento**.
The change keeps the existing PixiJS world and technical observatory available,
but adds a human-readable city layer that projects real AGORA state into
deterministic districts, constructions and social clusters.

## Design Decisions

- The frontend remains fact-bound: it uses observed landmarks, missions,
  semantic presence and public events. It does not invent agent activity,
  challenge progress, TOKOIN settlement or consensus.
- `apps/web/world/visual-seed.ts` introduces a deterministic Visual World
  Manifest from `world_instance_id`, entity id, ruleset version and visual
  schema version.
- The canvas label noise was reduced by truncating challenge labels and lowering
  challenge-label weight, so crowded challenge rings do not dominate the map.
- The main `/world` route now shows a `Ciudad del Pensamiento` layer with
  isometric district tiles, construction stages and social cluster summaries
  before the lower technical canvas.

## Validation

- `npm run test:world` -> 20 passed.
- `npm run typecheck` -> passed.
- `npm run lint` -> passed.
- `npm run build` -> passed.
- `curl http://127.0.0.1:8700/v1/world/manifest` returned world version `1.5.0`
  with 15 landmarks.
- `curl http://127.0.0.1:3000/world` returned the new `city-dashboard` SSR markup.

## Known Follow-up

The next step is to move more of the visual grammar into the Pixi scene itself:
true isometric camera/parallax, larger conversation staging, agent walk-toward-
speaker behavior and challenge-building interiors. This pass creates the stable
frontend contract and human-facing city surface needed for that work.
