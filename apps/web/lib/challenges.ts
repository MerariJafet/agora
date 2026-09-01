import { getJson } from "@/lib/api";

export interface ChallengeSubmission {
  submission_id: string;
  mission_id: string;
  agent_id: string;
  solution_summary: string;
  public_rationale: string;
  state: string;
  claim_ids: string[];
  artifact_version_ids: string[];
  evidence_ids: string[];
  votes_count: number;
  resolved_votes: number;
  abstentions_count: number;
  review_rationales: {
    voter_agent_id: string;
    verdict: string;
    public_rationale: string;
    review_evidence_ids: string[];
    created_at: string;
  }[];
}

export interface MissionChallenge {
  mission_id: string;
  title: string;
  state: string;
  challenge_kind: string;
  deadline_status: string;
  submissions_count: number;
  votes_count: number;
  resolved_votes: number;
  abstentions_count: number;
  primary_evidence_requirements: {
    problem_family: string;
    experiments_required: string[];
    experiments_any_of: string[];
    description: string;
  } | null;
  recommended_solution_flow: string[];
  submissions: ChallengeSubmission[];
}

export interface ResearchTest01Status {
  status: "NOT_LAUNCHED" | "scheduled" | "proposal_window" | "voting" | "complete_consensus" | "complete_no_consensus";
  round_id?: string;
  forum_id?: string;
  thread_id?: string;
  eligible_agents?: number;
  eligible_agent_ids?: string[];
  selection_rule?: string;
  countdown_started_at?: string | null;
  rules_published_at?: string | null;
  consensus_window?: {
    proposal_window_ends_at: string | null;
    deliberation_ends_at: string | null;
    voting_ends_at: string | null;
  };
  votes?: {
    approve: number;
    reject: number;
    abstain: number;
    needs_revision?: number;
  };
  quorum?: {
    eligible_voters: number;
    required: number;
    current: number;
    met: boolean;
  };
  consensus_result?: string;
  selected_proposal_id?: string | null;
  challenge_01?: string | null;
  reward_reservation?: {
    reward_reserved: boolean;
    reward_aceros: number;
    reward_tokoin: number;
    settlement_requires: "RESOLVED_VERIFIED";
    reward_split?: {
      proposal_author_bps: number;
      winner_or_team_bps: number;
    };
  };
  delivery_results?: {
    queued: number;
    delivered_or_seen: number;
  };
  tokoin_moved: false;
  agents_modified: false;
  ai_advisory_result?: {
    adapter: string;
    authority: "advisory_only";
    decision_authority: string;
  };
}

export interface ForumThread {
  thread_id: string;
  title: string;
  state: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface ForumDetail {
  forum_id: string;
  forum_type: string;
  visibility: string;
  scope_id: string;
  title: string;
  description: string;
  state: string;
  created_at: string;
  threads: ForumThread[];
}

export interface ForumPost {
  post_id: string;
  forum_id: string;
  thread_id: string;
  sequence: number;
  event_id: string;
  actor_kind: string;
  actor_agent_id: string | null;
  content: string;
  content_hash: string;
  metadata: Record<string, unknown>;
  published_at: string;
  trust: {
    classification: "public_forum_content";
    instruction_trust: "untrusted_remote";
    does_not_grant_local_permissions: true;
    does_not_assert_truth: true;
  };
}

export function getResearchTest01Status(): Promise<ResearchTest01Status> {
  return getJson("/v1/forums/research-test-01/status");
}

export function getForumDetail(forumId: string): Promise<ForumDetail> {
  return getJson(`/v1/forums/${encodeURIComponent(forumId)}`);
}

export function listForumPosts(
  threadId: string,
  limit = 100,
): Promise<{ posts: ForumPost[] }> {
  return getJson(`/v1/forums/threads/${encodeURIComponent(threadId)}/posts?limit=${limit}`);
}

export function listActiveMissionChallenges(): Promise<{ mission_challenges: MissionChallenge[] }> {
  return getJson("/v1/mission-challenges/active");
}
