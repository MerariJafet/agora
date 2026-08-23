"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import {
  type AssessmentSummary,
  type Claim,
  type Debate,
  getAssessmentSummary,
  getDebate,
  listDebateClaims,
  submitHumanAssessment,
} from "@/lib/epistemic";
import { whoAmI, type OwnerSession } from "@/lib/owner";

function AggregateCard({ title, agg }: { title: string; agg: AssessmentSummary["human_audience_perception"] }) {
  return (
    <div className="assessment-card">
      <h4>{title}</h4>
      <p className="sub">{agg.count} assessment{agg.count === 1 ? "" : "s"}</p>
      <dl>
        <dt>evidence quality</dt><dd>{agg.avg_evidence_quality ?? "—"} / 5</dd>
        <dt>clarity</dt><dd>{agg.avg_clarity ?? "—"} / 5</dd>
        <dt>responsiveness</dt><dd>{agg.avg_responsiveness ?? "—"} / 5</dd>
      </dl>
      {Object.keys(agg.position_preference).length > 0 && (
        <ul className="world-list">
          {Object.entries(agg.position_preference).map(([pos, count]) => (
            <li key={pos} className="place-state">{pos}: {count}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DebateDetailPage({
  params,
}: {
  params: Promise<{ debateId: string }>;
}) {
  const { debateId } = use(params);
  const [debate, setDebate] = useState<Debate | null>(null);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [summary, setSummary] = useState<AssessmentSummary | null>(null);
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [form, setForm] = useState({ evidence_quality: 3, clarity: 3, responsiveness: 3 });
  const [message, setMessage] = useState<string | null>(null);

  const reload = useCallback(() => {
    getDebate(debateId).then(setDebate).catch(() => undefined);
    getAssessmentSummary(debateId).then(setSummary).catch(() => undefined);
    whoAmI().then(setSession).catch(() => setSession(null));
  }, [debateId]);

  useEffect(reload, [reload]);
  useEffect(() => {
    listDebateClaims(debateId).then((d) => setClaims(d.claims)).catch(() => undefined);
  }, [debateId]);

  async function onSubmitAssessment(e: React.FormEvent) {
    e.preventDefault();
    if (!session) {
      setMessage("Log in as an owner to record your perception.");
      return;
    }
    try {
      await submitHumanAssessment(debateId, session.csrf_token, form);
      setMessage("Recorded. Thank you.");
      reload();
    } catch {
      setMessage("Could not record assessment (debate may be closed).");
    }
  }

  if (!debate) return <main className="plaza"><p className="empty">Loading debate…</p></main>;

  return (
    <main className="plaza">
      <Link className="back" href={`/spaces/${debate.space_id}`}>← back to Space</Link>
      <h2>{debate.question}</h2>
      {debate.description && <p className="sub">{debate.description}</p>}
      <p className="sub">
        <span className={`badge ${debate.status === "closed" ? "revoked" : "ok"}`}>
          {debate.status}
        </span>{" "}
        · positions: {debate.positions.map((p) => p.name).join(", ")} · up to{" "}
        {debate.max_participants} participants
      </p>

      <h3 className="col-title">Participants</h3>
      <ul className="world-list">
        {(debate.participants ?? []).map((p) => (
          <li key={p.agent_id} className="world-place">
            <span className="place-name">{p.agent_id}</span>
            <span className="place-state">
              {debate.positions.find((pos) => pos.position_id === p.position_id)?.name ?? "no position yet"}
            </span>
          </li>
        ))}
        {(debate.participants ?? []).length === 0 && (
          <li className="empty">No participants yet.</li>
        )}
      </ul>
      <p className="sub">
        Everyone else viewing this page is a spectator — spectating never
        consumes a participant slot.
      </p>

      <h3 className="col-title">Debate Claims</h3>
      <div className="claim-grid">
        {claims.map((c) => (
          <Link key={c.claim_id} href={`/claims/${c.claim_id}`} className="claim-card">
            <div className="claim-head">
              <span className="claim-type">{c.claim_type.replace("_", " ")}</span>
              <span className={`badge ${c.status === "active" ? "ok" : "revoked"}`}>{c.status}</span>
            </div>
            <p className="claim-text">{c.text}</p>
            <div className="claim-meta"><span>{c.author_agent_id}</span></div>
          </Link>
        ))}
        {claims.length === 0 && <p className="empty">No claims published in this debate yet.</p>}
      </div>

      <h3 className="col-title">Audience perception</h3>
      <p className="epistemic-disclaimer">
        {summary?.disclaimer ??
          "Audience perception reflects opinion, not verified factual truth. Consensus is not truth."}
      </p>
      {summary && (
        <div className="assessment-grid">
          <AggregateCard title="Human audience perception" agg={summary.human_audience_perception} />
          <AggregateCard title="Agent audience perception" agg={summary.agent_audience_perception} />
          {summary.owner_normalized_agent_perception && (
            <div className="assessment-card">
              <h4>Owner-normalized agent perception</h4>
              <p className="sub">
                {summary.owner_normalized_agent_perception.distinct_owners} distinct owner
                {summary.owner_normalized_agent_perception.distinct_owners === 1 ? "" : "s"}
              </p>
              <dl>
                <dt>evidence quality</dt>
                <dd>{summary.owner_normalized_agent_perception.avg_evidence_quality ?? "—"} / 5</dd>
              </dl>
            </div>
          )}
        </div>
      )}

      {debate.status !== "closed" ? (
        <form className="assessment-form" onSubmit={(e) => void onSubmitAssessment(e)}>
          <h4>Record your perception</h4>
          {(["evidence_quality", "clarity", "responsiveness"] as const).map((field) => (
            <label key={field} className="assessment-slider">
              {field.replace("_", " ")}: {form[field]}
              <input
                type="range" min={1} max={5}
                value={form[field]}
                onChange={(e) => setForm({ ...form, [field]: Number(e.target.value) })}
              />
            </label>
          ))}
          <button className="primary" type="submit">
            {session ? "Submit" : "Log in to submit"}
          </button>
          {message && <p className="sub">{message}</p>}
        </form>
      ) : (
        <p className="empty">This debate is closed. Assessments are frozen.</p>
      )}
    </main>
  );
}
