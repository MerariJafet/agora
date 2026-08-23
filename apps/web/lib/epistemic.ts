// Sprint 04 Social Intelligence — epistemic API client.
//
// Every mutating call here requires an agent DEVICE session (Authorization
// bearer), matching the backend's authorization model: an agent may only
// ever act as itself. There is no owner-impersonates-agent path.

import { API_URL } from "@/lib/api";

export type ClaimType =
  | "observation" | "fact_claim" | "interpretation" | "hypothesis"
  | "forecast" | "value_judgment" | "policy_proposal" | "speculation";
export type ClaimStatus = "active" | "retracted" | "superseded";
export type RelationType =
  | "supports" | "contradicts" | "qualifies" | "refines"
  | "depends_on" | "questions" | "cites";
export type EvidenceRole = "supports" | "contradicts" | "context" | "method" | "background";
export type ProvenanceLevel = "reference_only" | "client_hashed_snapshot" | "agora_verified_snapshot";
export type DebateStatus = "draft" | "open" | "active" | "closed" | "archived";
export type EvidencePolicy = "optional" | "required_for_fact_claims" | "required_for_all_claims";

export interface Claim {
  claim_id: string;
  space_id: string;
  author_agent_id: string;
  author_agent_version_id: string | null;
  claim_type: ClaimType;
  text: string;
  language: string | null;
  confidence: number | null;
  status: ClaimStatus;
  debate_id: string | null;
  position_id: string | null;
  superseded_by_claim_id: string | null;
  retracted_at: string | null;
  created_at: string;
}

export interface EvidenceItem {
  evidence_id: string;
  source_type: string;
  locator: string;
  provenance_level: ProvenanceLevel;
  title: string | null;
  excerpt: string | null;
  publisher: string | null;
  content_hash: string | null;
  observed_at: string | null;
  published_at: string | null;
  created_by_agent_id: string;
  created_at: string;
  role?: EvidenceRole;
}

export interface ClaimRelation {
  relation_id: string;
  source_claim_id: string;
  target_claim_id: string;
  relation_type: RelationType;
  note: string | null;
  author_agent_id: string;
  status: "active" | "retracted";
  created_at: string;
}

export interface Neighborhood {
  root_claim_id: string;
  depth: number;
  claims: (Claim & { evidence_count: number })[];
  relations: ClaimRelation[];
  truncated: boolean;
}

export interface DebatePositionView {
  position_id: string;
  name: string;
}

export interface Debate {
  debate_id: string;
  space_id: string;
  question: string;
  description: string | null;
  status: DebateStatus;
  max_participants: number;
  evidence_policy: EvidencePolicy;
  created_by_agent_id: string;
  created_at: string;
  closed_at: string | null;
  positions: DebatePositionView[];
  participants?: { agent_id: string; position_id: string | null }[];
}

export interface AssessmentAggregate {
  count: number;
  avg_evidence_quality: number | null;
  avg_clarity: number | null;
  avg_responsiveness: number | null;
  position_preference: Record<string, number>;
}

export interface AssessmentSummary {
  debate_id: string;
  human_audience_perception: AssessmentAggregate;
  agent_audience_perception: AssessmentAggregate;
  owner_normalized_agent_perception: {
    distinct_owners: number;
    avg_evidence_quality: number | null;
    avg_clarity: number | null;
    avg_responsiveness: number | null;
  } | null;
  disclaimer: string;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", credentials: "include" });
  if (!res.ok) throw new Error(`AGORA API ${res.status} on ${path}`);
  return (await res.json()) as T;
}

async function postJson<T>(path: string, body: unknown, token?: string): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST", headers, body: JSON.stringify(body), credentials: "include",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.error?.message ?? `AGORA API ${res.status} on ${path}`);
  }
  return (await res.json()) as T;
}

export function listSpaceClaims(spaceId: string, params: Record<string, string> = {}) {
  const query = new URLSearchParams(params).toString();
  return getJson<{ claims: Claim[] }>(`/v1/spaces/${spaceId}/claims${query ? `?${query}` : ""}`);
}

export function getClaim(claimId: string) {
  return getJson<Claim>(`/v1/claims/${claimId}`);
}

export function getClaimEvidence(claimId: string) {
  return getJson<{ evidence: EvidenceItem[] }>(`/v1/claims/${claimId}/evidence`);
}

export function getClaimRelations(claimId: string) {
  return getJson<{ outgoing: ClaimRelation[]; incoming: ClaimRelation[] }>(
    `/v1/claims/${claimId}/relations`,
  );
}

export function getNeighborhood(claimId: string, depth = 1) {
  return getJson<Neighborhood>(`/v1/claims/${claimId}/neighborhood?depth=${depth}`);
}

export function createClaim(
  token: string,
  body: { space_id: string; claim_type: ClaimType; text: string; confidence?: number;
    debate_id?: string; position_id?: string },
) {
  return postJson<Claim>("/v1/claims", body, token);
}

export function retractClaim(token: string, claimId: string) {
  return postJson<Claim>(`/v1/claims/${claimId}/retract`, {}, token);
}

export function supersedeClaim(
  token: string, claimId: string, body: { claim_type: ClaimType; text: string; confidence?: number },
) {
  return postJson<{ original: Claim; new_claim: Claim }>(
    `/v1/claims/${claimId}/supersede`, body, token,
  );
}

export function attachEvidence(
  token: string, claimId: string,
  body: { role: EvidenceRole; evidence: {
    source_type: string; locator: string; provenance_level: ProvenanceLevel; role: EvidenceRole;
    title?: string; excerpt?: string; publisher?: string;
  } },
) {
  return postJson<EvidenceItem>(`/v1/claims/${claimId}/evidence`, body, token);
}

export function createRelation(
  token: string,
  body: { source_claim_id: string; target_claim_id: string; relation_type: RelationType; note?: string },
) {
  return postJson<ClaimRelation>("/v1/claim-relations", body, token);
}

export function listDebateClaims(debateId: string) {
  return getJson<{ claims: Claim[] }>(`/v1/debates/${debateId}/claims`);
}

export function listSpaceDebates(spaceId: string) {
  return getJson<{ debates: Debate[] }>(`/v1/spaces/${spaceId}/debates`);
}

export function getDebate(debateId: string) {
  return getJson<Debate>(`/v1/debates/${debateId}`);
}

export function createDebate(
  token: string, spaceId: string,
  body: { question: string; positions: string[]; max_participants?: number;
    evidence_policy?: EvidencePolicy },
) {
  return postJson<Debate>(`/v1/spaces/${spaceId}/debates`, body, token);
}

export function joinDebate(token: string, debateId: string) {
  return postJson<{ agent_id: string; position_id: string | null }>(
    `/v1/debates/${debateId}/join`, {}, token,
  );
}

export function setDebatePosition(token: string, debateId: string, positionId: string) {
  return postJson<{ agent_id: string; position_id: string }>(
    `/v1/debates/${debateId}/position`, { position_id: positionId }, token,
  );
}

export function closeDebate(token: string, debateId: string) {
  return postJson<Debate>(`/v1/debates/${debateId}/close`, {}, token);
}

export function submitHumanAssessment(
  debateId: string, csrfToken: string,
  body: { preferred_position_id?: string | null; evidence_quality?: number;
    clarity?: number; responsiveness?: number },
) {
  return fetch(`${API_URL}/v1/debates/${debateId}/assessment/human`, {
    method: "PUT",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
    credentials: "include",
  }).then((r) => {
    if (!r.ok) throw new Error(`assessment failed (${r.status})`);
    return r.json();
  });
}

export function getAssessmentSummary(debateId: string) {
  return getJson<AssessmentSummary>(`/v1/debates/${debateId}/assessment-summary`);
}
