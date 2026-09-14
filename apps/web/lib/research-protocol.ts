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
        owner_gate: {
          required: true;
          state: string;
          proposal_hash: string | null;
          proposal_version: number | null;
          proposal_details_public: false;
        };
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
    `/v1/research-protocol/challenges/${encodeURIComponent(challengeId)}`,
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

export interface PilotReviewProposal {
  proposal_id: string;
  proposal_version: number;
  proposal_hash: string;
  state: string;
  assignment_id: string;
  assignment_state: string;
  candidate_id: string;
  validator: {
    validator_id: string;
    actor_id: string;
    display_name: string;
    institution_name: string;
    brain_provider: "codex" | "claude" | "python-scripted-test";
    review_role: "REPRODUCTION_METHODOLOGY" | "FALSIFICATION_EVIDENCE";
    badge: "TEST INSTITUTIONAL VALIDATOR";
    disclaimer: string;
  };
  review: {
    verdict: string;
    confidence: number;
    reproduction_status: string;
    dimensions: Record<string, number>;
    summary: string;
    methodology_findings: string;
    reproduction_findings: string;
    evidence_findings: string;
    critical_issues: string[];
    minor_issues: string[];
    requested_changes: string[];
    executed_tests: string[];
    artifacts_reviewed: string[];
  };
  recommendation: {
    assessment: "PASS" | "PASS_WITH_CONDITIONS" | "FAIL" | "INSUFFICIENT_EVIDENCE";
    rationale: string;
    blocking_issues: string[];
    what_is_missing: string[];
    suggested_actions: string[];
  };
  evidence_manifest: {
    context_hash: string;
    participant_ids: string[];
    thread_entry_ids: string[];
    event_ids: string[];
    artifact_ids: string[];
    test_receipt_hashes: string[];
  };
  tokoin_recommendation: {
    denomination: "ACEROS";
    total_aceros: number;
    allocations: Array<{
      recipient_kind: string;
      recipient_id: string;
      amount_aceros: number;
      basis: string;
    }>;
    synthetic_test_only: true;
    settlement_eligible: false;
    requires_separate_human_validation: true;
  };
  decision: null | {
    decision_id: string;
    decision: "APPROVE" | "REQUEST_REVISION" | "REJECT";
    proposal_hash: string;
    owner_notes: string;
    decision_hash: string;
    created_at: string;
  };
  approved_for_commit: boolean;
  synthetic_test_only: true;
  human_validation_satisfied: false;
  tokoin_settlement_eligible: false;
  disclaimer: string;
  created_at: string;
}

export interface PilotOwnerQueue {
  challenge_id: string;
  owner_id: string;
  pending_agent_analysis: number;
  proposals: PilotReviewProposal[];
  synthetic_test_only: true;
  human_validation_satisfied: false;
  tokoin_settlement_eligible: false;
}

export interface PilotValidatorRegistry {
  layer: "Institutional Validation Layer";
  synthetic_test_only: true;
  validators: Array<{
    validator_id: string;
    actor_id: string;
    display_name: string;
    institution_name: string;
    brain_provider: "codex" | "claude" | "python-scripted-test";
    review_role: "REPRODUCTION_METHODOLOGY" | "FALSIFICATION_EVIDENCE";
    active_status: boolean;
    badge: "TEST INSTITUTIONAL VALIDATOR";
    disclaimer: string;
  }>;
}

export function getPilotValidatorRegistry(): Promise<PilotValidatorRegistry> {
  return getJson("/v1/research-protocol/institutional-validators");
}

export function assignPilotValidatorPanel(
  candidateId: string,
  csrfToken: string,
  validatorIds: string[],
): Promise<unknown> {
  return researchMutation(
    `/v1/research-protocol/candidates/${encodeURIComponent(candidateId)}/pilot-panel`,
    csrfToken,
    { validator_ids: validatorIds },
  );
}

export function getOwnerPilotReviewProposals(challengeId: string): Promise<PilotOwnerQueue> {
  return getJson(
    `/v1/research-protocol/challenges/${encodeURIComponent(challengeId)}` +
      "/pilot-review-proposals/me",
  );
}

export function decidePilotReviewProposal(
  proposalId: string,
  csrfToken: string,
  body: {
    decision: "APPROVE" | "REQUEST_REVISION" | "REJECT";
    proposal_hash: string;
    owner_notes: string;
  },
): Promise<{
  decision_id: string;
  decision: string;
  proposal_hash: string;
  decision_hash: string;
  synthetic_test_only: true;
  tokoin_released: false;
}> {
  return researchMutation(
    `/v1/research-protocol/pilot-review-proposals/${encodeURIComponent(proposalId)}/decision`,
    csrfToken,
    body,
  );
}
