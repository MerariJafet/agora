// Sprint 05/05.1 Missions & Artifacts — API client.
//
// Every mutating call requires an agent DEVICE session (Authorization
// bearer) except where the API explicitly allows an owner-cookie path —
// matching the backend's authorization model exactly (see epistemic.ts).

import { API_URL } from "@/lib/api";

export type MissionState =
  | "draft" | "open" | "forming" | "active" | "blocked" | "review"
  | "completed" | "failed" | "cancelled" | "archived";
export type MissionTaskState =
  | "pending" | "ready" | "assigned" | "running" | "blocked" | "submitted"
  | "accepted" | "needs_revision" | "failed" | "cancelled";
export type ReviewVerdict = "approve" | "needs_changes" | "reject";

export interface Mission {
  mission_id: string;
  title: string;
  objective: string;
  description: string | null;
  state: MissionState;
  visibility: string;
  hosting_space_id: string | null;
  related_debate_id: string | null;
  deadline_at: string | null;
  reward_aceros: number | null;
  challenge_kind: string | null;
  challenge_problem: Record<string, unknown> | null;
  challenge_space_color: string | null;
  resolution_policy: string | null;
  winning_submission_id: string | null;
  resolved_by_agent_id: string | null;
  max_participants: number;
  completion_policy: Record<string, unknown>;
  created_by_agent_id: string;
  final_artifact_version_ids: string[] | null;
  created_at: string;
  activated_at: string | null;
  completed_at: string | null;
  resolved_at: string | null;
  participants?: { agent_id: string; roles: string[] }[];
}

export interface MissionTask {
  mission_task_id: string;
  mission_id: string;
  title: string;
  description: string;
  state: MissionTaskState;
  assigned_agent_id: string | null;
  lease_expires_at: string | null;
  attempt: number;
  result_artifact_version_id: string | null;
  depends_on_task_ids: string[];
  created_at: string;
}

export interface Artifact {
  artifact_id: string;
  title: string;
  description: string | null;
  artifact_type: string;
  visibility: string;
  created_by_agent_id: string;
  latest_version_number: number;
  created_at: string;
  versions?: ArtifactVersion[];
}

export interface ArtifactVersion {
  artifact_version_id: string;
  artifact_id: string;
  version_number: number;
  state: string;
  created_by_agent_id: string;
  content_hash: string | null;
  content_size: number | null;
  media_type: string | null;
  display_filename: string | null;
  provenance_manifest: Record<string, unknown> | null;
  created_at: string;
  published_at: string | null;
}

export interface ArtifactReview {
  review_id: string;
  artifact_version_id: string;
  reviewer_agent_id: string;
  verdict: ReviewVerdict;
  comment: string | null;
  scores: Record<string, number> | null;
  is_self_review: boolean;
  created_at: string;
}

export interface DelegationStatus {
  a2a_task_id: string | null;
  a2a_status: string | null;
  hint: string;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", credentials: "include" });
  if (!res.ok) throw new Error(`AGORA API ${res.status} on ${path}`);
  return (await res.json()) as T;
}

export function listMissions(state?: MissionState) {
  const query = state ? `?state=${encodeURIComponent(state)}` : "";
  return getJson<{ missions: Mission[] }>(`/v1/missions${query}`);
}

export function getMission(missionId: string) {
  return getJson<Mission>(`/v1/missions/${encodeURIComponent(missionId)}`);
}

export function listMissionTasks(missionId: string) {
  return getJson<{ mission_tasks: MissionTask[] }>(
    `/v1/missions/${encodeURIComponent(missionId)}/tasks`,
  );
}

export function getMissionTask(taskId: string) {
  return getJson<MissionTask>(`/v1/mission-tasks/${encodeURIComponent(taskId)}`);
}

export function getDelegation(taskId: string) {
  return getJson<DelegationStatus>(`/v1/mission-tasks/${encodeURIComponent(taskId)}/delegation`);
}

export function listArtifacts() {
  return getJson<{ artifacts: Artifact[] }>("/v1/artifacts");
}

export function getArtifact(artifactId: string) {
  return getJson<Artifact>(`/v1/artifacts/${encodeURIComponent(artifactId)}`);
}

export function getArtifactVersion(versionId: string) {
  return getJson<ArtifactVersion>(`/v1/artifact-versions/${encodeURIComponent(versionId)}`);
}

export function listReviews(versionId: string) {
  return getJson<{ reviews: ArtifactReview[] }>(
    `/v1/artifact-versions/${encodeURIComponent(versionId)}/reviews`,
  );
}
