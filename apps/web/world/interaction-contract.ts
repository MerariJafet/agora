import type { AgentSemanticState, Landmark } from "./types";

export type EntityFocus =
  | { kind: "agent"; id: string }
  | { kind: "challenge"; id: string }
  | { kind: "district"; id: string };

export function encodeFocus(focus: EntityFocus): string {
  return `${focus.kind}:${focus.id}`;
}

export function parseFocus(value: string | null): EntityFocus | null {
  if (!value) return null;
  const [kind, ...rest] = value.split(":");
  const id = rest.join(":");
  if (!id) return null;
  if (kind === "agent" || kind === "challenge" || kind === "district") return { kind, id };
  return null;
}

export function districtHref(landmark: Landmark): string {
  return `/world/district/${encodeURIComponent(landmark.id)}`;
}

export function challengeHref(challengeId: string): string {
  return `/world/challenge/${encodeURIComponent(challengeId)}`;
}

export function agentDistrictHref(agent: AgentSemanticState, spaces: Landmark[]): string {
  const place = spaces.find((space) => space.space_id === agent.space_id || space.id === agent.space_id);
  if (!place) return `/agents/${encodeURIComponent(agent.agent_id)}`;
  return `${districtHref(place)}?focus=${encodeURIComponent(encodeFocus({ kind: "agent", id: agent.agent_id }))}`;
}

export function focusedDistrictHref(landmark: Landmark, focus: EntityFocus): string {
  return `${districtHref(landmark)}?focus=${encodeURIComponent(encodeFocus(focus))}`;
}
