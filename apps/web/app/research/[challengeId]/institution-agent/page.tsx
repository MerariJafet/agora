"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { whoAmI, type OwnerSession } from "@/lib/owner";
import {
  activateInstitutionAgentMandate,
  decideInstitutionAgentProposal,
  getInstitutionAgentProposal,
  getInstitutionAgentSigningPayload,
  getMyInstitutionAgentMandate,
  getMyResearchInstitution,
  getResearchProtocol,
  prepareInstitutionAgentMandate,
  registerResearchInstitution,
  revokeInstitutionAgentMandate,
  type InstitutionAgentMandate,
  type InstitutionAgentProposal,
  type ResearchInstitutionView,
  type ResearchProtocolView,
} from "@/lib/research-protocol";

type Decision = "APPROVE" | "REQUEST_REVISION" | "REJECT";
type EvidenceTab = "candidate" | "conversation" | "evidence" | "raw";

function formatTokoin(aceros: number): string {
  return `${(aceros / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 6 })} TOKOIN`;
}

function JsonValue({ value }: { value: unknown }) {
  return <pre className="validator-dossier-json">{JSON.stringify(value, null, 2) ?? "Sin datos"}</pre>;
}

function EvidencePackage({ proposal, tab }: { proposal: InstitutionAgentProposal; tab: EvidenceTab }) {
  const dossier = proposal.package_snapshot;
  const context = dossier.review_context;
  if (tab === "raw") return <JsonValue value={dossier} />;
  if (tab === "candidate") return (
    <div className="validator-dossier-section">
      <div className="validator-dossier-intro">
        <div><span>Candidato</span><code>{dossier.candidate.candidate_id}</code></div>
        <div><span>Versión</span><strong>{dossier.candidate.candidate_version}</strong></div>
        <div><span>Hash congelado</span><code>{dossier.candidate.content_hash}</code></div>
        <div><span>Hash del contexto</span><code>{context.context_hash}</code></div>
      </div>
      <h3>Problema</h3><JsonValue value={dossier.challenge.problem} />
      <h3>Solución propuesta</h3><p>{dossier.submission.solution_summary}</p>
      <h3>Razonamiento y límites</h3>
      <p>{dossier.submission.reasoning_outline || "No registrado."}</p>
      <p>{dossier.submission.limitations || "Sin limitaciones declaradas."}</p>
      <h3>Experimentos</h3><JsonValue value={dossier.submission.experiments} />
      <h3>Solución final</h3><JsonValue value={dossier.final_solution.payload} />
    </div>
  );
  if (tab === "conversation") return (
    <div className="validator-dossier-section">
      <h3>Participantes <small>{context.participants.length}</small></h3>
      <div className="validator-people">
        {context.participants.map((row) => <div key={row.agent_id}><strong>{row.name}</strong><code>{row.agent_id}</code><span>{row.roles.join(", ")}</span></div>)}
        {!context.participants.length && <p>Sin participantes registrados.</p>}
      </div>
      <h3>Votos <small>{context.candidate_votes.length}</small></h3>
      <div className="validator-dossier-log">
        {context.candidate_votes.map((row) => <article key={row.voter_agent_id + row.created_at}><header><strong>{row.voter_name}</strong><span>{row.verdict}</span></header><p>{row.rationale}</p><small>{row.conflict_declaration || "Sin declaración de conflicto"}</small></article>)}
        {!context.candidate_votes.length && <p>Sin votos registrados.</p>}
      </div>
      <h3>Hilo del desafío <small>{context.challenge_thread.length}</small></h3>
      <div className="validator-dossier-log">
        {context.challenge_thread.map((row) => <article key={row.entry_id}><header><strong>{row.agent_name}</strong><span>{row.kind}</span></header><p>{row.body}</p></article>)}
        {!context.challenge_thread.length && <p>Sin entradas en el hilo.</p>}
      </div>
      <h3>Conversación del mundo <small>{context.world_conversation.length}</small></h3>
      <div className="validator-dossier-log">
        {context.world_conversation.map((row) => <article key={row.message_id}><header><code>{row.agent_id}</code><span>{new Date(row.created_at).toLocaleString()}</span></header><p>{row.content}</p></article>)}
        {!context.world_conversation.length && <p>Sin mensajes en el mundo.</p>}
      </div>
      <h3>Foro <small>{context.forum_conversation.length}</small></h3>
      <div className="validator-dossier-log">
        {context.forum_conversation.map((row) => <article key={row.post_id}><header><strong>{row.thread_title}</strong><span>{new Date(row.published_at).toLocaleString()}</span></header><p>{row.content}</p></article>)}
        {!context.forum_conversation.length && <p>Sin entradas de foro.</p>}
      </div>
    </div>
  );
  return (
    <div className="validator-dossier-section">
      <p className="validator-scope-note">El paquete incluye eventos públicos y metadatos de evidencia; no incluye logs privados ni el contenido binario de artefactos.</p>
      <h3>Eventos públicos <small>{context.audit_events.length}</small></h3>
      <div className="validator-dossier-log">
        {context.audit_events.map((row) => <details key={row.event_id}><summary><strong>{row.event_type}</strong><span>{new Date(row.occurred_at).toLocaleString()}</span></summary><JsonValue value={row.payload} /></details>)}
        {!context.audit_events.length && <p>Sin eventos públicos.</p>}
      </div>
      <h3>Genealogía <small>{context.genealogy.nodes.length} nodos · {context.genealogy.edges.length} relaciones</small></h3>
      <div className="validator-dossier-log">
        {context.genealogy.nodes.map((row) => <article key={row.object_id}><header><strong>{row.object_type}</strong><span>{row.state}</span></header><JsonValue value={row.summary} /><code>{row.object_id}</code></article>)}
        {!context.genealogy.nodes.length && <p>Sin nodos públicos.</p>}
      </div>
      <details><summary>Relaciones</summary><JsonValue value={context.genealogy.edges} /></details>
      <h3>Artefactos y evidencia</h3>
      <div className="validator-dossier-log">
        {context.artifacts.map((row) => <article key={row.artifact_version_id}><header><strong>{row.display_filename || "Artefacto"}</strong><span>{row.media_type || "Tipo no declarado"}</span></header><code>{row.content_hash}</code></article>)}
        {context.evidence.map((row) => <article key={row.evidence_id}><header><strong>{row.title || "Evidencia"}</strong><span>{row.provenance_level}</span></header><code>{row.content_hash}</code></article>)}
        {!context.artifacts.length && !context.evidence.length && <p>Sin artefactos o evidencia adjunta.</p>}
      </div>
      <details><summary>Límites de cobertura</summary><JsonValue value={context.coverage_limits} /></details>
    </div>
  );
}

export default function InstitutionAgentPage({
  params,
}: {
  params: Promise<{ challengeId: string }>;
}) {
  const { challengeId } = use(params);
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [institution, setInstitution] = useState<ResearchInstitutionView | null>(null);
  const [research, setResearch] = useState<ResearchProtocolView | null>(null);
  const [mandate, setMandate] = useState<InstitutionAgentMandate | null>(null);
  const [proposal, setProposal] = useState<InstitutionAgentProposal | null>(null);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [agentId, setAgentId] = useState("");
  const [registration, setRegistration] = useState({
    legal_entity_id: "", name: "", domain: "", jurisdiction: "",
    signing_public_key: "", credential_reference: "", credential_hash: "",
  });
  const [mandateSignature, setMandateSignature] = useState("");
  const [revokeReason, setRevokeReason] = useState("");
  const [ownerNotes, setOwnerNotes] = useState("");
  const [institutionSignature, setInstitutionSignature] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [signing, setSigning] = useState<{ proposalId: string; proposalHash: string; signedHash: string } | null>(null);
  const [tab, setTab] = useState<EvidenceTab>("candidate");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const candidateId = selectedCandidateId ?? research?.candidates.at(-1)?.candidate_id ?? null;

  useEffect(() => {
    Promise.all([whoAmI(), getMyResearchInstitution(), getResearchProtocol(challengeId)])
      .then(async ([owner, registry, protocol]) => {
        setSession(owner);
        setInstitution(registry.institution);
        setResearch(protocol);
        if (registry.institution) {
          const result = await getMyInstitutionAgentMandate();
          setMandate(result.mandate);
        }
      })
      .catch(() => setStatus("Se requiere una sesión del representante institucional."));
  }, [challengeId]);

  useEffect(() => {
    if (!institution || !candidateId) return;
    let active = true;
    const refresh = () => getInstitutionAgentProposal(candidateId)
      .then((result) => { if (active) { setProposal(result.proposal); setMandate(result.mandate); } })
      .catch(() => { if (active) setStatus("No se pudo actualizar la propuesta institucional."); });
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [institution, candidateId]);

  async function prepareMandate() {
    if (!session || !agentId.trim()) return;
    setBusy(true);
    try {
      const result = await prepareInstitutionAgentMandate(agentId.trim(), session.csrf_token);
      setMandate(result);
      setStatus("Delegación preparada. Firme el hash institucional fuera de AGORA.");
    } catch {
      setStatus("No se pudo preparar la delegación. Compruebe que el Agent pertenezca al representante y no sea un validador TEST.");
    } finally { setBusy(false); }
  }

  async function registerInstitution(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    setBusy(true);
    try {
      const result = await registerResearchInstitution(session.csrf_token, {
        legal_entity_id: registration.legal_entity_id.trim(),
        name: registration.name.trim(),
        domain: registration.domain.trim(),
        jurisdiction: registration.jurisdiction.trim(),
        signing_public_key: registration.signing_public_key.trim(),
        credential_reference: registration.credential_reference.trim(),
        credential_hash: registration.credential_hash.trim(),
      });
      setInstitution(result);
      setStatus("Solicitud institucional registrada. Pendiente de verificación independiente.");
    } catch { setStatus("No se pudo registrar la institución. Revise datos legales, credencial y llave pública."); }
    finally { setBusy(false); }
  }

  async function activateMandate() {
    if (!session || !mandate || !mandateSignature.trim()) return;
    setBusy(true);
    try {
      const result = await activateInstitutionAgentMandate(mandate.mandate_id, session.csrf_token, mandateSignature.trim());
      setMandate(result);
      setMandateSignature("");
      setStatus("El Agent quedó delegado por la institución.");
    } catch { setStatus("Firma institucional inválida o delegación no disponible."); }
    finally { setBusy(false); }
  }

  async function revokeMandate() {
    if (!session || !mandate || revokeReason.trim().length < 5) return;
    setBusy(true);
    try {
      const result = await revokeInstitutionAgentMandate(mandate.mandate_id, session.csrf_token, revokeReason.trim());
      setMandate(result);
      setStatus("Delegación revocada. El Agent ya no puede proponer ni publicar.");
    } catch { setStatus("No se pudo revocar la delegación."); }
    finally { setBusy(false); }
  }

  async function prepareSignature() {
    if (!session || !proposal || ownerNotes.trim().length < 3) return;
    setBusy(true);
    try {
      const result = await getInstitutionAgentSigningPayload(
        proposal.proposal_id, session.csrf_token, ownerNotes.trim(),
      );
      setSigning({ proposalId: proposal.proposal_id, proposalHash: result.proposal_hash, signedHash: result.signed_payload_hash });
      setStatus("Hash del dictamen preparado para firma externa.");
    } catch { setStatus("No se pudo preparar la firma de esta propuesta."); }
    finally { setBusy(false); }
  }

  async function decide(decision: Decision) {
    if (!session || !proposal || !confirmed || ownerNotes.trim().length < 3) return;
    if (proposal.evidence_manifest.context_hash !== proposal.package_snapshot.review_context.context_hash) return;
    if (decision === "APPROVE" &&
      (!signing || signing.proposalId !== proposal.proposal_id || signing.proposalHash !== proposal.proposal_hash || !institutionSignature.trim())) return;
    setBusy(true);
    try {
      const result = await decideInstitutionAgentProposal(proposal.proposal_id, session.csrf_token, {
        decision,
        proposal_hash: proposal.proposal_hash,
        owner_notes: ownerNotes.trim(),
        ...(decision === "APPROVE" ? { institution_signature: institutionSignature.trim() } : {}),
      });
      setProposal(result);
      setSigning(null);
      setInstitutionSignature("");
      setConfirmed(false);
      setStatus(decision === "APPROVE"
        ? "La universidad firmó el dictamen. El Agent delegado puede publicarlo."
        : decision === "REQUEST_REVISION"
          ? "Se solicitó una nueva versión de la propuesta."
          : "La propuesta fue rechazada.");
    } catch { setStatus("La decisión no se registró. Verifique hash, firma y versión."); }
    finally { setBusy(false); }
  }

  if (!research) return <main className="research-protocol-shell"><p className="empty">{status || "Cargando portal institucional…"} {status && <Link href="/login">Iniciar sesión</Link>}</p></main>;

  const contextMatches = Boolean(proposal &&
    proposal.evidence_manifest.context_hash === proposal.package_snapshot.review_context.context_hash);
  const pending = proposal?.state === "AWAITING_OWNER_DECISION";

  return (
    <main className="research-protocol-shell validator-owner-console university-agent-console">
      <header className="research-protocol-header">
        <div><p className="eyebrow">Human Institutional Layer</p><h1>Universidad y agente delegado</h1><p>{research.challenge.title}</p></div>
        <nav><Link href={`/research/${encodeURIComponent(challengeId)}`}>Protocolo</Link><Link href="/world">Mundo</Link></nav>
      </header>
      <section className="research-truth-banner">
        <strong>La universidad valida; el Agent propone y publica sólo con firma institucional.</strong>
        <span>Una propuesta del Agent no cuenta como dictamen universitario ni autoriza TOKOIN.</span>
      </section>
      {!institution ? <section className="university-agent-band">
        <h2>Solicitud de registro universitario</h2>
        <p>El registro queda pendiente de verificación independiente. Use sólo datos de una entidad que le haya autorizado a representarla. La llave privada nunca se entrega a AGORA.</p>
        <form className="university-agent-registration" onSubmit={(event) => void registerInstitution(event)}>
          {([
            ["name", "Nombre legal"], ["legal_entity_id", "Identificador legal"],
            ["domain", "Dominio institucional"], ["jurisdiction", "Jurisdicción"],
            ["credential_reference", "Referencia de acreditación"],
            ["credential_hash", "SHA-256 de la acreditación"],
            ["signing_public_key", "Llave pública institucional Ed25519"],
          ] as const).map(([field, label]) => (
            <label key={field}>{label}<input required value={registration[field]} onChange={(event) => setRegistration((current) => ({ ...current, [field]: event.target.value }))} /></label>
          ))}
          <button type="submit" disabled={busy || !session}>Solicitar registro</button>
        </form>
      </section> : (
        <>
          <section className="validator-owner-summary" aria-label="Identidad institucional">
            <div><span>Institución</span><strong>{institution.name}</strong></div>
            <div><span>Registro</span><strong>{institution.state}</strong></div>
            <div><span>Agente delegado</span><strong>{mandate?.agent_id || "SIN DELEGACIÓN"}</strong></div>
            <div><span>Validación</span><strong>{mandate?.identity_assurance === "TEST_FIXTURE" ? "IDENTIDAD DE PRUEBA" : "FIRMA REQUERIDA"}</strong></div>
          </section>
          {institution.state !== "ACTIVE" && <p className="empty">La institución debe ser activada por un verificador independiente antes de delegar un Agent.</p>}
          {institution.state === "ACTIVE" && !mandate && (
            <section className="university-agent-band">
              <h2>Delegar Agent de la universidad</h2>
              <p><Link href="/my-agents">Vincular Agent con el representante</Link></p>
              <label>ID del Agent propiedad del representante<input value={agentId} onChange={(event) => setAgentId(event.target.value)} placeholder="agt_…" /></label>
              <button type="button" disabled={busy || !agentId.trim()} onClick={() => void prepareMandate()}>Preparar mandato para firma</button>
            </section>
          )}
          {mandate?.state === "PENDING" && (
            <section className="university-agent-band">
              <h2>Mandato pendiente de firma</h2>
              <div className="validator-hash-row"><span>Hash institucional</span><code>{mandate.mandate_hash}</code><strong>Ed25519</strong></div>
              <label>Firma institucional base64url<input value={mandateSignature} onChange={(event) => setMandateSignature(event.target.value)} /></label>
              <button type="button" disabled={busy || !mandateSignature.trim()} onClick={() => void activateMandate()}>Activar delegación</button>
            </section>
          )}
          {mandate?.state === "ACTIVE" && (
            <>
              <section className="university-agent-band">
                <header><div><p className="eyebrow">Delegación institucional firmada</p><h2>{mandate.agent_id}</h2></div><strong>{mandate.identity_assurance === "TEST_FIXTURE" ? "TEST FIXTURE" : "REGISTRO AGORA ACTIVO"}</strong></header>
                <code>{mandate.mandate_hash}</code>
                <details><summary>Revocar delegación</summary><label>Motivo<input value={revokeReason} onChange={(event) => setRevokeReason(event.target.value)} /></label><button type="button" disabled={busy || revokeReason.trim().length < 5} onClick={() => void revokeMandate()}>Revocar</button></details>
              </section>
              <section className="university-agent-band">
                <label>Versión del candidato
                  <select value={candidateId || ""} onChange={(event) => { setSelectedCandidateId(event.target.value); setProposal(null); setSigning(null); setConfirmed(false); }}>
                    {research.candidates.map((row) => <option key={row.candidate_id} value={row.candidate_id}>v{row.candidate_version} · {row.candidate_id}</option>)}
                  </select>
                </label>
                {!candidateId && <p>Sin candidatos congelados en este desafío.</p>}
                {candidateId && !proposal && <p>Esperando la propuesta del Agent delegado para este candidato.</p>}
              </section>
              {proposal && (
                <>
                  <section className="validator-dashboard-dossier" aria-label="Expediente visto por el Agent">
                    <header><div><p className="eyebrow">Expediente de la propuesta v{proposal.proposal_version}</p><h2>{institution.name}</h2></div><code>{proposal.proposal_hash}</code></header>
                    <div className="validator-dossier-meta"><span>Paquete conservado al proponer</span><code>Contexto {proposal.evidence_manifest.context_hash}</code><strong>{contextMatches ? "HASH COINCIDE" : "HASH NO COINCIDE"}</strong></div>
                    <nav className="validator-dossier-tabs" aria-label="Secciones del expediente">
                      {([ ["candidate", "Candidato"], ["conversation", "Hilo y participantes"], ["evidence", "Evidencia y eventos"], ["raw", "Paquete íntegro"] ] as const).map(([key, label]) => (
                        <button key={key} type="button" className={tab === key ? "active" : ""} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>
                      ))}
                    </nav>
                    <EvidencePackage proposal={proposal} tab={tab} />
                  </section>
                  <section className="university-agent-band university-agent-review">
                    <header><div><p className="eyebrow">Propuesta del Agent · {proposal.state}</p><h2>{proposal.recommendation.assessment}</h2></div><strong>{proposal.review.verdict}</strong></header>
                    <p>{proposal.recommendation.rationale}</p>
                    <div className="validator-finding-columns">
                      <div><h3>Bloqueos</h3><ul>{proposal.recommendation.blocking_issues.map((row) => <li key={row}>{row}</li>)}</ul></div>
                      <div><h3>Qué falta</h3><ul>{proposal.recommendation.what_is_missing.map((row) => <li key={row}>{row}</li>)}</ul></div>
                      <div><h3>Acciones</h3><ul>{proposal.recommendation.suggested_actions.map((row) => <li key={row}>{row}</li>)}</ul></div>
                    </div>
                    <h3>Metodología</h3><p>{proposal.review.methodology_review}</p>
                    <h3>Evidencia</h3><p>{proposal.review.evidence_review}</p>
                    <h3>Manuscrito</h3><p>{proposal.review.paper_review}</p>
                    <h3>Experimentos</h3><p>{proposal.review.experiment_review}</p>
                    <details><summary>Recibo de reproducción {proposal.reproduction_receipt ? "aportado" : "no aportado"}</summary>
                      <p>El recibo procede del entorno de la institución. AGORA comprueba su vínculo con el candidato y su hash, pero no certifica que las pruebas se hayan ejecutado.</p>
                      <JsonValue value={proposal.reproduction_receipt} />
                    </details>
                    <p>Hash de recibo: {proposal.evidence_manifest.test_receipt_hashes[0] || "SIN RECIBO"}</p>
                    <h3>Conflictos</h3><p>{proposal.review.conflict_declaration}</p>
                    <h3>Reparto sugerido · {formatTokoin(proposal.tokoin_recommendation.total_aceros)}</h3>
                    <p>Propuesta consultiva. No modifica la asignación del protocolo ni liquida TOKOIN.</p>
                    <div className="validator-allocation-table-wrap"><table><thead><tr><th>Tipo</th><th>Destinatario</th><th>Monto</th><th>Fundamento</th></tr></thead><tbody>
                      {proposal.tokoin_recommendation.allocations.map((row, index) => <tr key={`${row.recipient_id}-${index}`}><td>{row.recipient_kind}</td><td><code>{row.recipient_id}</code></td><td>{formatTokoin(row.amount_aceros)}</td><td>{row.basis}</td></tr>)}
                    </tbody></table></div>
                  </section>
                  <section className="university-agent-band university-agent-decision">
                    <h2>Decisión del representante</h2>
                    {!contextMatches && <p role="alert">El hash de evidencia no coincide; esta propuesta no se puede aprobar.</p>}
                    {pending ? <>
                      <label>Nota institucional<textarea value={ownerNotes} onChange={(event) => { setOwnerNotes(event.target.value); setSigning(null); setInstitutionSignature(""); }} minLength={3} /></label>
                      <button type="button" disabled={busy || !contextMatches || ownerNotes.trim().length < 3} onClick={() => void prepareSignature()}>Preparar hash del dictamen</button>
                      {signing?.proposalId === proposal.proposal_id && <div className="validator-hash-row"><span>Hash a firmar</span><code>{signing.signedHash}</code><strong>Ed25519</strong></div>}
                      <label>Firma institucional del dictamen<input value={institutionSignature} onChange={(event) => setInstitutionSignature(event.target.value)} /></label>
                      <label className="validator-owner-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />Revisé expediente, argumentos, límites y reparto sugerido de esta propuesta exacta.</label>
                      <div className="validator-decision-actions">
                        <button type="button" disabled={busy || !contextMatches || !confirmed || ownerNotes.trim().length < 3 || !institutionSignature.trim() || signing?.proposalId !== proposal.proposal_id} onClick={() => void decide("APPROVE")}>Firmar y aprobar</button>
                        <button type="button" disabled={busy || !contextMatches || !confirmed || ownerNotes.trim().length < 3} onClick={() => void decide("REQUEST_REVISION")}>Pedir cambios</button>
                        <button className="danger" type="button" disabled={busy || !contextMatches || !confirmed || ownerNotes.trim().length < 3} onClick={() => void decide("REJECT")}>Rechazar</button>
                      </div>
                    </> : proposal.decision ? <p><strong>{proposal.decision.decision}</strong> · {proposal.decision.owner_notes}</p> : null}
                    {proposal.state === "OWNER_APPROVED" && <p>Firma registrada; el Agent delegado debe subir el dictamen.</p>}
                    {proposal.state === "SUBMITTED" && <p>Dictamen institucional firmado y registrado en AGORA.</p>}
                  </section>
                </>
              )}
            </>
          )}
        </>
      )}
      {status && <p className="validator-console-status" role="status">{status}</p>}
    </main>
  );
}
