import type { AgentDetailView, AgentEventView, AgentView } from "@agora/sdk-typescript";

export const API_URL =
  process.env.NEXT_PUBLIC_AGORA_API_URL ?? "http://127.0.0.1:8700";

async function getJson<T>(path: string): Promise<T> {
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
