import type { Mission } from "@/lib/missions";
import type { AgentSemanticState, Landmark } from "./types";
import type { ObservatoryEvent } from "./observatory";

export const VISUAL_SCHEMA_VERSION = "visual-world-manifest.v1";

export type ConstructionStage =
  | "hologram"
  | "foundation"
  | "working"
  | "review"
  | "monument"
  | "incomplete";

export interface VisualConstruction {
  id: string;
  seed: string;
  title: string;
  district_id: string;
  stage: ConstructionStage;
  environment_class: "REAL" | "TEST" | "UNKNOWN" | "LEGACY";
  footprint: "diamond" | "forum" | "tower" | "archive" | "forge";
  modules: number;
  participants: number;
  provenance: {
    source: "landmark" | "mission";
    source_id: string;
    facts_only: true;
  };
}

export interface VisualDistrict {
  id: string;
  name: string;
  vocation: string;
  population: number;
  state: Landmark["state"];
  constructions: VisualConstruction[];
}

export interface VisualWorldManifest {
  schema_version: typeof VISUAL_SCHEMA_VERSION;
  world_instance_id: string;
  world_version: string;
  ruleset_version: string;
  districts: VisualDistrict[];
  social_clusters: {
    space_id: string;
    participant_count: number;
    recent_messages: number;
  }[];
}

function hash(input: string): string {
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < input.length; i += 1) {
    const ch = input.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return `${(h2 >>> 0).toString(16).padStart(8, "0")}${(h1 >>> 0).toString(16).padStart(8, "0")}`;
}

export function visualSeed(params: {
  worldInstanceId: string;
  entityId: string;
  rulesetVersion: string;
  visualSchemaVersion?: string;
}): string {
  return hash([
    params.worldInstanceId,
    params.entityId,
    params.rulesetVersion,
    params.visualSchemaVersion ?? VISUAL_SCHEMA_VERSION,
  ].join("|"));
}

function stageForLandmark(landmark: Landmark): ConstructionStage {
  if (landmark.state === "LOCKED") return "incomplete";
  if (landmark.state === "COMING_SOON") return "hologram";
  if (landmark.shape === "challenge") return "working";
  return "foundation";
}

function stageForMission(mission: Mission): ConstructionStage {
  if (mission.state === "completed") return "monument";
  if (mission.state === "review") return "review";
  if (["active", "forming", "open"].includes(mission.state)) return "working";
  if (["failed", "cancelled", "archived"].includes(mission.state)) return "incomplete";
  return "hologram";
}

function footprint(seed: string, stage: ConstructionStage): VisualConstruction["footprint"] {
  if (stage === "review") return "archive";
  if (stage === "monument") return "tower";
  if (stage === "hologram") return "diamond";
  const options: VisualConstruction["footprint"][] = ["forum", "forge", "archive"];
  return options[Number.parseInt(seed.slice(0, 2), 16) % options.length] ?? "forum";
}

function environmentClass(landmark: Landmark): VisualConstruction["environment_class"] {
  const text = `${landmark.id} ${landmark.name} ${landmark.purpose}`.toLowerCase();
  if (text.includes("test")) return "TEST";
  if (text.includes("legacy")) return "LEGACY";
  if (text.includes("unknown") || landmark.id === "unknown") return "UNKNOWN";
  return "REAL";
}

export function buildVisualWorldManifest(params: {
  worldInstanceId: string;
  worldVersion: string;
  rulesetVersion: string;
  landmarks: Landmark[];
  agents: AgentSemanticState[];
  missions: Mission[];
  events: ObservatoryEvent[];
}): VisualWorldManifest {
  const population = new Map<string, number>();
  params.agents.forEach((agent) => {
    population.set(agent.space_id, (population.get(agent.space_id) ?? 0) + 1);
  });

  const districts = params.landmarks.map((landmark) => {
    const seed = visualSeed({
      worldInstanceId: params.worldInstanceId,
      entityId: landmark.id,
      rulesetVersion: params.rulesetVersion,
    });
    const stage = stageForLandmark(landmark);
    const baseConstruction: VisualConstruction = {
      id: `landmark:${landmark.id}`,
      seed,
      title: landmark.name,
      district_id: landmark.id,
      stage,
      environment_class: environmentClass(landmark),
      footprint: footprint(seed, stage),
      modules: Math.max(1, Math.min(9, Math.round((landmark.radius ?? 120) / 70))),
      participants: population.get(landmark.space_id ?? "") ?? 0,
      provenance: { source: "landmark", source_id: landmark.id, facts_only: true },
    };
    return {
      id: landmark.id,
      name: landmark.name,
      vocation: landmark.purpose,
      population: population.get(landmark.space_id ?? "") ?? 0,
      state: landmark.state,
      constructions: [baseConstruction],
    };
  });

  params.missions.forEach((mission) => {
    const landmark = params.landmarks.find((item) => item.space_id === mission.hosting_space_id);
    if (!landmark) return;
    const seed = visualSeed({
      worldInstanceId: params.worldInstanceId,
      entityId: mission.mission_id,
      rulesetVersion: params.rulesetVersion,
    });
    const stage = stageForMission(mission);
    const district = districts.find((item) => item.id === landmark.id);
    district?.constructions.push({
      id: `mission:${mission.mission_id}`,
      seed,
      title: mission.title,
      district_id: landmark.id,
      stage,
      environment_class: "REAL",
      footprint: footprint(seed, stage),
      modules: Math.max(2, Math.min(12, 2 + Math.floor((mission.reward_aceros ?? 0) / 50_000_000))),
      participants: population.get(mission.hosting_space_id ?? "") ?? 0,
      provenance: { source: "mission", source_id: mission.mission_id, facts_only: true },
    });
  });

  return {
    schema_version: VISUAL_SCHEMA_VERSION,
    world_instance_id: params.worldInstanceId,
    world_version: params.worldVersion,
    ruleset_version: params.rulesetVersion,
    districts,
    social_clusters: [...population.entries()]
      .map(([spaceId, participantCount]) => ({
        space_id: spaceId,
        participant_count: participantCount,
        recent_messages: params.events.filter((event) => (
          event.kind === "social" && event.space_id === spaceId
        )).length,
      }))
      .sort((a, b) => b.participant_count - a.participant_count)
      .slice(0, 8),
  };
}
