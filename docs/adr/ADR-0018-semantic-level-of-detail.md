# ADR-0018: Semantic Level of Detail

Status: Accepted · Date: 2026-08-22

## Decision
Three detail modes, selected from camera zoom and semantic population — never
from a simulated object count.

| Mode | Trigger (initial, configurable) | Rendering |
|---|---|---|
| Near | zoom ≥ `mid_zoom_below` (0.45) | Full procedural avatars, nameplates, activity animations, individually hit-testable |
| Mid | zoom < 0.45 | Scaled-down avatars, labels hidden, activity reduced to a single indicator dot, non-interactive |
| Far | zoom < `far_zoom_below` (0.22) | No per-agent nodes at all: one aggregate cluster per Space sized by √population, labelled with the count |

Thresholds live in the **world manifest** (`lod` block), so they are
documented, versioned and tunable without shipping a new client build.

Cluster counts derive from `WorldStore.populationBySpace()` — semantic
presence — not from counting sprites, so the far view is correct even when
nothing is rendered.

## Rationale
Nearby agents must stay individually selectable (the Inspector is the point),
so they are never moved into a representation that prevents interaction.
Distant crowds carry no interaction requirement, so they collapse into
aggregates — which is both cheaper and more readable than 1000 overlapping
dots. ParticleContainer was evaluated and NOT adopted: aggregation removes
the per-agent draw entirely, which beats making per-agent draws cheaper.

## Consequences
- Rendering cost at scale is bounded by visible landmarks, not population.
- Zooming out during a crowd surge degrades gracefully instead of stuttering.
