import { API_URL, getJson } from "@/lib/api";

export interface ResearchProtocolView {
  protocol_version: string;
  challenge: {
    challenge_id: string;
    title: string;
    objective: string;
    state: string;
    consensus_is_truth: false;
  };
  genealogy: {
    root_hash: string;
    nodes: Array<{
      node_id: string;
      node_type: string;
      author_actor_id: string;
      content_hash: string;
      status: string;
      created_at: string;
      summary: Record<string, unknown>;
    }>;
    edges: Array<{
      edge_id: string;
      source: string;
      target: string;
      relation: string;
    }>;
  };
  candidates: Array<{
    candidate_id: string;
    candidate_version: number;
    state: string;
    content_hash: string;
    knowledge_root_hash: string;
    created_at: string;
  }>;
  institutional_reviews: Array<{
    review_id: string;
    candidate_id: string;
    institution_id: string;
    verdict: string;
    content_hash: string;
    created_at: string;
  }>;
  institutional_validator_layer?: {
    actor_type: "INSTITUTIONAL_VALIDATOR";
    pilot_is_synthetic: true;
    pilot_can_satisfy_human_validation: false;
    pilot_can_release_tokoin: false;
    panels: Array<{
      candidate_id: string;
      candidate_state: string;
      blind_review: true;
      minimum_validators: 2;
      all_committed: boolean;
      all_revealed: boolean;
      status: string;
      synthetic_test_only: true;
      human_validation_satisfied: false;
      tokoin_settlement_eligible: false;
      pilot_credit_per_completed_review_aceros: number;
      pilot_credit_is_non_settleable: true;
      tracks: Array<{
        assignment_id: string;
        candidate_id: string;
        state: string;
        committed: boolean;
        commitment_hash: string | null;
        revealed: boolean;
        validator: {
          validator_id: string;
          actor_id: string;
          display_name: string;
          institution_name: string;
          brain_provider: "codex" | "claude";
          review_role: "REPRODUCTION_METHODOLOGY" | "FALSIFICATION_EVIDENCE";
          scientific_domains: string[];
          badge: "TEST INSTITUTIONAL VALIDATOR";
          disclaimer: string;
          reputation_score: number;
          active_status: boolean;
          can_satisfy_human_validation: false;
          can_release_tokoin: false;
        };
        review?: {
          review_id: string;
          verdict: string;
          confidence: number;
          reproduction_status: string;
          summary: string;
          review_hash: string;
          synthetic_test_review: true;
        };
      }>;
    }>;
  };
  rewards: Array<{
    reward_id: string;
    candidate_id: string;
    state: string;
    total_aceros: number;
    algorithm_version: string;
    content_hash: string;
    allocation: {
      pools: Record<string, number>;
    };
  }>;
  publication_packages: Array<{
    package_id: string;
    candidate_id: string;
    state: string;
    package_hash: string;
    responsible_institution_ids: string[];
  }>;
}

export function getResearchProtocol(challengeId: string): Promise<ResearchProtocolView> {
  return getJson<ResearchProtocolView>(
    `/agora-api/v1/research-protocol/challenges/${encodeURIComponent(challengeId)}`,
  );
}

export interface ResearchInstitutionView {
  institution_id: string;
  legal_entity_id: string;
  name: string;
  domain: string;
  jurisdiction: string;
  state: string;
  credential_hash: string;
  payout_address_configured: boolean;
}

export interface InstitutionalReviewDraft {
  institution_id: string;
  verdict: "APPROVED" | "APPROVED_WITH_MINOR_CHANGES" | "REQUIRES_REVISION" | "REJECTED" | "INSUFFICIENT_EVIDENCE";
  methodology_review: string;
  evidence_review: string;
  paper_review: string;
  experiment_review: string;
  conflict_declaration: string;
}

async function researchMutation<T>(path: string, csrfToken: string, body: object): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`AGORA API ${response.status} on ${path}`);
  return (await response.json()) as T;
}

export function getMyResearchInstitution(): Promise<{ institution: ResearchInstitutionView | null }> {
  return getJson("/v1/research-protocol/institutions/me");
}

export function prepareInstitutionalReview(
  candidateId: string,
  csrfToken: string,
  body: InstitutionalReviewDraft,
): Promise<{ signed_payload_hash: string; signing_payload: object; instruction: string }> {
  return researchMutation(
    `/v1/research-protocol/candidates/${encodeURIComponent(candidateId)}/review-signing-payload`,
    csrfToken,
    body,
  );
}

export function submitInstitutionalReview(
  candidateId: string,
  csrfToken: string,
  body: InstitutionalReviewDraft & { signature: string },
): Promise<{ review_id: string; verdict: string; content_hash: string }> {
  return researchMutation(
    `/v1/research-protocol/candidates/${encodeURIComponent(candidateId)}/reviews`,
    csrfToken,
    body,
  );
}
