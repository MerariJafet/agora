"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { whoAmI, type OwnerSession } from "@/lib/owner";
import {
  decidePilotReviewProposal,
  getOwnerPilotReviewProposals,
  getResearchProtocol,
  type PilotOwnerQueue,
  type PilotReviewProposal,
  type ResearchProtocolView,
} from "@/lib/research-protocol";

type Decision = "APPROVE" | "REQUEST_REVISION" | "REJECT";

function short(value: string): string {
  return value.length > 20 ? `${value.slice(0, 9)}…${value.slice(-8)}` : value;
}

function tokoin(aceros: number): string {
  return `${(aceros / 100_000_000).toLocaleString(undefined, {
    maximumFractionDigits: 6,
  })} TOKOIN`;
}

function Findings({ title, rows }: { title: string; rows: string[] }) {
  return (
    <section className="validator-finding-list">
      <h3>{title}</h3>
      {rows.length ? <ul>{rows.map((row) => <li key={row}>{row}</li>)}</ul> : <p>Ninguno.</p>}
    </section>
  );
}

export default function ValidatorReviewPage({
  params,
}: {
  params: Promise<{ challengeId: string }>;
}) {
  const { challengeId } = use(params);
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [research, setResearch] = useState<ResearchProtocolView | null>(null);
  const [queue, setQueue] = useState<PilotOwnerQueue | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refresh() {
    const [owner, protocol, nextQueue] = await Promise.all([
      whoAmI(),
      getResearchProtocol(challengeId),
      getOwnerPilotReviewProposals(challengeId),
    ]);
    setSession(owner);
    setResearch(protocol);
    setQueue(nextQueue);
  }

  useEffect(() => {
    Promise.all([
      whoAmI(),
      getResearchProtocol(challengeId),
      getOwnerPilotReviewProposals(challengeId),
    ])
      .then(([owner, protocol, nextQueue]) => {
        setSession(owner);
        setResearch(protocol);
        setQueue(nextQueue);
      })
      .catch(() => setStatus("Se requiere la sesión del operador que asignó el panel."));
  }, [challengeId]);

  async function decide(proposal: PilotReviewProposal, decision: Decision) {
    const ownerNotes = notes[proposal.proposal_id]?.trim() ?? "";
    if (!session || ownerNotes.length < 3 || !confirmed[proposal.proposal_id]) return;
    setBusy(proposal.proposal_id);
    setStatus(null);
    try {
      await decidePilotReviewProposal(proposal.proposal_id, session.csrf_token, {
        decision,
        proposal_hash: proposal.proposal_hash,
        owner_notes: ownerNotes,
      });
      await refresh();
      setStatus(
        decision === "APPROVE"
          ? "Propuesta aprobada. El agente puede firmar y subir este dictamen exacto."
          : decision === "REQUEST_REVISION"
            ? "Revisión solicitada. El agente debe emitir una nueva versión."
            : "Propuesta rechazada. Esta asignación no puede publicar ni comprometer el dictamen.",
      );
    } catch {
      setStatus("La decisión no se registró. Actualice la propuesta y verifique su hash.");
    } finally {
      setBusy(null);
    }
  }

  if (!research || !queue) {
    return <main className="research-protocol-shell"><p className="empty">{status ?? "Cargando dictámenes…"}</p></main>;
  }

  return (
    <main className="research-protocol-shell validator-owner-console">
      <header className="research-protocol-header">
        <div>
          <p className="eyebrow">Institutional Validation Layer</p>
          <h1>Decisión humana sobre validadores TEST</h1>
          <p>{research.challenge.title}</p>
        </div>
        <nav>
          <Link href={`/research/${encodeURIComponent(challengeId)}`}>Volver al protocolo</Link>
          <Link href="/world">Mundo</Link>
        </nav>
      </header>

      <section className="research-truth-banner">
        <strong>TEST INSTITUTIONAL VALIDATOR · SIMULATED · NOT_REAL</strong>
        <span>Su decisión autoriza publicación sintética; no acredita una universidad ni liquida TOKOIN.</span>
      </section>

      <section className="validator-owner-summary" aria-label="Estado de revisión">
        <div><span>Operador</span><strong>{session?.username ?? queue.owner_id}</strong></div>
        <div><span>Esperando análisis</span><strong>{queue.pending_agent_analysis}</strong></div>
        <div><span>Propuestas</span><strong>{queue.proposals.length} / 2</strong></div>
        <div><span>Liquidación</span><strong>PROHIBIDA</strong></div>
      </section>

      <section className="validator-proposal-stack" aria-label="Propuestas de validación">
        {queue.proposals.map((proposal) => {
          const total = proposal.tokoin_recommendation.total_aceros;
          const canDecide = proposal.state === "AWAITING_OWNER_DECISION";
          return (
            <article className="validator-proposal" key={proposal.proposal_id}>
              <header>
                <div>
                  <p className="eyebrow">{proposal.validator.review_role.replaceAll("_", " ")}</p>
                  <h2>{proposal.validator.display_name}</h2>
                  <p>{proposal.validator.institution_name} · cerebro {proposal.validator.brain_provider}</p>
                </div>
                <span className="synthetic-badge">{proposal.validator.badge}</span>
              </header>

              <div className="validator-proposal-status">
                <div><span>Recomendación</span><strong>{proposal.recommendation.assessment}</strong></div>
                <div><span>Dictamen</span><strong>{proposal.review.verdict}</strong></div>
                <div><span>Reproducción</span><strong>{proposal.review.reproduction_status}</strong></div>
                <div><span>Confianza</span><strong>{proposal.review.confidence}%</strong></div>
              </div>

              <section className="validator-proposal-body">
                <h3>Conclusión</h3>
                <p>{proposal.recommendation.rationale}</p>
                <div className="validator-finding-columns">
                  <Findings title="Bloqueos" rows={proposal.recommendation.blocking_issues} />
                  <Findings title="Qué falta" rows={proposal.recommendation.what_is_missing} />
                  <Findings title="Acciones sugeridas" rows={proposal.recommendation.suggested_actions} />
                </div>
              </section>

              <section className="validator-evidence-coverage">
                <h3>Cobertura auditada</h3>
                <dl>
                  <div><dt>Participantes</dt><dd>{proposal.evidence_manifest.participant_ids.length}</dd></div>
                  <div><dt>Hilo y conversación</dt><dd>{proposal.evidence_manifest.thread_entry_ids.length}</dd></div>
                  <div><dt>Eventos</dt><dd>{proposal.evidence_manifest.event_ids.length}</dd></div>
                  <div><dt>Artefactos</dt><dd>{proposal.evidence_manifest.artifact_ids.length}</dd></div>
                  <div><dt>Pruebas</dt><dd>{proposal.review.executed_tests.length}</dd></div>
                </dl>
                <details>
                  <summary>Pruebas y hallazgos completos</summary>
                  <h4>Metodología</h4><p>{proposal.review.methodology_findings}</p>
                  <h4>Reproducción</h4><p>{proposal.review.reproduction_findings}</p>
                  <h4>Evidencia</h4><p>{proposal.review.evidence_findings}</p>
                  <h4>Observaciones menores</h4>
                  {proposal.review.minor_issues.length ? (
                    <ul>{proposal.review.minor_issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
                  ) : <p>Ninguna.</p>}
                  <h4>Pruebas ejecutadas</h4>
                  <ul>{proposal.review.executed_tests.map((test) => <li key={test}>{test}</li>)}</ul>
                  <h4>Artefactos revisados</h4>
                  <ul>{proposal.review.artifacts_reviewed.map((artifact) => <li key={artifact}>{artifact}</li>)}</ul>
                  <h4>Hash del contexto auditado</h4>
                  <code title={proposal.evidence_manifest.context_hash}>{proposal.evidence_manifest.context_hash}</code>
                </details>
              </section>

              <section className="validator-allocation">
                <header>
                  <div><h3>Reparto TOKOIN sugerido</h3><p>{tokoin(total)} · TEST CREDIT NON-SETTLEABLE</p></div>
                  <strong>0 movimientos reales</strong>
                </header>
                <div className="validator-allocation-table-wrap">
                  <table>
                    <thead><tr><th>Tipo</th><th>Destinatario</th><th>Proporción</th><th>Monto</th><th>Fundamento</th></tr></thead>
                    <tbody>
                      {proposal.tokoin_recommendation.allocations.map((row, index) => (
                        <tr key={`${row.recipient_kind}-${row.recipient_id}-${index}`}>
                          <td>{row.recipient_kind.replaceAll("_", " ")}</td>
                          <td><code title={row.recipient_id}>{short(row.recipient_id)}</code></td>
                          <td>{total ? ((row.amount_aceros / total) * 100).toFixed(2) : "0.00"}%</td>
                          <td>{tokoin(row.amount_aceros)}</td>
                          <td>{row.basis}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <footer className="validator-owner-decision">
                <div className="validator-hash-row">
                  <span>Propuesta v{proposal.proposal_version}</span>
                  <code title={proposal.proposal_hash}>{proposal.proposal_hash}</code>
                  <strong>{proposal.state}</strong>
                </div>
                {canDecide ? (
                  <>
                    <label>
                      Nota del operador
                      <textarea
                        required
                        minLength={3}
                        value={notes[proposal.proposal_id] ?? ""}
                        onChange={(event) => setNotes((current) => ({
                          ...current,
                          [proposal.proposal_id]: event.target.value,
                        }))}
                      />
                    </label>
                    <label className="validator-owner-confirm">
                      <input
                        type="checkbox"
                        checked={confirmed[proposal.proposal_id] ?? false}
                        onChange={(event) => setConfirmed((current) => ({
                          ...current,
                          [proposal.proposal_id]: event.target.checked,
                        }))}
                      />
                      Revisé el dictamen, su evidencia, faltantes y reparto TEST ligados a este hash.
                    </label>
                    <div className="validator-decision-actions">
                      <button type="button" disabled={busy === proposal.proposal_id || !confirmed[proposal.proposal_id] || (notes[proposal.proposal_id]?.trim().length ?? 0) < 3} onClick={() => void decide(proposal, "APPROVE")}>Aprobar propuesta</button>
                      <button type="button" disabled={busy === proposal.proposal_id || !confirmed[proposal.proposal_id] || (notes[proposal.proposal_id]?.trim().length ?? 0) < 3} onClick={() => void decide(proposal, "REQUEST_REVISION")}>Solicitar cambios</button>
                      <button className="danger" type="button" disabled={busy === proposal.proposal_id || !confirmed[proposal.proposal_id] || (notes[proposal.proposal_id]?.trim().length ?? 0) < 3} onClick={() => void decide(proposal, "REJECT")}>Rechazar</button>
                    </div>
                  </>
                ) : proposal.decision ? (
                  <p><strong>{proposal.decision.decision}</strong> · {proposal.decision.owner_notes}</p>
                ) : null}
              </footer>
            </article>
          );
        })}
        {queue.proposals.length === 0 && (
          <p className="empty">Los validadores todavía están analizando el candidato.</p>
        )}
      </section>
      {status && <p className="validator-console-status" role="status">{status}</p>}
    </main>
  );
}
