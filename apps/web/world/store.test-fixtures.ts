// Deterministic fixtures shared by world unit tests and the scale harness.
// Keeping them in one place means the harness measures the same shapes the
// tests assert on.

import type { WorldSnapshot } from "./store.ts";
import type { Activity, AvatarSpec, Landmark, WorldManifest } from "./types.ts";

export const TEST_PLAZA = "spc_00000000000000000000P1AZA0";
export const TEST_GARDEN = "spc_00000000000000000000GARDEN";

export function testAvatar(tint = "#4ac48a"): AvatarSpec {
  return {
    schema_version: "1.0",
    body: "orb",
    visor: "round",
    antenna: "none",
    accessory: "none",
    emblem: "none",
    expression: "neutral",
    tint,
  };
}

const landmark = (
  id: string, name: string, spaceId: string | null, x: number, y: number,
  state: Landmark["state"] = "ACTIVE",
): Landmark => ({
  id, name, state, space_id: spaceId, purpose: `${name} purpose`,
  shape: "district", x, y, radius: 190,
});

export function testManifest(): WorldManifest {
  return {
    world_version: "1.0.0",
    name: "AGORA Genesis World",
    bounds: { min_x: -1300, min_y: -900, max_x: 1300, max_y: 1300 },
    landmarks: [
      { ...landmark("central", "Central Plaza", TEST_PLAZA, 0, 0), radius: 260 },
      landmark("ideas", "Idea Garden", TEST_GARDEN, -620, 340),
      landmark("frontier", "Community Frontier", null, 0, 980, "LOCKED"),
    ],
    portals: [{ id: "portal-central-ideas", from: "central", to: "ideas" }],
    nav_edges: [["central", "ideas"]],
    lod: { mid_zoom_below: 0.45, far_zoom_below: 0.22, cluster_population_above: 150 },
  };
}

const ACTIVITY_CYCLE: Activity[] = ["idle", "reading", "discussing", "researching"];

export function syntheticSnapshot(count: number, spaceId = TEST_PLAZA): WorldSnapshot {
  return {
    spaces: {
      [spaceId]: {
        count,
        agents: Array.from({ length: count }, (_, i) => ({
          agent_id: `agt_${String(i).padStart(26, "0")}`,
          name: `Synthetic-${i}`,
          activity: ACTIVITY_CYCLE[i % ACTIVITY_CYCLE.length] ?? "idle",
          avatar: testAvatar(),
        })),
      },
    },
    total_present: count,
  };
}
