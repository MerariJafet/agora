import assert from "node:assert/strict";
import { test } from "node:test";
import {
  cadenceChatTone,
  cadenceToneLabel,
  formatCountdown,
  isLivePhase,
  phaseBounds,
  phaseProgress,
  quorumShare,
  remainingSeconds,
  splitMentions,
  type CadenceRound,
} from "./cadence.ts";

function testRound(overrides: Partial<CadenceRound> = {}): CadenceRound {
  return {
    round_id: "rrd_test",
    title: "Research window",
    state: "OPEN",
    phase_ends_at: "2026-09-13T10:10:00Z",
    countdown_started_at: "2026-09-13T10:00:00Z",
    windows: {
      proposal_window_ends_at: "2026-09-13T10:10:00Z",
      deliberation_ends_at: "2026-09-13T10:20:00Z",
      voting_ends_at: "2026-09-13T10:30:00Z",
    },
    eligible_agents: 20,
    votes: { approve: 0, reject: 0, abstain: 0, needs_revision: 0, total: 0 },
    quorum_required: 12,
    quorum_count: 0,
    selected_proposal_id: null,
    challenge_mission_id: null,
    reward_reserved: false,
    ...overrides,
  };
}

test("formatCountdown renders mm:ss and never fakes a countdown that does not exist", () => {
  assert.equal(formatCountdown(412), "06:52");
  assert.equal(formatCountdown(0), "00:00");
  assert.equal(formatCountdown(59), "00:59");
  assert.equal(formatCountdown(3600), "60:00");
  assert.equal(formatCountdown(null), "--:--");
  assert.equal(formatCountdown(Number.NaN), "--:--");
  // Un restante negativo (deriva de reloj) se muestra como cerrado, no en rojo mágico.
  assert.equal(formatCountdown(-5), "00:00");
});

test("remainingSeconds anchors the deadline on the fetch instant, not on the client clock", () => {
  const receivedAt = 1_000_000;
  assert.equal(remainingSeconds(600, receivedAt, receivedAt), 600);
  assert.equal(remainingSeconds(600, receivedAt, receivedAt + 60_000), 540);
  // Nunca baja de cero aunque la pestaña estuviera dormida.
  assert.equal(remainingSeconds(600, receivedAt, receivedAt + 900_000), 0);
  assert.equal(remainingSeconds(null, receivedAt, receivedAt), null);
});

test("phaseBounds uses the three round windows and refuses to invent missing edges", () => {
  const round = testRound();
  const proposal = phaseBounds(round, "proposal");
  assert.ok(proposal);
  assert.equal((proposal.end - proposal.start) / 1000, 600);
  const deliberation = phaseBounds(round, "deliberation");
  assert.ok(deliberation);
  assert.equal((deliberation.end - deliberation.start) / 1000, 600);
  const voting = phaseBounds(round, "voting");
  assert.ok(voting);
  assert.equal((voting.end - voting.start) / 1000, 600);
  assert.equal(phaseBounds(round, "closed"), null);
  assert.equal(phaseBounds(null, "proposal"), null);
});

test("phaseBounds falls back to the previous edge when deliberation is not published", () => {
  const round = testRound({
    windows: {
      proposal_window_ends_at: "2026-09-13T10:10:00Z",
      deliberation_ends_at: null,
      voting_ends_at: "2026-09-13T10:30:00Z",
    },
  });
  assert.equal(phaseBounds(round, "deliberation"), null);
  const voting = phaseBounds(round, "voting");
  assert.ok(voting);
  // Sin borde de deliberación, votación arranca donde cerró propuestas.
  assert.equal((voting.end - voting.start) / 1000, 1200);
});

test("phaseProgress is the elapsed share of the current phase, clamped to 0..1", () => {
  const round = testRound();
  assert.equal(phaseProgress(round, "proposal", 600), 0);
  assert.equal(phaseProgress(round, "proposal", 300), 0.5);
  assert.equal(phaseProgress(round, "proposal", 0), 1);
  assert.equal(phaseProgress(round, "proposal", 900), 0);
  assert.equal(phaseProgress(round, "closed", 0), null);
  assert.equal(phaseProgress(round, "proposal", null), null);
});

test("quorumShare is the eligible fraction the quorum demands, or null without a census", () => {
  assert.equal(quorumShare(testRound()), 0.6);
  assert.equal(quorumShare(testRound({ eligible_agents: 0 })), null);
  assert.equal(quorumShare(null), null);
});

test("isLivePhase only shouts while a window is actually open", () => {
  assert.equal(isLivePhase("proposal"), true);
  assert.equal(isLivePhase("deliberation"), true);
  assert.equal(isLivePhase("voting"), true);
  assert.equal(isLivePhase("closed"), false);
  assert.equal(isLivePhase("none"), false);
});

test("cadenceChatTone classifies real pilot forum events deterministically", () => {
  assert.equal(cadenceChatTone("research.window.opened"), "proposal");
  assert.equal(cadenceChatTone("challenge.solution_submitted.summary"), "proposal");
  assert.equal(cadenceChatTone("research.proposal.created"), "proposal");
  assert.equal(cadenceChatTone("challenge.vote.summary"), "vote");
  assert.equal(cadenceChatTone("challenge.abstention.summary"), "vote");
  assert.equal(cadenceChatTone("research.vote.cast"), "vote");
  assert.equal(cadenceChatTone("research.challenge.activated"), "activated");
  assert.equal(cadenceChatTone("research.challenge.genesis_wave2_launched"), "activated");
  assert.equal(cadenceChatTone("challenge.submission_finalized.summary"), "resolution");
  assert.equal(cadenceChatTone("research.candidate.released"), "resolution");
  // Sin evento, o evento ajeno a la cadencia: sin tono, el chat no se colorea.
  assert.equal(cadenceChatTone(null), null);
  assert.equal(cadenceChatTone(undefined), null);
  assert.equal(cadenceChatTone("world.charter_published"), null);
  assert.equal(cadenceChatTone("challenge.thread_contribution.summary"), null);
  assert.equal(cadenceToneLabel(cadenceChatTone("challenge.vote.summary")), "voto");
  assert.equal(cadenceToneLabel(null), null);
});

test("splitMentions finds @handles with the same lexicon as the mentions backend", () => {
  assert.deepEqual(splitMentions("hola @nobel-maximo, mira esto"), [
    { text: "hola ", mention: null },
    { text: "@nobel-maximo", mention: "nobel-maximo" },
    { text: ", mira esto", mention: null },
  ]);
  assert.deepEqual(splitMentions("@todos"), [{ text: "@todos", mention: "todos" }]);
  // Correos y arrobas encadenadas NO son menciones.
  assert.deepEqual(splitMentions("escribe a merari@example.com"), [
    { text: "escribe a merari@example.com", mention: null },
  ]);
  assert.deepEqual(splitMentions("@@raro"), [{ text: "@@raro", mention: null }]);
  assert.deepEqual(splitMentions("sin menciones"), [{ text: "sin menciones", mention: null }]);
  assert.deepEqual(splitMentions(""), [{ text: "", mention: null }]);
  assert.deepEqual(splitMentions("@a y @b"), [
    { text: "@a", mention: "a" },
    { text: " y ", mention: null },
    { text: "@b", mention: "b" },
  ]);
});
