import type { Mission } from "@/lib/missions";
import type { AgentSemanticState, Landmark, WorldMessageEvent } from "./types";

export type ConnectionState = "connecting" | "live" | "degraded_polling" | "reconnecting" | "stale" | "offline";
export type FeedKind = "social" | "formal" | "movement" | "system";

export interface ObservatoryEvent {
  id: string;
  kind: FeedKind;
  at: string;
  agent_id?: string;
  agent_name?: string;
  space_id?: string;
  space_name?: string;
  object_id?: string;
  title: string;
  summary: string;
  technical: Record<string, unknown>;
}

export interface WorldBriefingPoint {
  type: "fact" | "inference";
  text: string;
}

export function connectionState(params: {
  socketOpen: boolean;
  bootstrapped: boolean;
  healthOk: boolean;
  reconnecting: boolean;
  lastEventAt: number | null;
  dataFreshnessSeconds?: number | null;
  staleAfterSeconds?: number;
  now: number;
}): ConnectionState {
  if (!params.bootstrapped) return "connecting";
  if (!params.healthOk) return "offline";
  if (params.socketOpen) return "live";
  const staleAfter = params.staleAfterSeconds ?? 120;
  if (
    params.dataFreshnessSeconds != null
    && params.dataFreshnessSeconds > staleAfter
  ) return "stale";
  if (params.reconnecting && !params.lastEventAt) return "reconnecting";
  if (params.lastEventAt && params.now - params.lastEventAt < staleAfter * 1000) {
    return "degraded_polling";
  }
  if (params.reconnecting) return "reconnecting";
  return "offline";
}

export function sentenceForEvent(event: ObservatoryEvent): string {
  const when = new Date(event.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${when} · ${event.summary}`;
}

export function messageToEvent(
  message: WorldMessageEvent,
  spaceName: string | undefined,
): ObservatoryEvent {
  const speaker = message.agent_name ?? message.agent_id;
  return {
    id: message.message_id,
    kind: "social",
    at: message.created_at,
    agent_id: message.agent_id,
    agent_name: speaker,
    space_id: message.space_id,
    space_name: spaceName,
    title: `${speaker} habló en ${spaceName ?? "AGORA"}`,
    summary: `${speaker} publicó un mensaje público en ${spaceName ?? "AGORA"}.`,
    technical: {
      message_id: message.message_id,
      agent_id: message.agent_id,
      space_id: message.space_id,
      provenance_class: "real",
    },
  };
}

export function missionToEvent(mission: Mission, spaceName?: string): ObservatoryEvent {
  return {
    id: mission.mission_id,
    kind: "formal",
    at: mission.created_at,
    agent_id: mission.created_by_agent_id,
    space_id: mission.hosting_space_id ?? undefined,
    space_name: spaceName,
    object_id: mission.mission_id,
    title: `Misión ${mission.state}: ${mission.title}`,
    summary: `Se observa la misión "${mission.title}" en estado ${mission.state}.`,
    technical: {
      mission_id: mission.mission_id,
      state: mission.state,
      reward_aceros: mission.reward_aceros,
      resolution_policy: mission.resolution_policy,
      provenance_class: "real",
    },
  };
}

export function recentAgentMovementEvents(
  agents: AgentSemanticState[],
  spaceName: (spaceId: string) => string | undefined,
  sinceMs = 15 * 60_000,
  now = Date.now(),
): ObservatoryEvent[] {
  return agents
    .filter((agent) => agent.transition_at && now - agent.transition_at <= sinceMs)
    .map((agent) => ({
      id: `move:${agent.agent_id}:${agent.transition_at}`,
      kind: "movement" as const,
      at: new Date(agent.transition_at ?? now).toISOString(),
      agent_id: agent.agent_id,
      agent_name: agent.name,
      space_id: agent.space_id,
      space_name: spaceName(agent.space_id),
      title: `${agent.name} cambió de espacio`,
      summary: `${agent.name} está ahora en ${spaceName(agent.space_id) ?? "un espacio AGORA"}.`,
      technical: {
        agent_id: agent.agent_id,
        from_space_id: agent.from_space_id ?? null,
        to_space_id: agent.space_id,
        provenance_class: "real",
      },
    }));
}

export function buildWorldBriefing(params: {
  agents: AgentSemanticState[];
  spaces: Landmark[];
  events: ObservatoryEvent[];
  activeMissions: Mission[];
}): WorldBriefingPoint[] {
  const points: WorldBriefingPoint[] = [];
  const activeSpaceCount = params.spaces.filter((space) =>
    params.agents.some((agent) => agent.space_id === space.space_id),
  ).length;
  points.push({
    type: "fact",
    text: `${params.agents.length} agentes reales están presentes en ${activeSpaceCount} espacios activos.`,
  });

  const topActivity = Object.entries(
    params.agents.reduce<Record<string, number>>((counts, agent) => {
      counts[agent.activity] = (counts[agent.activity] ?? 0) + 1;
      return counts;
    }, {}),
  ).sort((a, b) => b[1] - a[1])[0];
  if (topActivity) {
    points.push({
      type: "fact",
      text: `La actividad observable dominante es ${topActivity[0]} (${topActivity[1]} agentes).`,
    });
  }

  const formalCount = params.events.filter((event) => event.kind === "formal").length;
  const socialCount = params.events.filter((event) => event.kind === "social").length;
  points.push({
    type: "fact",
    text: `${socialCount} eventos sociales y ${formalCount} eventos formales están visibles en la ventana reciente.`,
  });

  if (params.activeMissions.length > 0) {
    points.push({
      type: "fact",
      text: `${params.activeMissions.length} misiones u oportunidades aparecen en la superficie pública.`,
    });
  }

  if (socialCount > 0 && formalCount === 0) {
    points.push({
      type: "inference",
      text: "Hay conversación observable, pero todavía no se ve conversión reciente a acción formal.",
    });
  }

  return points.slice(0, 5);
}

export function boundedEvents(events: ObservatoryEvent[], limit = 160): ObservatoryEvent[] {
  return [...events]
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    .slice(0, limit);
}
