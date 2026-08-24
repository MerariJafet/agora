import { getJson } from "./api";

export interface KnowledgeSource {
  source_id: string;
  adapter_id: string;
  name: string;
  domain: string;
  allowed_hosts: string[];
  capabilities: string[];
  freshness_contract: string;
  license_terms: string;
  ttl_seconds: number;
  upstream_call_count: number;
  cache_hit_count: number;
}

export interface WorldPulseEvent {
  pulse_event_id: string;
  cluster_key: string;
  title: string;
  summary: string;
  freshness_contract: string;
  source_count: number;
  latest_snapshot_id: string;
  updated_at: string;
}

export function listKnowledgeSources(): Promise<{ sources: KnowledgeSource[] }> {
  return getJson<{ sources: KnowledgeSource[] }>("/v1/knowledge/sources");
}

export function listWorldPulseEvents(): Promise<{ events: WorldPulseEvent[] }> {
  return getJson<{ events: WorldPulseEvent[] }>("/v1/world-pulse/events");
}
