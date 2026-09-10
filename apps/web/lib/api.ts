import { resolveRealtimeWsUrl } from "./connection";
import type { AgentDetailView, AgentEventView, AgentView } from "@agora/sdk-typescript";

// Same-site rule: the owner session cookie is SameSite=Lax, so the API must
// share the page's hostname (localhost↔localhost or 127.0.0.1↔127.0.0.1 —
// ports don't matter for site identity) or the realtime WS handshake would
// silently lose the cookie. Default derives from the current page.
export const API_URL =
  process.env.NEXT_PUBLIC_AGORA_API_URL ??
  (typeof window !== "undefined"
    ? "/agora-api"
    : (process.env.AGORA_CANONICAL_API_URL ?? "http://127.0.0.1:8700"));

export function realtimeWsUrl(): string {
  return resolveRealtimeWsUrl({
    configured: process.env.NEXT_PUBLIC_AGORA_WS_URL,
    api: process.env.NEXT_PUBLIC_AGORA_API_URL ??
      (typeof window === "undefined"
        ? (process.env.AGORA_CANONICAL_API_URL ?? "http://127.0.0.1:8700")
        : undefined),
    pageUrl: typeof window !== "undefined" ? window.location.href : undefined,
    legacyPort: process.env.NEXT_PUBLIC_AGORA_API_PORT,
  });
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`AGORA API ${res.status} on ${path}`);
  return (await res.json()) as T;
}

export function listAgents(): Promise<{ agents: AgentView[] }> {
  return getJson("/v1/agents");
}

export function getAgent(agentId: string): Promise<AgentDetailView> {
  return getJson(`/v1/agents/${encodeURIComponent(agentId)}`);
}

export function getAgentEvents(
  agentId: string,
): Promise<{ events: AgentEventView[] }> {
  return getJson(`/v1/agents/${encodeURIComponent(agentId)}/events`);
}

// Device revocation requires device or owner authority (Sprint 01.1 hardening):
// the web shell has neither until human accounts land in Sprint 02 (ADR-0009).
// Owners revoke from the machine that holds the key: `agora revoke`.
