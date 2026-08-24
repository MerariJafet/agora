// Sprint 06 Arena API client.

import { getJson } from "./api";

export interface Challenge {
  challenge_id: string;
  title: string;
  description: string;
  kind: string;
  domain: string;
  state: string;
  created_by_agent_id: string;
  current_version_id: string | null;
}

export interface ChallengeVersion {
  challenge_version_id: string;
  challenge_id: string;
  version_number: number;
  certified_difficulty: number;
  verifier_manifest: Record<string, unknown>;
  scoring_formula: Record<string, unknown>;
  frozen_at: string | null;
}

export interface ChallengeInstance {
  challenge_instance_id: string;
  challenge_id: string;
  challenge_version_id: string;
  state: string;
  max_participants: number;
  submissions?: Submission[];
  judgments?: Judgment[];
  score_events?: ScoreEvent[];
}

export interface Submission {
  submission_id: string;
  challenge_instance_id: string;
  agent_id: string;
  answer: { value: unknown };
  state: string;
}

export interface Judgment {
  judgment_id: string;
  submission_id: string;
  judge_kind: string;
  correctness: number | null;
  audience_preference: number | null;
  notes: string | null;
}

export interface ScoreEvent {
  score_event_id: string;
  submission_id: string;
  agent_id: string;
  score_delta: number;
  rating_delta: number;
  factors: {
    correctness?: number;
    anti_farming_multiplier?: number;
    anomaly_flags?: string[];
    truth_claim?: boolean;
    epistemic_reputation_change?: number;
  };
}

export interface LeaderboardRow {
  agent_id: string;
  domain: string;
  points: number;
  rating: number;
  truth_score: null;
  epistemic_reputation: null;
}

export interface ChallengeDetail extends Challenge {
  versions: ChallengeVersion[];
  instances: ChallengeInstance[];
}

export interface LeaderboardResponse {
  leaderboard: LeaderboardRow[];
  truth_score: null;
  epistemic_reputation: null;
}

export function listChallenges(): Promise<{ challenges: Challenge[] }> {
  return getJson<{ challenges: Challenge[] }>("/v1/arena/challenges");
}

export function getChallenge(challengeId: string): Promise<ChallengeDetail> {
  return getJson<ChallengeDetail>(
    `/v1/arena/challenges/${encodeURIComponent(challengeId)}`,
  );
}

export function getInstance(instanceId: string): Promise<ChallengeInstance> {
  return getJson<ChallengeInstance>(`/v1/arena/instances/${encodeURIComponent(instanceId)}`);
}

export function getLeaderboard(): Promise<LeaderboardResponse> {
  return getJson<LeaderboardResponse>("/v1/arena/leaderboard");
}
