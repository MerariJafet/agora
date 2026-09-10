import assert from "node:assert/strict";
import { test } from "node:test";
import { resolveRealtimeWsUrl } from "./connection.ts";

test("public HTTPS pages use the same-origin websocket proxy", () => {
  assert.equal(resolveRealtimeWsUrl({ pageUrl: "https://agora.example/world" }),
    "wss://agora.example/agora-api/v1/realtime/web");
});
test("local pages use the same-origin websocket proxy", () => {
  assert.equal(resolveRealtimeWsUrl({ pageUrl: "http://localhost:3000/world" }),
    "ws://localhost:3000/agora-api/v1/realtime/web");
});
test("explicit APIs support absolute and relative URLs", () => {
  assert.equal(resolveRealtimeWsUrl({ api: "https://api.example/" }),
    "wss://api.example/v1/realtime/web");
  assert.equal(resolveRealtimeWsUrl({ api: "/gateway", pageUrl: "https://agora.example/" }),
    "wss://agora.example/gateway/v1/realtime/web");
});
test("explicit websocket URLs and legacy ports remain available", () => {
  assert.equal(resolveRealtimeWsUrl({ configured: "wss://events.example/socket" }),
    "wss://events.example/socket");
  assert.equal(resolveRealtimeWsUrl({ pageUrl: "http://localhost:3000/", legacyPort: "8710" }),
    "ws://localhost:8710/v1/realtime/web");
});
test("unsafe protocols fail closed", () => {
  assert.throws(() => resolveRealtimeWsUrl({ configured: "javascript:alert(1)" }));
});
