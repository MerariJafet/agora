"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  alphaCompatibility,
  alphaDashboard,
  listFeatureFlags,
  listModerationReports,
  type AlphaDashboard,
  type FeatureFlag,
  type ModerationReport,
} from "@/lib/alpha";

type Compatibility = Awaited<ReturnType<typeof alphaCompatibility>>;

export default function AlphaPage() {
  const [dashboard, setDashboard] = useState<AlphaDashboard | null>(null);
  const [reports, setReports] = useState<ModerationReport[]>([]);
  const [flags, setFlags] = useState<FeatureFlag[]>([]);
  const [compatibility, setCompatibility] = useState<Compatibility | null>(null);

  useEffect(() => {
    alphaDashboard().then(setDashboard).catch(() => setDashboard(null));
    listModerationReports().then((r) => setReports(r.reports)).catch(() => setReports([]));
    listFeatureFlags().then((r) => setFlags(r.feature_flags)).catch(() => setFlags([]));
    alphaCompatibility().then(setCompatibility).catch(() => setCompatibility(null));
  }, []);

  const checks = dashboard ? Object.entries(dashboard.readiness.checks) : [];

  return (
    <main className="plaza">
      <Link className="back" href="/world">
        ← back to World
      </Link>
      <h2>
        PUBLIC ALPHA GATE{" "}
        <span className={`badge ${dashboard?.readiness.status === "GO" ? "ok" : "revoked"}`}>
          {dashboard?.readiness.status ?? "loading"}
        </span>
      </h2>
      <p className="sub">
        Final roadmap gate for security, reliability, cost, moderation and
        operator readiness. This page does not deploy AGORA or require provider
        credentials.
      </p>

      {dashboard && (
        <>
          <section className="stats-grid">
            <div className="stat">
              <span>pending outbox</span>
              <strong>{dashboard.readiness.pending_outbox}</strong>
            </div>
            <div className="stat">
              <span>open high risk reports</span>
              <strong>{dashboard.readiness.open_high_or_critical_moderation}</strong>
            </div>
            <div className="stat">
              <span>admin actions</span>
              <strong>{dashboard.counts.admin_actions}</strong>
            </div>
            <div className="stat">
              <span>drills</span>
              <strong>{dashboard.counts.drills}</strong>
            </div>
          </section>

          <section className="columns">
            <div>
              <h3 className="col-title">Readiness checks</h3>
              <div className="claim-list">
                {checks.map(([key, ok]) => (
                  <article className="claim-card alpha-row" key={key}>
                    <span className={`badge ${ok ? "ok" : "revoked"}`}>
                      {ok ? "pass" : "block"}
                    </span>
                    <p>{key.replaceAll("_", " ")}</p>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <h3 className="col-title">Cost envelope</h3>
              <div className="claim-list">
                {Object.entries(dashboard.costs.agora_cost_units).map(([key, value]) => (
                  <article className="claim-card alpha-row" key={key}>
                    <span className="claim-type">{key.replaceAll("_", " ")}</span>
                    <strong>{value}</strong>
                  </article>
                ))}
                <article className="claim-card">
                  <span className="badge ok">separated</span>
                  <p>Owner inference cost: {dashboard.costs.owner_inference_cost}</p>
                  <p>Real charges enabled: {String(dashboard.costs.real_charges_enabled)}</p>
                </article>
              </div>
            </div>
          </section>

          <section className="columns">
            <div>
              <h3 className="col-title">Moderation queue</h3>
              <div className="claim-list">
                {reports.length === 0 && <p className="empty">No reports in the queue.</p>}
                {reports.map((report) => (
                  <article className="claim-card" key={report.report_id}>
                    <span className="badge">{report.status}</span>
                    <h4>{report.target_type}</h4>
                    <p>{report.reason}</p>
                    <p className="sub">{report.severity}</p>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <h3 className="col-title">Feature flags</h3>
              <div className="claim-list">
                {flags.length === 0 && <p className="empty">No feature flags configured.</p>}
                {flags.map((flag) => (
                  <article className="claim-card" key={flag.flag_id}>
                    <span className={`badge ${flag.enabled ? "ok" : "revoked"}`}>
                      {flag.enabled ? "enabled" : "disabled"}
                    </span>
                    <h4>{flag.key}</h4>
                    <p>{flag.description}</p>
                    <p className="sub">{flag.risk_level}</p>
                  </article>
                ))}
              </div>
            </div>
          </section>

          <section>
            <h3 className="col-title">Threat boundaries</h3>
            <div className="badge-row">
              {dashboard.boundaries_reviewed.map((boundary) => (
                <span className="badge ok" key={boundary}>
                  {boundary}
                </span>
              ))}
            </div>
          </section>

          <section className="columns">
            <div>
              <h3 className="col-title">Runbooks</h3>
              <div className="claim-list">
                {Object.entries(dashboard.runbooks).map(([name, steps]) => (
                  <article className="claim-card" key={name}>
                    <h4>{name.replaceAll("_", " ")}</h4>
                    <ol className="compact-list">
                      {steps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  </article>
                ))}
              </div>
            </div>
            <div>
              <h3 className="col-title">Protocol compatibility</h3>
              {compatibility && (
                <div className="claim-list">
                  <article className="claim-card">
                    <span className="badge ok">validated</span>
                    <h4>A2A</h4>
                    <p>{compatibility.a2a.sdk}</p>
                    <p className="sub">{compatibility.a2a.scope}</p>
                  </article>
                  <article className="claim-card">
                    <span className="badge ok">validated</span>
                    <h4>MCP</h4>
                    <p>{compatibility.mcp.sdk}</p>
                    <p className="sub">{compatibility.mcp.scope}</p>
                  </article>
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
