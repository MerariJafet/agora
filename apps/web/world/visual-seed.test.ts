import assert from "node:assert/strict";
import { test } from "node:test";
import type { Mission } from "@/lib/missions";
import { messageToEvent } from "./observatory.ts";
import { syntheticSnapshot, testManifest, TEST_GARDEN } from "./store.test-fixtures.ts";
import { WorldStore } from "./store.ts";
import { buildVisualWorldManifest, visualSeed } from "./visual-seed.ts";

function mission(overrides: Partial<Mission> = {}): Mission {
  return {
    mission_id: "mis_visual",
    title: "Challenge tower",
    objective: "Build a visible proof structure.",
    description: null,
    state: "active",
    visibility: "public",
    hosting_space_id: TEST_GARDEN,
    related_debate_id: null,
    deadline_at: null,
    reward_aceros: 100_000_000,
    challenge_kind: "test",
    challenge_problem: null,
    challenge_space_color: null,
    resolution_policy: null,
    winning_submission_id: null,
    resolved_by_agent_id: null,
    max_participants: 16,
    completion_policy: {},
    created_by_agent_id: "agt_creator",
    final_artifact_version_ids: null,
    created_at: "2026-09-05T00:00:00Z",
    activated_at: null,
    completed_at: null,
    resolved_at: null,
    ...overrides,
  };
}

test("visual seeds are deterministic for the same world entity and ruleset", () => {
  const first = visualSeed({
    worldInstanceId: "world_real",
    entityId: "challenge_a",
    rulesetVersion: "rules.v1",
  });
  const second = visualSeed({
    worldInstanceId: "world_real",
    entityId: "challenge_a",
    rulesetVersion: "rules.v1",
  });
  const changed = visualSeed({
    worldInstanceId: "world_real",
    entityId: "challenge_b",
    rulesetVersion: "rules.v1",
  });

  assert.equal(first, second);
  assert.notEqual(first, changed);
});

test("visual world manifest projects real semantic state into constructions", () => {
  const store = new WorldStore();
  const manifest = testManifest();
  store.setManifest(manifest);
  store.applySnapshot(syntheticSnapshot(3, TEST_GARDEN));
  const agents = [...store.agents.values()];
  const events = [messageToEvent({
    message_id: "msg_1",
    space_id: TEST_GARDEN,
    agent_id: agents[0]!.agent_id,
    agent_name: agents[0]!.name,
    content: "Public progress",
    created_at: "2026-09-05T00:00:00Z",
  }, "Idea Garden")];

  const visual = buildVisualWorldManifest({
    worldInstanceId: "world_real",
    worldVersion: manifest.world_version,
    rulesetVersion: "rules.v1",
    landmarks: manifest.landmarks,
    agents,
    missions: [mission()],
    events,
  });

  const garden = visual.districts.find((district) => district.id === "ideas");
  assert.equal(visual.schema_version, "visual-world-manifest.v1");
  assert.equal(garden?.population, 3);
  assert.equal(garden?.constructions.length, 2);
  assert.equal(garden?.constructions[1]?.stage, "working");
  assert.equal(garden?.constructions[1]?.provenance.facts_only, true);
  assert.deepEqual(visual.social_clusters[0], {
    space_id: TEST_GARDEN,
    participant_count: 3,
    recent_messages: 1,
  });
});

test("future and locked landmarks remain honest visual states", () => {
  const manifest = testManifest();
  const visual = buildVisualWorldManifest({
    worldInstanceId: "world_real",
    worldVersion: manifest.world_version,
    rulesetVersion: "rules.v1",
    landmarks: manifest.landmarks,
    agents: [],
    missions: [],
    events: [],
  });

  const frontier = visual.districts.find((district) => district.id === "frontier");
  assert.equal(frontier?.constructions[0]?.stage, "incomplete");
});
