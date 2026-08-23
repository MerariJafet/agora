"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import {
  type ArtifactVersion,
  type ArtifactReview,
  type DelegationStatus,
  type Mission,
  type MissionTask,
  getArtifactVersion,
  getDelegation,
  getMission,
  listMissionTasks,
  listReviews,
} from "@/lib/missions";
import { worldSocket } from "@/world/client";

// Task state -> a short, always-visible text label. Never rely on color
// alone (S5.1-T08): every badge below carries this same text regardless of
// theme/contrast settings.
const TASK_STATE_LABEL: Record<string, string> = {
  pending: "pending (blocked on a dependency)",
  ready: "ready to claim",
  assigned: "assigned (leased)",
  running: "running",
  blocked: "blocked",
  submitted: "submitted, awaiting review",
  accepted: "accepted",
  needs_revision: "needs revision",
  failed: "failed",
  cancelled: "cancelled",
};

function taskBadgeClass(state: string): string {
  if (state === "accepted") return "ok";
  if (state === "failed" || state === "cancelled" || state === "needs_revision") return "revoked";
  return "";
}

function TaskResult({ task }: { task: MissionTask }) {
  const [version, setVersion] = useState<ArtifactVersion | null>(null);
  const [reviews, setReviews] = useState<ArtifactReview[]>([]);
  const [delegation, setDelegation] = useState<DelegationStatus | null>(null);

  useEffect(() => {
    if (task.result_artifact_version_id) {
      getArtifactVersion(task.result_artifact_version_id).then(setVersion).catch(() => undefined);
      listReviews(task.result_artifact_version_id).then((r) => setReviews(r.reviews)).catch(() => undefined);
    }
    getDelegation(task.mission_task_id).then(setDelegation).catch(() => setDelegation(null));
  }, [task.mission_task_id, task.result_artifact_version_id]);

  return (
    <div className="mission-task-detail">
      {delegation?.a2a_task_id && (
        <p className="sub">
          Delegated over A2A · exchange status: <strong>{delegation.a2a_status}</strong>
          {" "}({delegation.hint.replaceAll("_", " ")})
        </p>
      )}
      {version ? (
        <div className="assessment-card">
          <h4>
            <Link href={`/missions/artifact-versions/${version.artifact_version_id}`}>
              {version.display_filename ?? version.artifact_version_id} · v{version.version_number}
            </Link>
          </h4>
          <p className="sub">
            {version.content_size ?? 0} bytes · {version.media_type ?? "unknown type"} ·{" "}
            hash {version.content_hash?.slice(0, 12)}…
          </p>
          <ul className="world-list">
            {reviews.map((r) => (
              <li key={r.review_id} className="world-place">
                <span className="place-name">
                  {r.reviewer_agent_id} — {r.verdict}
                  {r.is_self_review ? " (self-review)" : ""}
                </span>
                {r.comment && <span className="place-state">{r.comment}</span>}
              </li>
            ))}
            {reviews.length === 0 && <li className="empty">No reviews yet.</li>}
          </ul>
        </div>
      ) : (
        <p className="sub">No result submitted yet.</p>
      )}
    </div>
  );
}

function TaskRow({
  task, allTasks, expanded, onToggle,
}: {
  task: MissionTask; allTasks: MissionTask[]; expanded: boolean; onToggle: () => void;
}) {
  const dependencyTitles = task.depends_on_task_ids.map(
    (id) => allTasks.find((t) => t.mission_task_id === id)?.title ?? id,
  );
  return (
    <li className="world-place mission-task-row">
      <button
        type="button"
        className="mission-task-toggle"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        <span className="place-name">{task.title}</span>
        <span className={`badge ${taskBadgeClass(task.state)}`}>
          {TASK_STATE_LABEL[task.state] ?? task.state}
        </span>
      </button>
      <p className="sub">
        {task.assigned_agent_id ? `assigned to ${task.assigned_agent_id}` : "unassigned"}
        {dependencyTitles.length > 0 && <> · depends on: {dependencyTitles.join(", ")}</>}
        {task.attempt > 0 && <> · attempt {task.attempt}</>}
      </p>
      {expanded && (
        <TaskResult
          key={`${task.mission_task_id}:${task.result_artifact_version_id ?? "none"}`}
          task={task}
        />
      )}
    </li>
  );
}

export default function MissionDetailPage({
  params,
}: {
  params: Promise<{ missionId: string }>;
}) {
  const { missionId } = use(params);
  const [mission, setMission] = useState<Mission | null>(null);
  const [tasks, setTasks] = useState<MissionTask[]>([]);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);
  const [live, setLive] = useState(false);

  const reload = useCallback(() => {
    getMission(missionId).then(setMission).catch(() => undefined);
    listMissionTasks(missionId).then((r) => setTasks(r.mission_tasks)).catch(() => undefined);
  }, [missionId]);

  useEffect(reload, [reload]);

  // Realtime: subscribe to this Mission's own scope (S5.1-T06/T07) — the
  // same additive WS subscribe mechanism already used for Spaces, just with
  // a mission_id instead of a space_id. No polling once connected.
  useEffect(() => {
    const socket = worldSocket();
    socket.onopen = () => {
      setLive(true);
      socket.send(JSON.stringify({ type: "subscribe", space_id: missionId }));
    };
    socket.onclose = () => setLive(false);
    socket.onerror = () => setLive(false);
    socket.onmessage = () => reload(); // every Mission/Artifact event here is semantic, never noise
    return () => socket.close();
  }, [missionId, reload]);

  if (!mission) return <main className="plaza"><p className="empty">Loading Mission…</p></main>;

  const policyEntries = Object.entries(mission.completion_policy ?? {});

  return (
    <main className="plaza">
      <Link className="back" href="/missions">← back to Missions</Link>
      <h2>{mission.title}</h2>
      <p className="sub">
        <span className={`badge ${mission.state === "completed" ? "ok" : ""}`}>{mission.state}</span>
        {" "}
        <span className={`badge ${live ? "ok" : "revoked"}`}>{live ? "live" : "reconnecting"}</span>
        {" "}· created by {mission.created_by_agent_id}
      </p>
      <p className="sub">{mission.objective}</p>
      {mission.description && <p className="sub">{mission.description}</p>}

      <h3 className="col-title">Participants</h3>
      <ul className="world-list">
        {(mission.participants ?? []).map((p) => (
          <li key={p.agent_id} className="world-place">
            <span className="place-name">{p.agent_id}</span>
            <span className="place-state">{p.roles.join(", ") || "no role declared"}</span>
          </li>
        ))}
        {(mission.participants ?? []).length === 0 && (
          <li className="empty">No participants yet.</li>
        )}
      </ul>

      <h3 className="col-title">Task graph</h3>
      <p className="sub">
        Listed in an accessible, non-graph form: each task&apos;s dependencies are
        named explicitly rather than drawn as edges.
      </p>
      <ul className="world-list">
        {tasks.map((t) => (
          <TaskRow
            key={t.mission_task_id}
            task={t}
            allTasks={tasks}
            expanded={expandedTask === t.mission_task_id}
            onToggle={() =>
              setExpandedTask(expandedTask === t.mission_task_id ? null : t.mission_task_id)
            }
          />
        ))}
        {tasks.length === 0 && <li className="empty">No tasks yet.</li>}
      </ul>

      <h3 className="col-title">Completion policy</h3>
      {policyEntries.length > 0 ? (
        <dl className="inspector">
          {policyEntries.map(([k, v]) => (
            <div key={k} style={{ display: "contents" }}>
              <dt>{k.replaceAll("_", " ")}</dt>
              <dd>{String(v)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="sub">Default policy (all required tasks accepted, at least one final Artifact).</p>
      )}

      <h3 className="col-title">Final Artifacts</h3>
      {mission.final_artifact_version_ids && mission.final_artifact_version_ids.length > 0 ? (
        <ul className="world-list">
          {mission.final_artifact_version_ids.map((id) => (
            <li key={id} className="world-place">
              <Link className="place-name" href={`/missions/artifact-versions/${id}`}>{id}</Link>
              <span className="place-state">pinned exact version</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">
          {mission.state === "completed"
            ? "Completed with no final artifacts recorded."
            : "Not completed yet — no final Artifact is pinned."}
        </p>
      )}
    </main>
  );
}
