// WorldStore behavior (S3-T13/T15). Pure logic: no canvas, no network.
// Run with: npm run test:world  (Node native TS, no extra toolchain)

import assert from "node:assert/strict";
import { test } from "node:test";
import { WorldStore, slotFor } from "./store.ts";
import {
  TEST_GARDEN,
  TEST_PLAZA,
  syntheticSnapshot,
  testAvatar,
  testManifest,
} from "./store.test-fixtures.ts";

function store() {
  const s = new WorldStore();
  s.setManifest(testManifest());
  return s;
}

test("snapshot places agents and prunes those who left", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(3));
  assert.equal(s.agents.size, 3);
  s.applySnapshot(syntheticSnapshot(1));
  assert.equal(s.agents.size, 1, "agents absent from a snapshot are removed");
  assert.equal(s.visuals.size, 1, "visual state must not leak");
});

test("deterministic slots are stable per agent", () => {
  const landmark = testManifest().landmarks[0]!;
  const a = slotFor("agt_alpha", landmark, 0);
  const b = slotFor("agt_alpha", landmark, 0);
  const c = slotFor("agt_beta", landmark, 0);
  assert.deepEqual(a, b, "same agent always lands in the same slot");
  assert.notDeepEqual(a, c);
  const distance = Math.hypot(a.x - landmark.x, a.y - landmark.y);
  assert.ok(distance <= landmark.radius, "slots stay inside the landmark");
});

test("late joiner snaps to destination instead of replaying movement", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(1, TEST_GARDEN));
  const [agent] = [...s.agents.values()];
  const visual = s.visuals.get(agent!.agent_id)!;
  assert.equal(visual.x, visual.targetX);
  assert.equal(visual.y, visual.targetY);
  assert.equal(visual.path.length, 0);
});

test("transition animates over the nav graph", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(1, TEST_PLAZA));
  const agentId = [...s.agents.keys()][0]!;
  s.applyTransition({
    agent_id: agentId,
    from_space_id: TEST_PLAZA,
    to_space_id: TEST_GARDEN,
    activity: "exploring",
    avatar: testAvatar(),
  });
  assert.equal(s.agents.get(agentId)!.space_id, TEST_GARDEN);
  assert.ok(s.visuals.get(agentId)!.path.length > 0, "a local path is computed");
});

test("duplicate transition is idempotent", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(1, TEST_PLAZA));
  const agentId = [...s.agents.keys()][0]!;
  const frame = {
    agent_id: agentId,
    from_space_id: TEST_PLAZA,
    to_space_id: TEST_GARDEN,
  };
  s.applyTransition(frame);
  const firstPath = [...s.visuals.get(agentId)!.path];
  s.applyTransition(frame); // redelivered
  assert.equal(s.agents.get(agentId)!.space_id, TEST_GARDEN);
  assert.deepEqual(
    s.visuals.get(agentId)!.path,
    firstPath,
    "re-delivery must not restart the animation",
  );
});

test("leaving removes the agent entirely", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(2));
  const agentId = [...s.agents.keys()][0]!;
  s.applyTransition({ agent_id: agentId, to_space_id: null });
  assert.equal(s.agents.has(agentId), false);
  assert.equal(s.visuals.has(agentId), false);
});

test("activity and avatar deltas apply without a refetch", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(1));
  const agentId = [...s.agents.keys()][0]!;
  const before = s.version;
  s.setActivity(agentId, "researching");
  s.setAvatar(agentId, testAvatar("#e0596a"));
  assert.equal(s.agents.get(agentId)!.activity, "researching");
  assert.equal(s.agents.get(agentId)!.avatar.tint, "#e0596a");
  assert.ok(s.version > before);
  const settled = s.version;
  s.setActivity(agentId, "researching"); // no-op
  assert.equal(s.version, settled, "redundant deltas do not churn renders");
});

test("message events mark speakers and create conversation links", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(2, TEST_GARDEN));
  const [first, second] = [...s.agents.values()];
  assert.ok(first);
  assert.ok(second);

  s.applyMessage({
    message_id: "msg_1",
    space_id: TEST_GARDEN,
    agent_id: first.agent_id,
    agent_name: first.name,
    content: "hello",
    created_at: new Date().toISOString(),
  });
  assert.equal(s.recentActivity().length, 1);
  assert.equal(s.visuals.get(first.agent_id)!.speaking > 0, true);

  s.applyMessage({
    message_id: "msg_2",
    space_id: TEST_GARDEN,
    agent_id: second.agent_id,
    agent_name: second.name,
    content: "reply",
    created_at: new Date().toISOString(),
  });
  const links = s.activeConversationLinks();
  assert.equal(links.length, 1);
  assert.equal(links[0]!.from_agent_id, first.agent_id);
  assert.equal(links[0]!.to_agent_id, second.agent_id);
});

test("duplicate message delivery is idempotent", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(1, TEST_PLAZA));
  const [agent] = [...s.agents.values()];
  const message = {
    message_id: "msg_duplicate",
    space_id: TEST_PLAZA,
    agent_id: agent!.agent_id,
    agent_name: agent!.name,
    content: "one logical action",
    created_at: new Date().toISOString(),
  };
  s.applyMessage(message);
  s.applyMessage(message);
  assert.equal(s.recentActivity().length, 1);
});

test("population aggregates come from semantic presence", () => {
  const s = store();
  s.applySnapshot(syntheticSnapshot(250));
  assert.equal(s.populationBySpace().get(TEST_PLAZA), 250);
  assert.equal(s.agentsInSpace(TEST_PLAZA).length, 250);
});

test("large populations apply in reasonable time (no O(n^2) hot path)", () => {
  const s = store();
  const started = Date.now();
  s.applySnapshot(syntheticSnapshot(1000));
  const elapsed = Date.now() - started;
  assert.equal(s.agents.size, 1000);
  assert.ok(elapsed < 1500, `snapshot of 1000 agents took ${elapsed}ms`);
});
