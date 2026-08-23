// World data access. Topology is fetched once (ETag makes revalidation free);
// semantic population is fetched on load and after any realtime gap — never
// per event and never per frame.

import { API_URL } from "@/lib/api";
import type { WorldSnapshot } from "./store";
import type { WorldManifest } from "./types";

let manifestCache: { etag: string | null; manifest: WorldManifest } | null = null;

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

export function worldSocket(): WebSocket {
  const wsUrl = API_URL.replace("http://", "ws://").replace("https://", "wss://");
  return new WebSocket(`${wsUrl}/v1/realtime/web`);
}
