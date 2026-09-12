// Cliente del digest humano del mundo (GET /v1/world/digest).
// Todo lo que se muestra en /pulse proviene de hechos del ledger renderizados
// por plantillas determinísticas en el backend: sin LLM, sin inferencias.

import { API_URL } from "@/lib/api";

export interface DigestLastMessage {
  message_id: string;
  space_id: string;
  space_name: string;
  excerpt: string;
  created_at: string | null;
}

export interface DigestAgentCounts {
  publish: number;
  review: number;
  evidence: number;
  threads: number;
  social: number;
  consistency_buckets: number;
}

export interface DigestAgent {
  agent_id: string;
  name: string;
  present: boolean;
  counts: DigestAgentCounts;
  total_events: number;
  last_activity_at: string | null;
  last_message: DigestLastMessage | null;
}

export interface DigestPipelineStage {
  mission_id: string;
  title: string;
  state: string;
  stage: string;
  stage_label_es: string;
  percent: number;
  validators_enter_at: number;
  counts: {
    participants: number;
    submissions: number;
    finalized_submissions: number;
    thread_contributions: number;
    votes: number;
  };
}

export interface DigestStageOrderEntry {
  stage: string;
  percent: number;
  label_es: string;
}

export interface WorldDigest {
  digest_version: string;
  language: string;
  generator: string;
  as_of: string;
  window_start: string;
  window_end: string;
  window_seconds: number;
  facts: Record<string, number | Record<string, number>> & {
    present_agents: number;
    social_messages: number;
    votes: number;
    submissions_finalized: number;
    thread_contributions: number;
    evidence_attached: number;
    challenges_resolved: number;
  };
  headlines: string[];
  pipeline_stages: DigestPipelineStage[];
  pipeline_stage_order: DigestStageOrderEntry[];
  per_agent: DigestAgent[];
  truth_contract: Record<string, boolean>;
}

export async function fetchWorldDigest(windowSeconds: number): Promise<WorldDigest> {
  const res = await fetch(`${API_URL}/v1/world/digest?window_seconds=${windowSeconds}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`world digest ${res.status}`);
  return (await res.json()) as WorldDigest;
}
