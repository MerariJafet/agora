import type { Mission } from "@/lib/missions";
import type { AgentSemanticState, Landmark, WorldMessageEvent } from "./types";

export const VISUAL_SCHEMA_VERSION = "visual-world-manifest.v3.iso-room";
export const MAX_VISIBLE_BUBBLES = 4;
export const TARGET_OCCUPANCY_RATIO = 0.16;
export const MIN_ROOM_COLUMNS = 18;
export const MIN_ROOM_ROWS = 14;

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
  capacity: number;
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
  tileX: number;
  tileY: number;
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
  sizing: IsoRoomSizing;
  stations: IsoStation[];
  agents: IsoAgentProjection[];
  constructions: ChallengeConstructionProjection[];
}

export interface IsoRoomSizing {
  columns: number;
  rows: number;
  usableTiles: number;
  targetOccupancyRatio: number;
}

const DEFAULT_SIZING: IsoRoomSizing = {
  columns: MIN_ROOM_COLUMNS,
  rows: MIN_ROOM_ROWS,
  usableTiles: MIN_ROOM_COLUMNS * MIN_ROOM_ROWS,
  targetOccupancyRatio: TARGET_OCCUPANCY_RATIO,
};

export function stableHash(input: string): number {
  let hash = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    hash ^= input.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  return hash >>> 0;
}

export function roomSizingForPopulation(agentCount: number): IsoRoomSizing {
  const neededTiles = Math.ceil(Math.max(agentCount, 1) / TARGET_OCCUPANCY_RATIO);
  const targetAspect = 1.34;
  const columns = Math.max(MIN_ROOM_COLUMNS, Math.ceil(Math.sqrt(neededTiles * targetAspect)));
  const rows = Math.max(MIN_ROOM_ROWS, Math.ceil(neededTiles / columns));
  const scienceScale = agentCount >= 30 ? { columns: 24, rows: 18 } : { columns: 0, rows: 0 };
  return {
    columns: Math.max(columns, scienceScale.columns),
    rows: Math.max(rows, scienceScale.rows),
    usableTiles: Math.max(columns, scienceScale.columns) * Math.max(rows, scienceScale.rows),
    targetOccupancyRatio: TARGET_OCCUPANCY_RATIO,
  };
}

export function stationsForRoom(sizing: IsoRoomSizing): IsoStation[] {
  const col = sizing.columns - 1;
  const row = sizing.rows - 1;
  return [
    { kind: "portal", label: "Portal", gridX: Math.round(col * 0.08), gridY: Math.round(row * 0.52), capacity: 10 },
    { kind: "conversation", label: "Zona de conversacion", gridX: Math.round(col * 0.34), gridY: Math.round(row * 0.42), capacity: 24 },
    { kind: "deliberation", label: "Mesa de deliberacion", gridX: Math.round(col * 0.53), gridY: Math.round(row * 0.24), capacity: 20 },
    { kind: "voting", label: "Terminal de votacion", gridX: Math.round(col * 0.73), gridY: Math.round(row * 0.42), capacity: 14 },
    { kind: "evidence", label: "Estacion de evidencia", gridX: Math.round(col * 0.42), gridY: Math.round(row * 0.69), capacity: 24 },
    { kind: "review", label: "Mesa de revision", gridX: Math.round(col * 0.78), gridY: Math.round(row * 0.72), capacity: 16 },
    { kind: "workstation", label: "Estaciones de trabajo", gridX: Math.round(col * 0.22), gridY: Math.round(row * 0.76), capacity: 28 },
    { kind: "challenge_plot", label: "Parcela del reto", gridX: Math.round(col * 0.84), gridY: Math.round(row * 0.17), elevation: 1, capacity: 18 },
  ];
}

export function isoToScreen(
  gridX: number,
  gridY: number,
  elevation = 0,
  sizing: IsoRoomSizing = DEFAULT_SIZING,
) {
  const tileWidthPercent = 88 / Math.max(sizing.columns + sizing.rows, 1);
  const tileHeightPercent = 72 / Math.max(sizing.columns + sizing.rows, 1);
  const levelHeightPercent = 4.2;
  return {
    x: 50 + (gridX - gridY) * tileWidthPercent,
    y: 18 + (gridX + gridY) * tileHeightPercent - elevation * levelHeightPercent,
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

function clampTile(value: number, max: number): number {
  return Math.max(1, Math.min(max - 2, value));
}

function stationAnchorForAgent(
  station: IsoStation,
  stationKind: IsoStationKind,
  stationPeerCount: number,
  index: number,
  hash: number,
  sizing: IsoRoomSizing,
) {
  const podOffsets: Partial<Record<IsoStationKind, [number, number][]>> = {
    conversation: [[0, 0], [-5, 2], [4, 3], [-3, -3], [6, -1]],
    deliberation: [[0, 0], [-5, 2], [5, 2], [0, -5], [-3, 6], [4, -4]],
    evidence: [[0, 0], [-5, 2], [5, 1], [0, 4]],
    workstation: [[0, 0], [-5, -1], [4, 3], [-2, 4]],
    review: [[0, 0], [-3, 2], [3, -1]],
  };
  const offsets = podOffsets[stationKind];
  if (!offsets || stationPeerCount <= 6) return station;
  const pod = offsets[(hash + Math.floor(index / 5)) % offsets.length]!;
  return {
    ...station,
    gridX: clampTile(station.gridX + pod[0], sizing.columns),
    gridY: clampTile(station.gridY + pod[1], sizing.rows),
  };
}

export function projectAgentsIntoRoom(
  agents: AgentSemanticState[],
  district: Landmark,
  messages: WorldMessageEvent[],
  stations: IsoStation[] = stationsForRoom(roomSizingForPopulation(agents.length)),
  sizing: IsoRoomSizing = roomSizingForPopulation(agents.length),
): IsoAgentProjection[] {
  const byStation = new Map<IsoStationKind, AgentSemanticState[]>();
  const bubbleAgentIds = new Set(
    [...messages]
      .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
      .slice(0, MAX_VISIBLE_BUBBLES)
      .map((message) => message.agent_id),
  );
  agents.forEach((agent) => {
    const station = stationForAgent(agent, messages);
    byStation.set(station, [...(byStation.get(station) ?? []), agent]);
  });

  const occupied = new Set<string>();
  const sortedAgents = [...agents].sort((a, b) =>
    stableHash(`${VISUAL_SCHEMA_VERSION}|${district.id}|${a.agent_id}`)
    - stableHash(`${VISUAL_SCHEMA_VERSION}|${district.id}|${b.agent_id}`),
  );

  return sortedAgents.map((agent) => {
    const stationKind = stationForAgent(agent, messages);
    const station = stations.find((item) => item.kind === stationKind) ?? stations[1]!;
    const stationPeers = byStation.get(stationKind) ?? [];
    const index = Math.max(0, stationPeers.findIndex((peer) => peer.agent_id === agent.agent_id));
    const hash = stableHash(`${VISUAL_SCHEMA_VERSION}|${district.id}|${agent.agent_id}`);
    const anchor = stationAnchorForAgent(station, stationKind, stationPeers.length, index, hash, sizing);
    let tileX = anchor.gridX;
    let tileY = anchor.gridY;
    let found = false;
    for (let ring = 0; ring <= Math.max(sizing.columns, sizing.rows) && !found; ring += 1) {
      const candidates: [number, number][] = [];
      for (let dx = -ring; dx <= ring; dx += 1) {
        for (let dy = -ring; dy <= ring; dy += 1) {
          if (Math.max(Math.abs(dx), Math.abs(dy)) !== ring) continue;
          candidates.push([anchor.gridX + dx, anchor.gridY + dy]);
        }
      }
      candidates.sort((left, right) =>
        stableHash(`${hash}|${left[0]}|${left[1]}`) - stableHash(`${hash}|${right[0]}|${right[1]}`),
      );
      const candidate = candidates.find(([x, y]) =>
        x >= 1 && y >= 1 && x < sizing.columns - 1 && y < sizing.rows - 1 && !occupied.has(`${x}:${y}`),
      );
      if (candidate) {
        [tileX, tileY] = candidate;
        occupied.add(`${tileX}:${tileY}`);
        found = true;
      }
    }
    const point = isoToScreen(tileX, tileY, anchor.elevation ?? 0, sizing);
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
      z: tileX + tileY + index,
      facing,
      bubble,
      motion: motionForStation(stationKind, Boolean(bubble)),
      tileX,
      tileY,
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
  sizing: IsoRoomSizing = DEFAULT_SIZING,
): ChallengeConstructionProjection[] {
  const stations = stationsForRoom(sizing);
  const plot = stations.find((station) => station.kind === "challenge_plot") ?? stations[7]!;
  return missions
    .filter((mission) => !mission.hosting_space_id || mission.hosting_space_id === district.space_id)
    .slice(0, 4)
    .map((mission, index) => {
      const point = isoToScreen(plot.gridX - index, plot.gridY + index, index % 2, sizing);
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
  const sizing = roomSizingForPopulation(params.agents.length);
  const stations = stationsForRoom(sizing);
  return {
    district: params.district,
    template: templateForDistrict(params.district),
    sizing,
    stations,
    agents: projectAgentsIntoRoom(params.agents, params.district, params.messages, stations, sizing),
    constructions: projectChallengeConstructions(params.district, params.missions, sizing),
  };
}
