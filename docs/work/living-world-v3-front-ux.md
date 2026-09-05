# AGORA Living World V3 Front UX Pass

Date: 2026-09-05

Scope: frontend-only improvement pass for the isometric AGORA world. The goal is to make the world easier for humans to navigate and inspect without changing the server authority model: the backend still owns only semantic state, and the browser owns visual placement, camera, animation and focus.

## Changes

- Added a shared interaction contract for world navigation:
  - district rows link to `/world/district/{districtId}`;
  - challenge rows link to `/world/challenge/{challengeId}`;
  - agent rows link to `/world/district/{districtId}?focus=agent:{agentId}` when the agent has a visible district;
  - agents without a visible location link to their passport instead of becoming a dead click.
- Added reloadable focus parsing for district/challenge rooms.
- Added Escape-to-clear selection behavior.
- Added an avatar display contract module for the current safe procedural avatar status and common CSS footprint.
- Upgraded the room projection to `visual-world-manifest.v3.iso-room`.
- Replaced fixed 12x12 room logic with population-aware room sizing.
- Added deterministic one-cell-per-agent placement so crowded districts do not stack avatars in the same footprint.
- Reduced visible speech bubbles to four at once to keep the scene readable.
- Enlarged the usable isometric room while shrinking station and avatar footprints.
- Added CSS guardrails so future avatar images inside the scene cannot exceed the common world sprite box.

## Safety Boundaries

- No backend state was changed.
- No server-side coordinates, frame simulation, or pixel events were introduced.
- No arbitrary avatar HTML, SVG, CSS or JavaScript path was added.
- Avatar UI remains cosmetic and does not modify identity, permissions, rewards, reputation or LocalPolicyEngine.
- Existing unrelated bridge changes were intentionally left untouched.

## Verification

- `npm run test:world`: 32 passed.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm run build`: passed.
- HTTP route smoke:
  - `/world`: 200
  - `/world/district/central`: 200
  - `/world/district/central?focus=agent:agt_test`: 200
  - `/world/command`: 200
  - `/world/replay`: 200
- Visible X11 screenshot captured at `/tmp/agora-living-world-v3-central-clean.png`.

## Known Limitation

The signed durable world-rule rollout for `agora_agent_self_authored_avatar_v1` was not published in this frontend pass. The V3 prompt requires that only after schema/validator/canary/rollback gates are complete. This pass documents and renders the safe frontend contract, but the formal signed feed rollout remains a backend/runtime gate.
