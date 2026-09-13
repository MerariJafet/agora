import assert from "node:assert/strict";
import { test } from "node:test";
import { humanizeAgentMessage } from "./humanize-message.ts";

test("json payload with message shows only the message text", () => {
  const raw = '[agy-cli:sandbox] {"action": "speak", "space_slug": "central-plaza", "message": "Hola a todos los agentes"}';
  const result = humanizeAgentMessage(raw);
  assert.equal(result.text, "Hola a todos los agentes");
  assert.equal(result.humanized, true);
  assert.equal(result.raw, raw);
});

test("json payload without prefix also humanizes", () => {
  const result = humanizeAgentMessage('{"message": "Sin prefijo de runtime"}');
  assert.equal(result.text, "Sin prefijo de runtime");
  assert.equal(result.humanized, true);
});

test("move action without message renders compact spanish label", () => {
  const result = humanizeAgentMessage(
    '[agy-cli:sandbox] {"action": "move", "space_slug": "science-district", "activity": "researching"}',
  );
  assert.equal(result.text, "→ se movio a Science District (investigando)");
  assert.equal(result.humanized, true);
});

test("move action without activity omits parenthesis", () => {
  const result = humanizeAgentMessage('{"action": "move", "space_slug": "idea-garden"}');
  assert.equal(result.text, "→ se movio a Idea Garden");
});

test("unknown action renders generic label", () => {
  const result = humanizeAgentMessage('{"action": "vote", "space_slug": "central-plaza"}');
  assert.equal(result.text, "accion: vote (Central Plaza)");
  assert.equal(result.humanized, true);
});

test("plain text passes through untouched", () => {
  const raw = "Estoy revisando la evidencia del reto Collatz.";
  const result = humanizeAgentMessage(raw);
  assert.equal(result.text, raw);
  assert.equal(result.humanized, false);
});

test("corrupt or truncated json passes through untouched", () => {
  const raw = '[agy-cli:sandbox] {"action": "move", "space_slug": "science-district", "message": "Ob...';
  const result = humanizeAgentMessage(raw);
  assert.equal(result.text, raw);
  assert.equal(result.humanized, false);
});

test("json without known fields passes through untouched", () => {
  const raw = '{"foo": 1, "bar": "baz"}';
  const result = humanizeAgentMessage(raw);
  assert.equal(result.text, raw);
  assert.equal(result.humanized, false);
});

test("empty message field falls back to action label", () => {
  const result = humanizeAgentMessage('{"action": "move", "space_slug": "economy-hub", "message": "  "}');
  assert.equal(result.text, "→ se movio a Economy Hub");
  assert.equal(result.humanized, true);
});
