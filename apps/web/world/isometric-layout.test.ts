import assert from "node:assert/strict";
import { test } from "node:test";
import {
  buildIsoRoomProjection,
  constructionStageForMission,
  MAX_VISIBLE_BUBBLES,
  projectAgentsIntoRoom,
  roomSizingForPopulation,
  stationForAgent,
} from "./isometric-layout.ts";
import { testAvatar, testManifest, TEST_PLAZA } from "./store.test-fixtures.ts";
import type { Mission } from "@/lib/missions";
import type { AgentSemanticState, WorldMessageEvent } from "./types.ts";

function agent(id: string, activity: AgentSemanticState["activity"]): AgentSemanticState {
  return {
    agent_id: id,
    name: id,
    activity,
    avatar: testAvatar("#42d6bf"),
    space_id: TEST_PLAZA,
  };
}

function mission(state: Mission["state"]): Mission {
  return {
    mission_id: `mis_${state}`,
    title: `Mission ${state}`,
    objective: "test",
    description: null,
    state,
    visibility: "public",
    hosting_space_id: TEST_PLAZA,
    related_debate_id: null,
    deadline_at: null,
    reward_aceros: null,
    challenge_kind: "research",
    challenge_problem: null,
    challenge_space_color: null,
    resolution_policy: null,
    winning_submission_id: null,
    resolved_by_agent_id: null,
    max_participants: 16,
    completion_policy: {},
    created_by_agent_id: "agt_owner",
    final_artifact_version_ids: null,
    created_at: "2026-09-05T00:00:00Z",
    activated_at: null,
    completed_at: null,
    resolved_at: null,
    participants: [],
  };
}

test("agent placement is deterministic per district and agent", () => {
  const central = testManifest().landmarks[0]!;
  const agents = [agent("agt_alpha", "idle"), agent("agt_beta", "researching")];
  const first = projectAgentsIntoRoom(agents, central, []);
  const second = projectAgentsIntoRoom(agents, central, []);
  assert.deepEqual(first.map((item) => [item.x, item.y, item.station]), second.map((item) => [item.x, item.y, item.station]));
});

test("messages project to conversation station and visible bubbles", () => {
  const message: WorldMessageEvent = {
    message_id: "msg_1",
    space_id: TEST_PLAZA,
    agent_id: "agt_alpha",
    agent_name: "Alpha",
    content: "Este es un mensaje publico autorizado para la sala.",
    created_at: "2026-09-05T00:00:00Z",
  };
  const projection = projectAgentsIntoRoom([agent("agt_alpha", "idle")], testManifest().landmarks[0]!, [message]);
  assert.equal(projection[0]?.station, "conversation");
  assert.equal(projection[0]?.motion, "talk");
  assert.match(projection[0]?.bubble ?? "", /mensaje publico/);
});

test("semantic activity maps to work stations without server coordinates", () => {
  assert.equal(stationForAgent(agent("agt_reader", "researching"), []), "evidence");
  assert.equal(stationForAgent(agent("agt_reviewer", "reviewing"), []), "review");
  assert.equal(stationForAgent(agent("agt_builder", "building"), []), "workstation");
  assert.equal(stationForAgent(agent("agt_debater", "debating"), []), "deliberation");
});

test("mission state becomes deterministic challenge construction stage", () => {
  assert.equal(constructionStageForMission(mission("draft")), "blueprint");
  assert.equal(constructionStageForMission(mission("active")), "work");
  assert.equal(constructionStageForMission(mission("review")), "review");
  assert.equal(constructionStageForMission({ ...mission("completed"), resolved_at: "2026-09-05T01:00:00Z" }), "monument");
});

test("room projection contains stations, full agent projections and challenge structures", () => {
  const projection = buildIsoRoomProjection({
    district: testManifest().landmarks[0]!,
    agents: [agent("agt_alpha", "discussing")],
    messages: [],
    missions: [mission("active")],
  });
  assert.ok(projection.stations.some((station) => station.kind === "voting"));
  assert.equal(projection.agents[0]?.station, "deliberation");
  assert.equal(projection.constructions[0]?.stage, "work");
});

test("dense districts expand and assign one deterministic footprint per agent", () => {
  const central = testManifest().landmarks[0]!;
  const denseAgents = Array.from({ length: 35 }, (_, index) => agent(`agt_dense_${index}`, "discussing"));
  const projection = buildIsoRoomProjection({
    district: central,
    agents: denseAgents,
    messages: [],
    missions: [],
  });
  assert.ok(projection.sizing.columns >= 24);
  assert.ok(projection.sizing.rows >= 18);
  const footprints = new Set(projection.agents.map((item) => `${item.tileX}:${item.tileY}`));
  assert.equal(footprints.size, denseAgents.length);
});

test("crowded conversations distribute into visible social pods", () => {
  const central = testManifest().landmarks[0]!;
  const denseAgents = Array.from({ length: 35 }, (_, index) => agent(`agt_social_${index}`, "discussing"));
  const projection = buildIsoRoomProjection({
    district: central,
    agents: denseAgents,
    messages: [],
    missions: [],
  });
  const xs = projection.agents.map((item) => item.tileX);
  const ys = projection.agents.map((item) => item.tileY);
  assert.ok(Math.max(...xs) - Math.min(...xs) >= 8);
  assert.ok(Math.max(...ys) - Math.min(...ys) >= 6);
});

test("visible speech bubbles stay bounded in crowded rooms", () => {
  const central = testManifest().landmarks[0]!;
  const denseAgents = Array.from({ length: 12 }, (_, index) => agent(`agt_bubble_${index}`, "idle"));
  const messages = denseAgents.map((item, index): WorldMessageEvent => ({
    message_id: `msg_${index}`,
    space_id: TEST_PLAZA,
    agent_id: item.agent_id,
    agent_name: item.name,
    content: `mensaje ${index}`,
    created_at: `2026-09-05T00:00:${String(index).padStart(2, "0")}Z`,
  }));
  const projection = projectAgentsIntoRoom(denseAgents, central, messages);
  assert.equal(projection.filter((item) => item.bubble).length, MAX_VISIBLE_BUBBLES);
});

test("room sizing keeps low occupancy for population growth", () => {
  const sizing = roomSizingForPopulation(150);
  assert.ok(150 / sizing.usableTiles <= sizing.targetOccupancyRatio);
});
