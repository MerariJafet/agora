import type { AgentDetailView, AgentEventView, AgentView } from "@agora/sdk-typescript";

// Same-site rule: the owner session cookie is SameSite=Lax, so the API must
// share the page's hostname (localhost↔localhost or 127.0.0.1↔127.0.0.1 —
// ports don't matter for site identity) or the realtime WS handshake would
// silently lose the cookie. Default derives from the current page.
export const API_URL =
  process.env.NEXT_PUBLIC_AGORA_API_URL ??
  (typeof window !== "undefined"
    ? "/agora-api"
    : "http://127.0.0.1:8700");

export function realtimeWsUrl(): string {
  const configured = process.env.NEXT_PUBLIC_AGORA_WS_URL;
  if (configured) return configured;
  if (typeof window === "undefined") return "ws://127.0.0.1:8700/v1/realtime/web";
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.hostname}:8700/v1/realtime/web`;
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
