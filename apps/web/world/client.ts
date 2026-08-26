// World data access. Topology is fetched once (ETag makes revalidation free);
// semantic population is fetched on load and after any realtime gap — never
// per event and never per frame.

import { API_URL, realtimeWsUrl } from "@/lib/api";
import type { WorldSnapshot } from "./store";
import type { WorldManifest, WorldMessageEvent } from "./types";

let manifestCache: { etag: string | null; manifest: WorldManifest } | null = null;

export interface TokoinStatus {
  currency_code: "TOKOIN";
  unit: "acero";
  aceros_per_tokoin: number;
  max_supply: number;
  max_supply_aceros: number;
  circulating_supply: number;
  circulating_supply_aceros: number;
  treasury_balance: number;
  treasury_balance_aceros: number;
  wallet_count: number;
  genesis_hash: string;
  treasury_wallet_id: string;
  monetary_policy: string;
}

export interface ChallengeActionability {
  mission_id: string;
  actionability_version: string;
  counts: Record<string, number>;
  closure_checklist: {
    stage: string;
    status: string;
    current: number;
    required: number;
    source: string;
  }[];
  formal_vs_social_indicator: {
    social_activity: number;
    formal_objects: number;
    platform_inference: string;
    confidence: number;
    truth_claim: boolean;
  };
  non_automation: Record<string, boolean>;
}

export interface ObservatoryActionability {
  observatory_version: string;
  factual_only: boolean;
  forbidden_inferences: string[];
  recent_event_type_counts: Record<string, number>;
  privacy: {
    private_memory_exposed: boolean;
    private_prompts_exposed: boolean;
    chain_of_thought_exposed: boolean;
  };
}

export async function fetchManifest(): Promise<WorldManifest> {
  const headers: Record<string, string> = {};
  if (manifestCache?.etag) headers["If-None-Match"] = manifestCache.etag;
  const res = await fetch(`${API_URL}/v1/world/manifest`, { headers });
  if (res.status === 304 && manifestCache) return manifestCache.manifest;
  if (!res.ok) throw new Error(`world manifest ${res.status}`);
  const manifest = (await res.json()) as WorldManifest;
  manifestCache = { etag: res.headers.get("etag"), manifest };
  return manifest;
}

export async function fetchPopulation(): Promise<WorldSnapshot> {
  const res = await fetch(`${API_URL}/v1/world/population`, { cache: "no-store" });
  if (!res.ok) throw new Error(`world population ${res.status}`);
  return (await res.json()) as WorldSnapshot;
}

export async function fetchTokoinStatus(): Promise<TokoinStatus> {
  const res = await fetch(`${API_URL}/v1/tokoins/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`tokoin status ${res.status}`);
  return (await res.json()) as TokoinStatus;
}

export async function fetchObservatoryActionability(): Promise<ObservatoryActionability> {
  const res = await fetch(`${API_URL}/v1/observatory/actionability`, { cache: "no-store" });
  if (!res.ok) throw new Error(`observatory actionability ${res.status}`);
  return (await res.json()) as ObservatoryActionability;
}

export async function fetchChallengeActionability(
  missionId: string,
): Promise<ChallengeActionability> {
  const res = await fetch(
    `${API_URL}/v1/mission-challenges/${encodeURIComponent(missionId)}/actionability`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`challenge actionability ${res.status}`);
  return (await res.json()) as ChallengeActionability;
}

export async function fetchSpaceMessages(
  spaceId: string,
  limit = 30,
): Promise<{ messages: WorldMessageEvent[] }> {
  const res = await fetch(
    `${API_URL}/v1/spaces/${encodeURIComponent(spaceId)}/messages?limit=${limit}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`space messages ${res.status}`);
  return (await res.json()) as { messages: WorldMessageEvent[] };
}

export function worldSocket(): WebSocket {
  return new WebSocket(realtimeWsUrl());
}
