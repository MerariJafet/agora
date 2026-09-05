import type { Mission } from "@/lib/missions";
import type { AgentSemanticState, Landmark, WorldMessageEvent } from "./types";

export const VISUAL_SCHEMA_VERSION = "visual-world-manifest.v2.iso-room";

export type DistrictTemplate = "plaza" | "science" | "economy" | "forge" | "garden" | "unknown";

export type IsoStationKind =
  | "portal"
  | "conversation"
  | "deliberation"
  | "voting"
  | "evidence"
  | "review"
  | "workstation"
  | "challenge_plot";

export interface IsoStation {
  kind: IsoStationKind;
  label: string;
  gridX: number;
  gridY: number;
  elevation?: number;
}

export interface IsoAgentProjection {
  agent: AgentSemanticState;
  station: IsoStationKind;
  x: number;
  y: number;
  z: number;
  facing: "left" | "right";
  bubble: string | null;
  motion: "idle" | "walk" | "talk" | "think" | "vote" | "work" | "review" | "submit";
}

export interface ChallengeConstructionProjection {
  id: string;
  title: string;
  stage: "blueprint" | "deliberation" | "foundation" | "work" | "review" | "monument" | "archive";
  progress: number;
  x: number;
  y: number;
}

export interface IsoRoomProjection {
  district: Landmark;
  template: DistrictTemplate;
  stations: IsoStation[];
  agents: IsoAgentProjection[];
  constructions: ChallengeConstructionProjection[];
}

const BASE_STATIONS: IsoStation[] = [
  { kind: "portal", label: "Portal", gridX: 1, gridY: 6 },
  { kind: "conversation", label: "Zona de conversacion", gridX: 4, gridY: 5 },
  { kind: "deliberation", label: "Mesa de deliberacion", gridX: 6, gridY: 3 },
  { kind: "voting", label: "Terminal de votacion", gridX: 8, gridY: 5 },
  { kind: "evidence", label: "Estacion de evidencia", gridX: 5, gridY: 8 },
  { kind: "review", label: "Mesa de revision", gridX: 9, gridY: 8 },
  { kind: "workstation", label: "Estaciones de trabajo", gridX: 3, gridY: 9 },
  { kind: "challenge_plot", label: "Parcela del reto", gridX: 10, gridY: 2 },
];

export function stableHash(input: string): number {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash >>> 0;
}

export function isoToScreen(gridX: number, gridY: number, elevation = 0) {
  const tileWidthPercent = 7.2;
  const tileHeightPercent = 5.1;
  const levelHeightPercent = 4.2;
  return {
    x: 50 + (gridX - gridY) * tileWidthPercent / 2,
    y: 24 + (gridX + gridY) * tileHeightPercent / 2 - elevation * levelHeightPercent,
  };
}

export function templateForDistrict(district: Landmark | undefined): DistrictTemplate {
  const haystack = `${district?.id ?? ""} ${district?.name ?? ""}`.toLowerCase();
  if (haystack.includes("science")) return "science";
  if (haystack.includes("economy")) return "economy";
  if (haystack.includes("forge")) return "forge";
  if (haystack.includes("idea") || haystack.includes("garden")) return "garden";
  if (haystack.includes("unknown")) return "unknown";
  return "plaza";
}

export function latestMessageForAgent(
  agentId: string,
  messages: WorldMessageEvent[],
): WorldMessageEvent | undefined {
  return [...messages]
    .filter((message) => message.agent_id === agentId)
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
}

export function stationForAgent(
  agent: AgentSemanticState,
  messages: WorldMessageEvent[],
): IsoStationKind {
  if (latestMessageForAgent(agent.agent_id, messages)) return "conversation";
  if (agent.from_space_id && agent.from_space_id !== agent.space_id) return "portal";
  if (agent.activity === "debating" || agent.activity === "discussing") return "deliberation";
  if (agent.activity === "reviewing") return "review";
  if (agent.activity === "researching" || agent.activity === "reading") return "evidence";
  if (agent.activity === "building" || agent.activity === "computing" || agent.activity === "writing") {
    return "workstation";
  }
  return "conversation";
}

export function motionForStation(station: IsoStationKind, hasBubble: boolean): IsoAgentProjection["motion"] {
  if (hasBubble) return "talk";
  if (station === "portal") return "walk";
  if (station === "voting") return "vote";
  if (station === "evidence") return "submit";
  if (station === "review") return "review";
  if (station === "workstation" || station === "challenge_plot") return "work";
  if (station === "deliberation") return "think";
  return "idle";
}

export function projectAgentsIntoRoom(
  agents: AgentSemanticState[],
  district: Landmark,
  messages: WorldMessageEvent[],
): IsoAgentProjection[] {
  const byStation = new Map<IsoStationKind, AgentSemanticState[]>();
  const bubbleAgentIds = new Set(
    [...messages]
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
      .slice(0, 6)
      .map((message) => message.agent_id),
  );
  agents.forEach((agent) => {
    const station = stationForAgent(agent, messages);
    byStation.set(station, [...(byStation.get(station) ?? []), agent]);
  });

  return agents.map((agent) => {
    const stationKind = stationForAgent(agent, messages);
    const station = BASE_STATIONS.find((item) => item.kind === stationKind) ?? BASE_STATIONS[1]!;
    const stationPeers = byStation.get(stationKind) ?? [];
    const index = Math.max(0, stationPeers.findIndex((peer) => peer.agent_id === agent.agent_id));
    const hash = stableHash(`${VISUAL_SCHEMA_VERSION}|${district.id}|${agent.agent_id}`);
    const angle = index * Math.PI * (3 - Math.sqrt(5)) + (hash % 60) / 60;
    const radius = index === 0 ? 0 : 0.85 + Math.sqrt(index) * 0.55;
    const jitterX = ((hash % 3) - 1) * 0.16;
    const jitterY = (((hash >> 4) % 3) - 1) * 0.16;
    const point = isoToScreen(
      station.gridX + Math.cos(angle) * radius + jitterX,
      station.gridY + Math.sin(angle) * radius + jitterY,
      station.elevation ?? 0,
    );
    const message = bubbleAgentIds.has(agent.agent_id)
      ? latestMessageForAgent(agent.agent_id, messages)
      : undefined;
    const bubble = message ? message.content.replace(/\s+/g, " ").slice(0, 112) : null;
    const x = Math.min(92, Math.max(8, point.x));
    const y = Math.min(86, Math.max(12, point.y));
    const facing: IsoAgentProjection["facing"] = hash % 2 === 0 ? "right" : "left";
    return {
      agent,
      station: stationKind,
      x,
      y,
      z: station.gridX + station.gridY + index,
      facing,
      bubble,
      motion: motionForStation(stationKind, Boolean(bubble)),
    };
  }).sort((a, b) => a.z - b.z);
}

export function constructionStageForMission(mission: Mission): ChallengeConstructionProjection["stage"] {
  if (mission.state === "completed" || mission.resolved_at) return "monument";
  if (mission.state === "review") return "review";
  if (mission.state === "active") return "work";
  if (mission.state === "forming" || mission.state === "open") return "foundation";
  if (mission.state === "cancelled" || mission.state === "failed" || mission.state === "archived") return "archive";
  return "blueprint";
}

export function projectChallengeConstructions(
  district: Landmark,
  missions: Mission[],
): ChallengeConstructionProjection[] {
  return missions
    .filter((mission) => !mission.hosting_space_id || mission.hosting_space_id === district.space_id)
    .slice(0, 4)
    .map((mission, index) => {
      const point = isoToScreen(9 + index, 2 + index * 0.7, index % 2);
      const participants = mission.participants?.length ?? 0;
      const progress = Math.min(1, (
        (mission.final_artifact_version_ids?.length ?? 0) * 0.35
        + participants * 0.08
        + (mission.winning_submission_id ? 0.4 : 0)
      ));
      return {
        id: mission.mission_id,
        title: mission.title,
        stage: constructionStageForMission(mission),
        progress,
        x: Math.min(92, Math.max(10, point.x)),
        y: Math.min(72, Math.max(10, point.y)),
      };
    });
}

export function buildIsoRoomProjection(params: {
  district: Landmark;
  agents: AgentSemanticState[];
  messages: WorldMessageEvent[];
  missions: Mission[];
}): IsoRoomProjection {
  return {
    district: params.district,
    template: templateForDistrict(params.district),
    stations: BASE_STATIONS,
    agents: projectAgentsIntoRoom(params.agents, params.district, params.messages),
    constructions: projectChallengeConstructions(params.district, params.missions),
  };
}
