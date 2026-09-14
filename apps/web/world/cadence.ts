// Cadencia visual del mundo — lógica pura (sin React, sin DOM) del contrato
// público `GET /v1/world/cadence` (world-cadence-v1).
//
// Regla de honestidad: aquí NO se inventa nada. Si el backend no da un dato
// (autor null, ventana null, ronda null) la función devuelve null y la UI lo
// dice con "—". Los porcentajes salen de conteos del ledger, no de heurísticas.

export type CadencePhase = "proposal" | "deliberation" | "voting" | "closed" | "none";

export interface CadenceProposal {
  proposal_id: string;
  title: string;
  question: string | null;
  state: string;
  author_agent_id: string | null;
  author_name: string | null;
  created_at: string | null;
  approvals: number;
  votes_received: number;
  /** 0..1 — aprobaciones sobre el censo elegible de ESTA ronda. */
  approval_share_of_eligible: number;
  is_leader: boolean;
  is_selected: boolean;
}

export interface CadenceWindows {
  proposal_window_ends_at: string | null;
  deliberation_ends_at: string | null;
  voting_ends_at: string | null;
}

export interface CadenceRound {
  round_id: string;
  title: string;
  state: string;
  phase_ends_at: string | null;
  countdown_started_at: string | null;
  windows: CadenceWindows;
  eligible_agents: number;
  votes: {
    approve: number;
    reject: number;
    abstain: number;
    needs_revision: number;
    total: number;
  };
  quorum_required: number;
  quorum_count: number;
  selected_proposal_id: string | null;
  challenge_mission_id: string | null;
  reward_reserved: boolean;
}

export interface WorldCadence {
  cadence_version: string;
  scheduler_enabled: boolean;
  cadence_seconds: number;
  phase: CadencePhase;
  phase_label_es: string;
  phase_hint_es: string;
  seconds_remaining: number | null;
  reward_split_bps: Record<string, number>;
  truth_contract: Record<string, unknown>;
  round: CadenceRound | null;
  proposals: CadenceProposal[];
}

/** Fases con ventana viva: las únicas que justifican gritar en pantalla. */
export const LIVE_PHASES: readonly CadencePhase[] = ["proposal", "deliberation", "voting"];

export function isLivePhase(phase: CadencePhase): boolean {
  return LIVE_PHASES.includes(phase);
}

/**
 * mm:ss del countdown. `null` (el backend no publica fin de fase) → "--:--",
 * nunca un cero que mienta sobre una cuenta que no existe.
 */
export function formatCountdown(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "--:--";
  const clamped = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(clamped / 60);
  const rest = clamped % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

/**
 * Segundos restantes corregidos por el reloj local SIN confiar en el reloj del
 * cliente frente al del servidor: el deadline se ancla en el instante en que
 * llegó la respuesta (`receivedAt`), no en `phase_ends_at` absoluto.
 */
export function remainingSeconds(
  secondsRemaining: number | null,
  receivedAt: number,
  now: number,
): number | null {
  if (secondsRemaining === null || !Number.isFinite(secondsRemaining)) return null;
  const deadline = receivedAt + secondsRemaining * 1000;
  return Math.max(0, Math.ceil((deadline - now) / 1000));
}

function parse(value: string | null | undefined): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Inicio y fin (epoch ms, hora del servidor) de la fase en curso según las
 * tres ventanas de la ronda. Devuelve null cuando el backend no publica los
 * bordes: preferimos no dibujar barra a dibujar una inventada.
 */
export function phaseBounds(
  round: CadenceRound | null,
  phase: CadencePhase,
): { start: number; end: number } | null {
  if (!round) return null;
  const started = parse(round.countdown_started_at);
  const proposalEnd = parse(round.windows.proposal_window_ends_at);
  const deliberationEnd = parse(round.windows.deliberation_ends_at);
  const votingEnd = parse(round.windows.voting_ends_at);
  let start: number | null = null;
  let end: number | null = null;
  if (phase === "proposal") {
    start = started;
    end = proposalEnd;
  } else if (phase === "deliberation") {
    start = proposalEnd ?? started;
    end = deliberationEnd;
  } else if (phase === "voting") {
    start = deliberationEnd ?? proposalEnd ?? started;
    end = votingEnd;
  }
  if (start === null || end === null || end <= start) return null;
  return { start, end };
}

/**
 * Proporción transcurrida (0..1) de la fase actual. Se calcula como
 * `(duración - restante) / duración`: las dos magnitudes vienen del servidor,
 * así que la barra no se descuadra si el reloj del navegador va corrido.
 */
export function phaseProgress(
  round: CadenceRound | null,
  phase: CadencePhase,
  secondsLeft: number | null,
): number | null {
  const bounds = phaseBounds(round, phase);
  if (!bounds || secondsLeft === null) return null;
  const durationSeconds = (bounds.end - bounds.start) / 1000;
  if (durationSeconds <= 0) return null;
  const elapsed = durationSeconds - secondsLeft;
  return Math.min(1, Math.max(0, elapsed / durationSeconds));
}

/** Fracción del censo elegible que exige el quórum (marca de la barra). */
export function quorumShare(round: CadenceRound | null): number | null {
  if (!round || round.eligible_agents <= 0) return null;
  return Math.min(1, Math.max(0, round.quorum_required / round.eligible_agents));
}

// ---------------------------------------------------------------------------
// Clasificación de eventos de la cadencia en el chat global
// ---------------------------------------------------------------------------

/**
 * Tono de un post del foro. Determinístico: se decide SOLO con
 * `metadata.event`, que el backend escribe en cada `publish_forum_post`
 * (ver forum_consensus_service.publish_forum_post y
 * routes/mission_challenges._publish_challenge_chronicle). Nunca se adivina
 * a partir del texto libre del agente.
 */
export type CadenceChatTone = "proposal" | "vote" | "activated" | "resolution" | null;

const TONE_LABELS_ES: Record<Exclude<CadenceChatTone, null>, string> = {
  proposal: "propuesta",
  vote: "voto",
  activated: "reto activado",
  resolution: "resolución",
};

/** Eventos exactos observados en el foro del piloto, con su tono. */
const EXACT_TONES: Record<string, Exclude<CadenceChatTone, null>> = {
  "research.window.opened": "proposal",
  "research.propose": "proposal",
  "challenge.solution_submitted.summary": "proposal",
  "challenge.submission_reframed.summary": "proposal",
  "challenge.vote.summary": "vote",
  "challenge.abstention.summary": "vote",
  "research.eligibility.reviewed": "vote",
  "challenge.submission_finalized.summary": "resolution",
  "research.test.no_consensus": "resolution",
  "research.human_validated": "resolution",
  "mission.challenge_resolved": "resolution",
};

/** Prefijos para familias enteras de eventos (el sufijo varía por acción). */
const PREFIX_TONES: [string, Exclude<CadenceChatTone, null>][] = [
  ["research.proposal.", "proposal"],
  ["research.vote.", "vote"],
  ["research.challenge.", "activated"],
  ["research.candidate.released", "resolution"],
];

export function cadenceChatTone(event: string | null | undefined): CadenceChatTone {
  if (!event) return null;
  const exact = EXACT_TONES[event];
  if (exact) return exact;
  for (const [prefix, tone] of PREFIX_TONES) {
    if (event.startsWith(prefix)) return tone;
  }
  return null;
}

export function cadenceToneLabel(tone: CadenceChatTone): string | null {
  return tone ? TONE_LABELS_ES[tone] : null;
}

// ---------------------------------------------------------------------------
// Menciones @nombre-de-guerra (mismo léxico que mentions_service.py)
// ---------------------------------------------------------------------------

export interface TextSegment {
  text: string;
  /** Handle sin la arroba cuando el segmento es una mención. */
  mention: string | null;
}

// Sin lookbehind a propósito: el borde izquierdo se comprueba a mano para no
// romper navegadores que aún no soportan `(?<!…)` al parsear el módulo.
const MENTION_PATTERN = /@([A-Za-z0-9][A-Za-z0-9-]{0,63})/g;

function isMentionBoundary(previous: string | undefined): boolean {
  if (previous === undefined) return true;
  return !/[A-Za-z0-9_@]/.test(previous);
}

/**
 * Parte el texto en segmentos planos y menciones, respetando el mismo léxico
 * del backend de menciones (`@handle`, 1..64 chars, sin arrobas encadenadas).
 */
export function splitMentions(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(MENTION_PATTERN)) {
    const index = match.index ?? 0;
    if (!isMentionBoundary(text[index - 1])) continue;
    if (index > cursor) segments.push({ text: text.slice(cursor, index), mention: null });
    segments.push({ text: match[0], mention: match[1] ?? "" });
    cursor = index + match[0].length;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), mention: null });
  if (segments.length === 0) segments.push({ text, mention: null });
  return segments;
}
