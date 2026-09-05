import assert from "node:assert/strict";
import { test } from "node:test";
import {
  agentDistrictHref,
  challengeHref,
  districtHref,
  encodeFocus,
  focusedDistrictHref,
  parseFocus,
} from "./interaction-contract.ts";
import { testAvatar, testManifest, TEST_PLAZA } from "./store.test-fixtures.ts";
import type { AgentSemanticState } from "./types.ts";

const spaces = testManifest().landmarks.filter((landmark) => landmark.space_id);

test("district and challenge routes are stable and explicit", () => {
  assert.equal(districtHref(spaces[0]!), "/world/district/central");
  assert.equal(challengeHref("mis_alpha"), "/world/challenge/mis_alpha");
});

test("agent links deep-link to the current visible district", () => {
  const agent: AgentSemanticState = {
    agent_id: "agt_alpha",
    name: "Alpha",
    activity: "researching",
    avatar: testAvatar("#42d6bf"),
    space_id: TEST_PLAZA,
  };
  assert.match(agentDistrictHref(agent, spaces), /^\/world\/district\/central\?focus=agent%3Aagt_alpha$/);
});

test("agents without visible location route to passport rather than a dead click", () => {
  const agent: AgentSemanticState = {
    agent_id: "agt_lost",
    name: "Lost",
    activity: "offline",
    avatar: testAvatar("#42d6bf"),
    space_id: "spc_missing",
  };
  assert.equal(agentDistrictHref(agent, spaces), "/agents/agt_lost");
});

test("focus values roundtrip for reloadable inspection", () => {
  const focus = { kind: "agent" as const, id: "agt_alpha" };
  assert.deepEqual(parseFocus(encodeFocus(focus)), focus);
  assert.equal(focusedDistrictHref(spaces[0]!, focus), "/world/district/central?focus=agent%3Aagt_alpha");
  assert.equal(parseFocus("unknown:thing"), null);
});
