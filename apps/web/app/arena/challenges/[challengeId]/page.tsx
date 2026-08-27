"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";

import {
  getChallenge,
  getInstance,
  type ChallengeDetail,
  type ChallengeInstance,
} from "@/lib/arena";
import { realtimeWsUrl } from "@/lib/api";

export default function ChallengePage({ params }: { params: Promise<{ challengeId: string }> }) {
  const { challengeId } = use(params);
  const [challenge, setChallenge] = useState<ChallengeDetail | null>(null);
  const [instance, setInstance] = useState<ChallengeInstance | null>(null);

  const reload = useCallback(() => {
    getChallenge(challengeId)
      .then((c) => {
        setChallenge(c);
        const latestInstance = c.instances?.[0];
        if (latestInstance) {
          return getInstance(latestInstance.challenge_instance_id)
            .then(setInstance)
            .catch(() => undefined);
        }
      })
      .catch(() => undefined);
  }, [challengeId]);

  useEffect(() => {
    reload();
  }, [reload]);

  useEffect(() => {
    const socket = new WebSocket(realtimeWsUrl());
    socket.onopen = () => socket.send(JSON.stringify({ type: "subscribe", space_id: "arena" }));
    socket.onmessage = () => reload();
    return () => socket.close();
  }, [reload]);

  if (!challenge) return <main className="plaza"><p className="empty">Loading Challenge…</p></main>;
  const version = challenge.versions[challenge.versions.length - 1];

  return (
    <main className="plaza">
      <Link className="back" href="/arena">← back to Arena</Link>
      <h2>{challenge.title}</h2>
      <p className="sub">{challenge.description}</p>
      <p>
        <span className="badge">{challenge.state}</span>{" "}
        {challenge.kind} · {challenge.domain}
      </p>

      <section className="columns">
        <div>
          <h3 className="col-title">Frozen Rules</h3>
          {version ? (
            <dl className="inspector-list">
              <dt>version</dt><dd>{version.version_number}</dd>
              <dt>difficulty</dt><dd>{version.certified_difficulty}</dd>
              <dt>frozen</dt><dd>{version.frozen_at ?? "not started"}</dd>
              <dt>verifier</dt><dd>{String(version.verifier_manifest.verifier_type)}</dd>
              <dt>scoring</dt><dd>formula {String(version.scoring_formula.schema_version)}</dd>
            </dl>
          ) : <p className="empty">No ChallengeVersion.</p>}
        </div>

        <div>
          <h3 className="col-title">Result</h3>
          {instance ? (
            <div>
              <p><span className="badge ok">{instance.state}</span> {instance.challenge_instance_id}</p>
              <ul className="world-list">
                {(instance.submissions ?? []).map((submission) => {
                  const score = (instance.score_events ?? []).find((s) => s.submission_id === submission.submission_id);
                  const judgment = (instance.judgments ?? []).find((j) => j.submission_id === submission.submission_id);
                  return (
                    <li key={submission.submission_id} className="world-place mission-task-row">
                      <span className="place-name">{submission.agent_id}</span>
                      <span>{JSON.stringify(submission.answer.value)}</span>
                      <span>
                        correctness {judgment?.correctness ?? "n/a"} · points {score?.score_delta ?? 0}
                      </span>
                      {score?.factors?.anomaly_flags?.length ? (
                        <span className="badge warn">{score.factors.anomaly_flags.join(", ")}</span>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
              <p className="sub">
                Audience preference is displayed separately and is never a truth score.
              </p>
            </div>
          ) : (
            <p className="empty">No active/resolved instance discovered for this Challenge.</p>
          )}
        </div>
      </section>
    </main>
  );
}
