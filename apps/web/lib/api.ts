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

export async function revokeDevice(deviceId: string): Promise<void> {
  const res = await fetch(
    `${API_URL}/v1/devices/${encodeURIComponent(deviceId)}/revoke`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`Revoke failed (${res.status})`);
}
