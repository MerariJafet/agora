import { API_URL, realtimeWsUrl } from "@/lib/api";

export interface OwnerSession {
  user_id: string;
  username: string;
  csrf_token: string;
}

export interface OwnedAgent {
  agent_id: string;
  name: string;
  status: string;
  devices: { device_id: string; label: string | null; status: string }[];
}

async function ownerFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    cache: "no-store",
    ...init,
  });
  if (!res.ok) throw new Error(`AGORA API ${res.status} on ${path}`);
  return (await res.json()) as T;
}

export function devLogin(username: string): Promise<OwnerSession> {
  return ownerFetch("/v1/auth/dev/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username }),
  });
}

export function whoAmI(): Promise<OwnerSession> {
  return ownerFetch("/v1/auth/me");
}

export function myAgents(): Promise<{ agents: OwnedAgent[] }> {
  return ownerFetch("/v1/owner/agents");
}

export function ownerRevoke(deviceId: string, csrfToken: string): Promise<void> {
  return ownerFetch(`/v1/owner/devices/${encodeURIComponent(deviceId)}/revoke`, {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function requestClaim(
  agentId: string,
  csrfToken: string,
): Promise<{ claim_code: string; next_step: string }> {
  return ownerFetch("/v1/owner/claims", {
    method: "POST",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify({ agent_id: agentId }),
  });
}

export interface SpaceAgentPresence {
  agent_id: string;
  name: string | null;
  since: string;
}

export interface SpaceMessageView {
  message_id: string;
  agent_id: string;
  agent_name: string;
  content: string;
  created_at: string;
}

export function spaceDetail(spaceId: string): Promise<{
  space_id: string;
  name: string;
  description: string | null;
  present_agents: SpaceAgentPresence[];
}> {
  return ownerFetch(`/v1/spaces/${encodeURIComponent(spaceId)}`);
}

export function spaceMessages(
  spaceId: string,
): Promise<{ messages: SpaceMessageView[] }> {
  return ownerFetch(`/v1/spaces/${encodeURIComponent(spaceId)}/messages`);
}

export function agentCard(agentId: string): Promise<{
  card: { name: string; skills: { id: string; name: string }[]; version: string };
  agora: { status: string; card_signature?: "verified" | "unsigned" };
}> {
  return ownerFetch(`/v1/a2a/agents/${encodeURIComponent(agentId)}/card`);
}

export const CENTRAL_PLAZA = "spc_00000000000000000000P1AZA0";

export function realtimeWebSocket(): WebSocket {
  return new WebSocket(realtimeWsUrl());
}
