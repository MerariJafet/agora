"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  civicDashboard,
  listCivicRoles,
  listFindings,
  listRfcs,
  listSummaries,
  type CivicDashboard,
  type CivicFinding,
  type CivicRole,
  type ForgeRfc,
  type SummaryArtifact,
} from "@/lib/civic";

export default function CivicPage() {
  const [dashboard, setDashboard] = useState<CivicDashboard | null>(null);
  const [roles, setRoles] = useState<CivicRole[]>([]);
  const [summaries, setSummaries] = useState<SummaryArtifact[]>([]);
  const [findings, setFindings] = useState<CivicFinding[]>([]);
  const [rfcs, setRfcs] = useState<ForgeRfc[]>([]);

  useEffect(() => {
    civicDashboard().then(setDashboard).catch(() => setDashboard(null));
    listCivicRoles().then((r) => setRoles(r.roles)).catch(() => setRoles([]));
    listSummaries().then((r) => setSummaries(r.summaries)).catch(() => setSummaries([]));
    listFindings().then((r) => setFindings(r.findings)).catch(() => setFindings([]));
    listRfcs().then((r) => setRfcs(r.rfcs)).catch(() => setRfcs([]));
  }, []);

  return (
    <main className="plaza">
      <Link className="back" href="/world">← back to World</Link>
      <h2>Civic Intelligence</h2>
      <p className="sub">
        Summaries, source audits, replay and RFCs are public intellectual
        objects. They do not decide truth or grant privileges.
      </p>

      <section className="stats-grid">
        {dashboard &&
          Object.entries(dashboard)
            .filter(([, value]) => typeof value === "number")
            .map(([label, value]) => (
              <div className="stat" key={label}>
                <span>{label.replaceAll("_", " ")}</span>
                <strong>{value}</strong>
              </div>
            ))}
      </section>

      <section className="columns">
        <div>
          <h3 className="col-title">Civic Roles</h3>
          <div className="claim-list">
            {roles.map((role) => (
              <article className="claim-card" key={role.role_id}>
                <span className="badge">{role.status}</span>
                <h4>{role.name}</h4>
                <p>{role.role}</p>
              </article>
            ))}
          </div>
        </div>
        <div>
          <h3 className="col-title">Forge RFCs</h3>
          <div className="claim-list">
            {rfcs.map((rfc) => (
              <article className="claim-card" key={rfc.rfc_id}>
                <span className="badge">{rfc.status}</span>
                <h4>{rfc.title}</h4>
                <p>{rfc.decision ?? "under review"}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="columns">
        <div>
          <h3 className="col-title">Summaries</h3>
          <div className="claim-list">
            {summaries.map((summary) => (
              <article className="claim-card" key={summary.summary_id}>
                <span className="badge">{summary.trust}</span>
                <p>{summary.content}</p>
                <p className="sub">{summary.explicit_uncertainty}</p>
              </article>
            ))}
          </div>
        </div>
        <div>
          <h3 className="col-title">Findings</h3>
          <div className="claim-list">
            {findings.map((finding) => (
              <article className="claim-card" key={finding.finding_id}>
                <span className="badge">{finding.finding_type}</span>
                <h4>{finding.severity}</h4>
                <p>{finding.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <p className="sub">
        Reputation remains multidimensional. There is no single karma, truth
        score or automatic adoption of improved versions.
      </p>
    </main>
  );
}
