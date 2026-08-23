// Shared world types. Mirrors the server's semantic model: the browser owns
// every cosmetic value below (x/y/phase), the server owns none of them.

export type LandmarkState = "ACTIVE" | "COMING_SOON" | "LOCKED";

export interface Landmark {
  id: string;
  name: string;
  state: LandmarkState;
  space_id: string | null;
  purpose: string;
  future_sprint?: string;
  shape: string;
  x: number;
  y: number;
  radius: number;
}

export interface WorldManifest {
  world_version: string;
  name: string;
  bounds: { min_x: number; min_y: number; max_x: number; max_y: number };
  landmarks: Landmark[];
  portals: { id: string; from: string; to: string }[];
  nav_edges: [string, string][];
  lod: {
    mid_zoom_below: number;
    far_zoom_below: number;
    cluster_population_above: number;
  };
}

export interface AvatarSpec {
  schema_version: string;
  body: "orb" | "capsule" | "hex" | "bot";
  visor: "round" | "wide" | "hex" | "mono";
  antenna: "none" | "single" | "twin" | "dish" | "telescope";
  accessory: "none" | "satchel" | "book" | "wrench" | "scanner";
  emblem: "none" | "star" | "atom" | "code" | "sigma" | "compass";
  expression: "neutral" | "curious" | "focused" | "cheerful";
  tint: string;
  accent?: string;
}

export type Activity =
  | "idle" | "exploring" | "reading" | "discussing" | "debating"
  | "researching" | "computing" | "writing" | "reviewing" | "building"
  | "offline" | "error";

/** Semantic state the server owns. */
export interface AgentSemanticState {
  agent_id: string;
  name: string;
  activity: Activity;
  avatar: AvatarSpec;
  space_id: string;
  /** Set while a transition is being animated locally. */
  from_space_id?: string | null;
  transition_at?: number;
}

/** Cosmetic state the browser owns; never sent anywhere. */
export interface AgentVisualState {
  x: number;
  y: number;
  targetX: number;
  targetY: number;
  /** Waypoints through the nav graph, in world units. */
  path: { x: number; y: number }[];
  phase: number;
  speaking: number; // countdown in ms for a speech indicator
}
