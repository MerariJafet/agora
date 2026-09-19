"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { whoAmI, type OwnerSession } from "@/lib/owner";
import {
  decidePilotReviewProposal,
  getOwnerPilotAssignmentPackage,
  getOwnerPilotReviewProposals,
  getResearchProtocol,
  type PilotAssignmentPackage,
  type PilotOwnerQueue,
  type PilotReviewProposal,
  type ResearchProtocolView,
} from "@/lib/research-protocol";

type Decision = "APPROVE" | "REQUEST_REVISION" | "REJECT";
type DossierTab = "candidate" | "conversation" | "evidence" | "raw";

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

function StructuredValue({ value }: { value: unknown }) {
  return <pre className="validator-dossier-json">{JSON.stringify(value, null, 2) ?? "Sin datos"}</pre>;
}

function FieldValue({ value }: { value: unknown }) {
  return typeof value === "string"
    ? <p>{value}</p>
    : <StructuredValue value={value} />;
}

function Dossier({ dossier, tab }: { dossier: PilotAssignmentPackage; tab: DossierTab }) {
  const context = dossier.review_context;
  if (tab === "raw") return <StructuredValue value={dossier} />;
  if (tab === "candidate") return (
    <div className="validator-dossier-section">
      <div className="validator-dossier-intro">
        <div><span>Candidato congelado</span><code>{dossier.candidate.candidate_id}</code></div>
        <div><span>Versión</span><strong>{dossier.candidate.candidate_version}</strong></div>
        <div><span>Hash del candidato</span><code title={dossier.candidate.content_hash}>{dossier.candidate.content_hash}</code></div>
        <div><span>Raíz de conocimiento</span><code title={dossier.candidate.knowledge_root_hash}>{dossier.candidate.knowledge_root_hash}</code></div>
      </div>
      <h3>Problema y objetivo</h3>
      <FieldValue value={dossier.challenge.problem} />
      <FieldValue value={dossier.challenge.objective} />
      <h3>Solución propuesta</h3>
      <p>{dossier.submission.solution_summary}</p>
      <h4>Razonamiento</h4><p>{dossier.submission.reasoning_outline || "No registrado."}</p>
      <h4>Justificación pública</h4><p>{dossier.submission.public_rationale || "No registrada."}</p>
      <h4>Limitaciones</h4><p>{dossier.submission.limitations || "No registradas."}</p>
      <h4>Experimentos declarados</h4><StructuredValue value={dossier.submission.experiments} />
      <h4>Objeto final · {dossier.final_solution.visibility_lane}</h4>
      <StructuredValue value={dossier.final_solution.payload} />
    </div>
  );
  if (tab === "conversation") return (
    <div className="validator-dossier-section">
      <h3>Participantes <small>{context.participants.length}</small></h3>
      <div className="validator-people">
        {context.participants.map((person) => <div key={person.agent_id}><strong>{person.name}</strong><code>{person.agent_id}</code><span>{person.roles.join(", ") || "Participante"}</span></div>)}
        {!context.participants.length && <p>Sin participantes en este contexto.</p>}
      </div>
      <h3>Votos <small>{context.candidate_votes.length}</small></h3>
      <div className="validator-dossier-log">
        {context.candidate_votes.map((vote) => <article key={vote.voter_agent_id + vote.created_at}><header><strong>{vote.voter_name}</strong><span>{vote.verdict}</span></header><p>{vote.rationale}</p><small>Conflicto: {vote.conflict_declaration || "No declarado"}</small></article>)}
        {!context.candidate_votes.length && <p>Sin votos.</p>}
      </div>
      <h3>Hilo del desafío <small>{context.challenge_thread.length}</small></h3>
      <div className="validator-dossier-log">
        {context.challenge_thread.map((entry) => <article key={entry.entry_id}><header><strong>{entry.agent_name}</strong><span>{entry.kind} · {new Date(entry.created_at).toLocaleString()}</span></header><p>{entry.body}</p></article>)}
        {!context.challenge_thread.length && <p>Sin entradas en el hilo.</p>}
      </div>
      <h3>Conversación del mundo <small>{context.world_conversation.length}</small></h3>
      <div className="validator-dossier-log">
        {context.world_conversation.map((entry) => <article key={entry.message_id}><header><code>{short(entry.agent_id)}</code><span>{new Date(entry.created_at).toLocaleString()}</span></header><p>{entry.content}</p></article>)}
        {!context.world_conversation.length && <p>Sin mensajes del mundo.</p>}
      </div>
      <h3>Foro <small>{context.forum_conversation.length}</small></h3>
      <div className="validator-dossier-log">
        {context.forum_conversation.map((entry) => <article key={entry.post_id}><header><strong>{entry.thread_title}</strong><span>{new Date(entry.published_at).toLocaleString()}</span></header><p>{entry.content}</p></article>)}
        {!context.forum_conversation.length && <p>Sin entradas de foro.</p>}
      </div>
    </div>
  );
  return (
    <div className="validator-dossier-section">
      <p className="validator-scope-note">Registro público de auditoría incluido en el paquete. No incluye logs privados del servidor, contenido binario de artefactos ni mensajes fuera de los límites de cobertura.</p>
      <h3>Eventos públicos <small>{context.audit_events.length}</small></h3>
      <div className="validator-dossier-log">
        {context.audit_events.map((event) => <details key={event.event_id}><summary><strong>{event.event_type}</strong><span>{new Date(event.occurred_at).toLocaleString()}</span></summary><StructuredValue value={event.payload} /></details>)}
        {!context.audit_events.length && <p>Sin eventos públicos.</p>}
      </div>
      <h3>Genealogía <small>{context.genealogy.nodes.length} nodos · {context.genealogy.edges.length} relaciones</small></h3>
      <div className="validator-dossier-log">
        {context.genealogy.nodes.map((node) => <article key={node.object_id}><header><strong>{node.object_type}</strong><span>{node.state}</span></header><FieldValue value={node.summary} /><code>{node.object_id}</code></article>)}
        {!context.genealogy.nodes.length && <p>Sin nodos públicos.</p>}
      </div>
      <details><summary>Relaciones de genealogía</summary><StructuredValue value={context.genealogy.edges} /></details>
      <h3>Artefactos y evidencia</h3>
      <div className="validator-dossier-log">
        {context.artifacts.map((artifact) => <article key={artifact.artifact_version_id}><header><strong>{artifact.display_filename || "Artefacto"}</strong><span>{artifact.media_type || "Tipo no declarado"}</span></header><code>{artifact.content_hash}</code></article>)}
        {context.evidence.map((item) => <article key={item.evidence_id}><header><strong>{item.title || "Evidencia"}</strong><span>{item.provenance_level}</span></header><code>{item.content_hash}</code></article>)}
        {!context.artifacts.length && !context.evidence.length && <p>Sin artefactos o evidencia adjunta.</p>}
      </div>
      <details><summary>Límites de cobertura</summary><StructuredValue value={context.coverage_limits} /></details>
    </div>
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
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [dossier, setDossier] = useState<PilotAssignmentPackage | null>(null);
  const [dossierScope, setDossierScope] = useState<string | null>(null);
  const [dossierError, setDossierError] = useState<string | null>(null);
  const [tab, setTab] = useState<DossierTab>("candidate");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [queueRefreshFailed, setQueueRefreshFailed] = useState(false);
  const selectedProposalId = queue?.proposals.find((row) => row.assignment_id === selectedAssignmentId)?.proposal_id;
  const expectedDossierScope = selectedAssignmentId ? `${selectedAssignmentId}:${selectedProposalId ?? ""}` : null;

  async function refresh() {
    const [owner, protocol, nextQueue] = await Promise.all([
      whoAmI(),
      getResearchProtocol(challengeId),
      getOwnerPilotReviewProposals(challengeId),
    ]);
    setSession(owner);
    setResearch(protocol);
    setQueue(nextQueue);
    setQueueRefreshFailed(false);
    setSelectedAssignmentId((current) => current && nextQueue.assignments.some((row) => row.assignment_id === current)
      ? current : nextQueue.assignments[0]?.assignment_id ?? null);
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
        setQueueRefreshFailed(false);
        setSelectedAssignmentId(nextQueue.assignments[0]?.assignment_id ?? null);
      })
      .catch(() => setStatus("Se requiere la sesión del operador que asignó el panel."));
  }, [challengeId]);

  useEffect(() => {
    if (!selectedAssignmentId) return;
    let active = true;
    getOwnerPilotAssignmentPackage(selectedAssignmentId)
      .then((nextDossier) => {
        if (active) {
          setDossier(nextDossier);
          setDossierError(null);
          setDossierScope(`${selectedAssignmentId}:${selectedProposalId ?? ""}`);
        }
      })
      .catch(() => {
        if (active) {
          setDossier(null);
          setDossierError("No se pudo cargar el expediente de esta asignación.");
          setDossierScope(`${selectedAssignmentId}:${selectedProposalId ?? ""}`);
        }
      });
    return () => { active = false; };
  }, [selectedAssignmentId, selectedProposalId]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      getOwnerPilotReviewProposals(challengeId)
        .then((nextQueue) => { setQueue(nextQueue); setQueueRefreshFailed(false); })
        .catch(() => setQueueRefreshFailed(true));
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [challengeId]);

  async function decide(proposal: PilotReviewProposal, decision: Decision) {
    const ownerNotes = notes[proposal.proposal_id]?.trim() ?? "";
    if (!session || !dossier || dossierScope !== expectedDossierScope || queueRefreshFailed ||
      dossier.assignment_id !== proposal.assignment_id ||
      dossier.review_context.context_hash !== proposal.evidence_manifest.context_hash ||
      ownerNotes.length < 3 || !confirmed[proposal.proposal_id]) return;
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

  const selectedAssignment = queue.assignments.find((row) => row.assignment_id === selectedAssignmentId);
  const selectedProposal = queue.proposals.find((row) => row.assignment_id === selectedAssignmentId);
  const currentDossier = dossierScope === expectedDossierScope ? dossier : null;
  const contextMatches = Boolean(dossier && selectedProposal &&
    dossierScope === expectedDossierScope && dossier.assignment_id === selectedProposal.assignment_id &&
    dossier.review_context.context_hash === selectedProposal.evidence_manifest.context_hash);

  return (
    <main className="research-protocol-shell validator-owner-console">
      <header className="research-protocol-header">
        <div>
          <p className="eyebrow">Institutional Validation Layer</p>
          <h1>Panel de validación</h1>
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
      {queueRefreshFailed && <p className="validator-console-status" role="alert">No se pudo actualizar la cola. Recargue antes de decidir.</p>}

      <section className="validator-owner-summary" aria-label="Estado de revisión">
        <div><span>Operador</span><strong>{session?.username ?? queue.owner_id}</strong></div>
        <div><span>Esperando análisis</span><strong>{queue.pending_agent_analysis}</strong></div>
        <div><span>Propuestas</span><strong>{queue.proposals.length} / {queue.assignments.length}</strong></div>
        <div><span>Liquidación</span><strong>PROHIBIDA</strong></div>
      </section>

      <nav className="validator-dashboard-tracks" aria-label="Validadores asignados">
        {queue.assignments.map((assignment) => (
          <button
            key={assignment.assignment_id}
            type="button"
            className={assignment.assignment_id === selectedAssignmentId ? "active" : ""}
            aria-current={assignment.assignment_id === selectedAssignmentId ? "page" : undefined}
            onClick={() => { setSelectedAssignmentId(assignment.assignment_id); setTab("candidate"); }}
          >
            <span>{assignment.validator.brain_provider.toUpperCase()} · {assignment.validator.review_role === "REPRODUCTION_METHODOLOGY" ? "Reproducción / Metodología" : "Falsación / Evidencia"}</span>
            <strong>{assignment.validator.display_name}</strong>
            <small>{assignment.validator.badge} · {assignment.proposal_state || assignment.state}</small>
          </button>
        ))}
      </nav>

      {selectedAssignment && (
        <section className="validator-dashboard-dossier" aria-label="Expediente del validador">
          <header>
            <div><p className="eyebrow">Expediente ciego del agente</p><h2>{selectedAssignment.validator.institution_name}</h2></div>
            <span className="synthetic-badge">TEST INSTITUTIONAL VALIDATOR</span>
          </header>
          <div className="validator-dossier-meta">
            <span>{selectedProposal
              ? "Paquete conservado con la propuesta"
              : selectedAssignment.state === "ASSIGNED"
                ? "Paquete público actual antes de la propuesta"
                : "Contexto público actual de un panel histórico sin propuesta"}</span>
            {currentDossier && <code title={currentDossier.review_context.context_hash}>Contexto {short(currentDossier.review_context.context_hash)}</code>}
            <strong>{currentDossier?.peer_review_data_disclosed === false ? "REVISIÓN CIEGA" : "Cargando"}</strong>
          </div>
          <nav className="validator-dossier-tabs" aria-label="Secciones del expediente">
            {([ ["candidate", "Candidato"], ["conversation", "Hilo y participantes"], ["evidence", "Evidencia y eventos"], ["raw", "Paquete íntegro"] ] as const).map(([key, label]) => (
              <button key={key} type="button" className={tab === key ? "active" : ""} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>
            ))}
          </nav>
          {currentDossier ? <Dossier dossier={currentDossier} tab={tab} /> : <p className="empty">{dossierScope === expectedDossierScope ? dossierError : "Cargando expediente…"}</p>}
        </section>
      )}

      <section className="validator-proposal-stack" aria-label="Propuestas de validación">
        {queue.proposals.filter((row) => row.assignment_id === selectedAssignmentId).map((proposal) => {
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
                      Revisé el expediente, dictamen, faltantes y reparto TEST ligados a este hash. Esta decisión no es validación institucional humana ni libera TOKOIN.
                    </label>
                    <div className="validator-decision-actions">
                      <button type="button" disabled={busy === proposal.proposal_id || queueRefreshFailed || !contextMatches || !confirmed[proposal.proposal_id] || (notes[proposal.proposal_id]?.trim().length ?? 0) < 3} onClick={() => void decide(proposal, "APPROVE")}>Aprobar propuesta</button>
                      <button type="button" disabled={busy === proposal.proposal_id || queueRefreshFailed || !contextMatches || !confirmed[proposal.proposal_id] || (notes[proposal.proposal_id]?.trim().length ?? 0) < 3} onClick={() => void decide(proposal, "REQUEST_REVISION")}>Solicitar cambios</button>
                      <button className="danger" type="button" disabled={busy === proposal.proposal_id || queueRefreshFailed || !contextMatches || !confirmed[proposal.proposal_id] || (notes[proposal.proposal_id]?.trim().length ?? 0) < 3} onClick={() => void decide(proposal, "REJECT")}>Rechazar</button>
                    </div>
                    {!contextMatches && <p role="alert">El hash del expediente no coincide con el dictamen o no se pudo cargar. No decida hasta verificar el paquete.</p>}
                  </>
                ) : proposal.decision ? (
                  <p><strong>{proposal.decision.decision}</strong> · {proposal.decision.owner_notes}</p>
                ) : null}
              </footer>
            </article>
          );
        })}
        {selectedAssignment && !selectedProposal && (
          <p className="empty">
            {selectedAssignment.state === "ASSIGNED"
              ? "Este validador está analizando el candidato. La propuesta aparecerá aquí al enviarse."
              : "No hay propuesta del agente en esta asignación. El panel puede haber concluido antes de la puerta de decisión del propietario."}
          </p>
        )}
        {!queue.assignments.length && <p className="empty">No hay asignaciones de validadores TEST para este desafío bajo su cuenta.</p>}
      </section>
      {status && <p className="validator-console-status" role="status">{status}</p>}
    </main>
  );
}
