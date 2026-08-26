import assert from "node:assert/strict";
import { test } from "node:test";
import {
  boundedEvents,
  buildWorldBriefing,
  connectionState,
  messageToEvent,
  recentAgentMovementEvents,
  sentenceForEvent,
} from "./observatory.ts";
import { testAvatar, testManifest, TEST_GARDEN } from "./store.test-fixtures.ts";

test("connection state separates connecting, live, degraded polling, stale and offline", () => {
  const now = Date.now();
  assert.equal(connectionState({
    socketOpen: false,
    bootstrapped: false,
    healthOk: false,
    reconnecting: false,
    lastEventAt: null,
    now,
  }), "connecting");
  assert.equal(connectionState({
    socketOpen: true,
    bootstrapped: true,
    healthOk: true,
    reconnecting: false,
    lastEventAt: now,
    now,
  }), "live");
  assert.equal(connectionState({
    socketOpen: false,
    bootstrapped: true,
    healthOk: true,
    reconnecting: false,
    lastEventAt: now - 30_000,
    now,
  }), "degraded_polling");
  assert.equal(connectionState({
    socketOpen: false,
    bootstrapped: true,
    healthOk: true,
    reconnecting: true,
    lastEventAt: null,
    now,
  }), "reconnecting");
  assert.equal(connectionState({
    socketOpen: false,
    bootstrapped: true,
    healthOk: true,
    reconnecting: false,
    lastEventAt: now - 30_000,
    dataFreshnessSeconds: 180,
    now,
  }), "stale");
  assert.equal(connectionState({
    socketOpen: false,
    bootstrapped: true,
    healthOk: false,
    reconnecting: false,
    lastEventAt: now - 120_000,
    now,
  }), "offline");
});

test("message events are narrated without exposing private content", () => {
  const event = messageToEvent({
    message_id: "msg_1",
    space_id: TEST_GARDEN,
    agent_id: "agt_alpha",
    agent_name: "Agora-Alpha",
    content: "Public statement",
    created_at: "2026-08-26T05:00:00.000Z",
  }, "Idea Garden");
  assert.equal(event.kind, "social");
  assert.equal(event.technical.provenance_class, "real");
  assert.match(sentenceForEvent(event), /Agora-Alpha publicó un mensaje público/);
});

test("briefing separates facts from inference", () => {
  const manifest = testManifest();
  const points = buildWorldBriefing({
    agents: [{
      agent_id: "agt_alpha",
      name: "Alpha",
      activity: "researching",
      avatar: testAvatar(),
      space_id: TEST_GARDEN,
    }],
    spaces: manifest.landmarks,
    events: [messageToEvent({
      message_id: "msg_1",
      space_id: TEST_GARDEN,
      agent_id: "agt_alpha",
      agent_name: "Alpha",
      content: "hello",
      created_at: new Date().toISOString(),
    }, "Idea Garden")],
    activeMissions: [],
  });
  assert.equal(points[0]?.type, "fact");
  assert.ok(points.some((point) => point.type === "inference"));
});

test("movement events only derive from recent semantic transitions", () => {
  const now = Date.now();
  const events = recentAgentMovementEvents([{
    agent_id: "agt_alpha",
    name: "Alpha",
    activity: "exploring",
    avatar: testAvatar(),
    space_id: TEST_GARDEN,
    from_space_id: "spc_start",
    transition_at: now - 1000,
  }], () => "Idea Garden", 15_000, now);
  assert.equal(events.length, 1);
  assert.equal(events[0]?.kind, "movement");
});

test("bounded events are sorted newest first and limited", () => {
  const events = boundedEvents([
    { id: "old", kind: "system", at: "2026-08-26T04:00:00Z", title: "old", summary: "old", technical: {} },
    { id: "new", kind: "system", at: "2026-08-26T05:00:00Z", title: "new", summary: "new", technical: {} },
  ], 1);
  assert.equal(events.length, 1);
  assert.equal(events[0]?.id, "new");
});
