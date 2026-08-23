// WorldStore (S3-T15): normalized client state = static topology + semantic
// agent state + cosmetic visual state.
//
// Rules:
// - Deltas apply idempotently; replaying the same event is a no-op.
// - Late events converge to semantic truth (a transition whose destination is
//   already the agent's space just snaps, it never replays obsolete motion).
// - A missed realtime connection is repaired by re-requesting the semantic
//   snapshot, never by refetching topology per event.
// - Agents that leave are deleted from both maps, so nothing leaks.

import type {
  AgentSemanticState,
  AgentVisualState,
  Activity,
  AvatarSpec,
  Landmark,
  WorldManifest,
} from "./types";

export interface WorldSnapshot {
  spaces: Record<string, { count: number; agents: {
    agent_id: string; name: string; activity: Activity; avatar: AvatarSpec;
  }[] }>;
  total_present: number;
}

/** Deterministic placement slot: same agent lands in the same spot for every
 *  observer, without the server synchronizing a single coordinate. */
export function slotFor(agentId: string, landmark: Landmark, index: number): {
  x: number;
  y: number;
} {
  let hash = 2166136261;
  for (let i = 0; i < agentId.length; i += 1) {
    hash ^= agentId.charCodeAt(i);
    hash = Math.imul(hash, 16777619) >>> 0;
  }
  const ring = 1 + ((hash >>> 3) % 3);
  const angle = ((hash % 360) + index * 37) * (Math.PI / 180);
  const distance = (landmark.radius * 0.35) + ring * (landmark.radius * 0.16);
  return {
    x: landmark.x + Math.cos(angle) * distance,
    y: landmark.y + Math.sin(angle) * distance,
  };
}

export class WorldStore {
  manifest: WorldManifest | null = null;
  agents = new Map<string, AgentSemanticState>();
  visuals = new Map<string, AgentVisualState>();
  /** Bumped on any change so React can re-render cheaply. */
  version = 0;
  private listeners = new Set<() => void>();

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private changed() {
    this.version += 1;
    this.listeners.forEach((l) => l());
  }

  setManifest(manifest: WorldManifest) {
    this.manifest = manifest;
    this.changed();
  }

  landmark(id: string): Landmark | undefined {
    return this.manifest?.landmarks.find((l) => l.id === id);
  }

  landmarkForSpace(spaceId: string | null | undefined): Landmark | undefined {
    if (!spaceId) return undefined;
    return this.manifest?.landmarks.find((l) => l.space_id === spaceId);
  }

  /** Full semantic snapshot: authoritative, prunes agents that left. */
  applySnapshot(snapshot: WorldSnapshot) {
    const seen = new Set<string>();
    Object.entries(snapshot.spaces).forEach(([spaceId, space]) => {
      space.agents.forEach((agent, index) => {
        seen.add(agent.agent_id);
        this.upsertAgent({
          agent_id: agent.agent_id,
          name: agent.name,
          activity: agent.activity,
          avatar: agent.avatar,
          space_id: spaceId,
        }, index, true);
      });
    });
    [...this.agents.keys()].forEach((id) => {
      if (!seen.has(id)) this.removeAgent(id);
    });
    this.changed();
  }

  private placement(agentId: string, spaceId: string, index?: number) {
    const landmark = this.landmarkForSpace(spaceId);
    if (!landmark) return { x: 0, y: 0 };
    const idx = index ?? [...this.agents.values()].filter(
      (a) => a.space_id === spaceId,
    ).length;
    return slotFor(agentId, landmark, idx);
  }

  upsertAgent(state: AgentSemanticState, index?: number, snap = false) {
    const existing = this.agents.get(state.agent_id);
    this.agents.set(state.agent_id, { ...existing, ...state });
    const target = this.placement(state.agent_id, state.space_id, index);
    const visual = this.visuals.get(state.agent_id);
    if (!visual || snap) {
      // Joining late (or reconnecting) places the agent AT its destination
      // rather than replaying a movement that already finished.
      this.visuals.set(state.agent_id, {
        x: visual && !snap ? visual.x : target.x,
        y: visual && !snap ? visual.y : target.y,
        targetX: target.x,
        targetY: target.y,
        path: [],
        phase: Math.random() * Math.PI * 2,
        speaking: 0,
      });
    } else {
      visual.targetX = target.x;
      visual.targetY = target.y;
    }
  }

  removeAgent(agentId: string) {
    this.agents.delete(agentId);
    this.visuals.delete(agentId);
  }

  /** Semantic transition → local animation over the nav graph. */
  applyTransition(frame: {
    agent_id: string;
    name?: string;
    from_space_id?: string | null;
    to_space_id?: string | null;
    activity?: Activity;
    avatar?: AvatarSpec;
  }) {
    if (!frame.to_space_id) {
      this.removeAgent(frame.agent_id);
      this.changed();
      return;
    }
    const existing = this.agents.get(frame.agent_id);
    const next: AgentSemanticState = {
      agent_id: frame.agent_id,
      name: frame.name ?? existing?.name ?? frame.agent_id,
      activity: frame.activity ?? existing?.activity ?? "idle",
      avatar: frame.avatar ?? existing?.avatar ?? defaultAvatar(),
      space_id: frame.to_space_id,
      from_space_id: frame.from_space_id ?? null,
      transition_at: Date.now(),
    };
    // Idempotent: a duplicate transition to the space we already occupy does
    // not restart the animation.
    const alreadyThere = existing?.space_id === frame.to_space_id;
    this.upsertAgent(next);
    const visual = this.visuals.get(frame.agent_id);
    if (visual && !alreadyThere) {
      visual.path = this.pathBetween(frame.from_space_id ?? null, frame.to_space_id);
    }
    this.changed();
  }

  setActivity(agentId: string, activity: Activity) {
    const agent = this.agents.get(agentId);
    if (!agent || agent.activity === activity) return;
    agent.activity = activity;
    this.changed();
  }

  setAvatar(agentId: string, avatar: AvatarSpec) {
    const agent = this.agents.get(agentId);
    if (!agent) return;
    agent.avatar = avatar;
    this.changed();
  }

  markSpeaking(agentId: string) {
    const visual = this.visuals.get(agentId);
    if (visual) visual.speaking = 3200;
    this.changed();
  }

  /** BFS over the nav graph; cosmetic only, the server never sees a path. */
  pathBetween(fromSpace: string | null, toSpace: string): { x: number; y: number }[] {
    const manifest = this.manifest;
    const from = this.landmarkForSpace(fromSpace);
    const to = this.landmarkForSpace(toSpace);
    if (!manifest || !from || !to) return [];
    const adjacency = new Map<string, string[]>();
    manifest.nav_edges.forEach(([a, b]) => {
      adjacency.set(a, [...(adjacency.get(a) ?? []), b]);
      adjacency.set(b, [...(adjacency.get(b) ?? []), a]);
    });
    const queue: string[][] = [[from.id]];
    const visited = new Set([from.id]);
    while (queue.length) {
      const route = queue.shift()!;
      const tail = route[route.length - 1]!;
      if (tail === to.id) {
        return route
          .slice(1)
          .map((id) => this.landmark(id))
          .filter((l): l is Landmark => Boolean(l))
          .map((l) => ({ x: l.x, y: l.y }));
      }
      (adjacency.get(tail) ?? []).forEach((next) => {
        if (!visited.has(next)) {
          visited.add(next);
          queue.push([...route, next]);
        }
      });
    }
    return [{ x: to.x, y: to.y }];
  }

  agentsInSpace(spaceId: string): AgentSemanticState[] {
    return [...this.agents.values()].filter((a) => a.space_id === spaceId);
  }

  populationBySpace(): Map<string, number> {
    const counts = new Map<string, number>();
    this.agents.forEach((agent) => {
      counts.set(agent.space_id, (counts.get(agent.space_id) ?? 0) + 1);
    });
    return counts;
  }
}

export function defaultAvatar(): AvatarSpec {
  return {
    schema_version: "1.0",
    body: "orb",
    visor: "round",
    antenna: "none",
    accessory: "none",
    emblem: "none",
    expression: "neutral",
    tint: "#8a94ad",
  };
}
