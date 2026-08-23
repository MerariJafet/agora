# ADR-0016: PixiJS World Renderer

Status: Accepted · Date: 2026-08-22

## Decision
The world canvas uses **PixiJS 8.20.0** (pinned), initialized asynchronously
(`await app.init(...)`, required in v8) inside `apps/web/world/engine.ts`.

Operational rules:
- `preference: "webgl"` as the broad-compatibility baseline; Pixi selects a
  supported backend and the page falls back to the DOM world list if
  initialization fails at all.
- **Private ticker** (`sharedTicker: false`) — the engine decides when frames
  happen; nothing global can drive or starve it.
- `visibilitychange` stops the ticker on hidden tabs and restarts on return.
- Static terrain/nav-graph is `cacheAsTexture(true)` — it never changes, so
  it is rasterized once instead of re-stroked every frame.
- Interactive nearby agents stay regular `Container`s so they remain
  hit-testable and inspectable. High-volume representations are aggregate
  cluster graphics (see ADR-0018), not individually interactive sprites.
- React owns all panels, text and controls; the canvas is `aria-hidden` and
  the DOM sidebar is the accessible surface (S3-T21).
- The engine is destroyed on unmount and replaces the canvas host's children
  on init, so hot reload cannot accumulate canvases.

## Consequences
- Rendering is pure output: the engine never fetches, posts or mutates
  authoritative state.
- Pinning a major.minor.patch keeps v8 API assumptions (async init, Graphics
  API shape) stable; upgrades require re-verifying those two.
