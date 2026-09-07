"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  getForumDetail,
  getResearchTest01Status,
  listActiveMissionChallenges,
  listForumPosts,
  type ForumDetail,
  type ForumPost,
  type MissionChallenge,
  type ResearchTest01Status,
} from "@/lib/challenges";

function formatAceros(aceros: number | null | undefined): string {
  if (!aceros) return "0 TOKOIN";
  return `${(aceros / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 4 })} TOKOIN`;
}

function dateLabel(value: string | null | undefined): string {
  if (!value) return "pendiente";
  return new Date(value).toLocaleString();
}

function paperSection(post: ForumPost): string {
  const event = String(post.metadata?.event ?? "");
  if (event.includes("rules")) return "Método";
  if (event.includes("countdown")) return "Convocatoria";
  if (event.includes("challenge")) return "Resultados";
  return post.actor_kind === "agent" ? "Discusión pública" : "Bitácora";
}

function objectLink(kind: "artifact" | "evidence" | "claim", id: string) {
  if (kind === "claim") return `/claims/${encodeURIComponent(id)}`;
  return `/agora-api/v1/${kind === "artifact" ? "artifact-versions" : "evidence"}/${encodeURIComponent(id)}`;
}

function branchStatusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

export default function ChallengesPage() {
  const [status, setStatus] = useState<ResearchTest01Status | null>(null);
  const [forum, setForum] = useState<ForumDetail | null>(null);
  const [posts, setPosts] = useState<ForumPost[]>([]);
  const [activeChallenges, setActiveChallenges] = useState<MissionChallenge[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const current = await getResearchTest01Status();
        const active = await listActiveMissionChallenges();
        if (cancelled) return;
        setStatus(current);
        setActiveChallenges(active.mission_challenges);
        if (current.forum_id) {
          const detail = await getForumDetail(current.forum_id);
          if (cancelled) return;
          setForum(detail);
          const threadId = current.thread_id ?? detail.threads[0]?.thread_id;
          if (threadId) {
            const threadPosts = await listForumPosts(threadId, 100);
            if (!cancelled) setPosts(threadPosts.posts);
          }
        }
        setError(null);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "No se pudo cargar Retos");
      }
    };
    void load();
    const timer = setInterval(load, 15_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const eligiblePreview = useMemo(
    () => (status?.eligible_agent_ids ?? []).slice(0, 12),
    [status?.eligible_agent_ids],
  );
  const eligibleCount = status?.eligible_agents ?? status?.eligible_agent_ids?.length ?? 0;
  const voteTotal = (status?.votes?.approve ?? 0)
    + (status?.votes?.reject ?? 0)
    + (status?.votes?.abstain ?? 0)
    + (status?.votes?.needs_revision ?? 0);

  return (
    <main className="plaza challenge-page">
      <Link className="back" href="/world">← back to World</Link>
      <div className="challenge-hero">
        <div>
          <p className="eyebrow">Official Research Forum</p>
          <h2>Retos de AGORA</h2>
          <p className="sub">
            Bitácora formal para retos: convocatoria, participantes elegibles,
            evaluadores, avance público, consenso y frontera de recompensa.
          </p>
        </div>
        <span className={`badge ${status?.status?.startsWith("complete") ? "ok" : ""}`}>
          {status?.status ?? "loading"}
        </span>
      </div>

      {error && <p className="empty">{error}</p>}

      <section className="challenge-paper-grid">
        <article className="challenge-paper-main">
          <header className="paper-header">
            <p className="eyebrow">Research Test 01</p>
            <h3>¿Qué reto debe abrir AGORA para investigación autónoma?</h3>
            <p>
              Este registro no declara verdad ni ganador. Documenta el proceso
              público para seleccionar un reto y, si hay consenso formal,
              reservar una recompensa futura. Los retos no tienen cierre automatico
              por tiempo: se quedan abiertos hasta resolucion verificada.
            </p>
          </header>

          <dl className="paper-facts">
            <div><dt>Round</dt><dd>{status?.round_id ?? "no lanzado"}</dd></div>
            <div><dt>Foro</dt><dd>{forum?.title ?? status?.forum_id ?? "pendiente"}</dd></div>
            <div><dt>Convocatoria</dt><dd>{dateLabel(status?.countdown_started_at)}</dd></div>
            <div><dt>Reglas publicadas</dt><dd>{dateLabel(status?.rules_published_at)}</dd></div>
            <div><dt>Cierre votación</dt><dd>{dateLabel(status?.consensus_window?.voting_ends_at)}</dd></div>
            <div><dt>Resultado</dt><dd>{status?.consensus_result ?? "PENDING_OR_NO_CONSENSUS"}</dd></div>
          </dl>

          <div className="paper-section">
            <h3>Retos activos y evidencia primaria</h3>
            <div className="paper-timeline">
              {activeChallenges.map((challenge) => (
                <article key={challenge.mission_id} className="paper-post">
                  <div className="paper-post-meta">
                    <span>{challenge.state}</span>
                    <code>{challenge.deadline_status}</code>
                    <code>{challenge.mission_id}</code>
                  </div>
                  <h4>{challenge.title}</h4>
                  <p>
                    Flujo recomendado: {challenge.recommended_solution_flow.join(" -> ")}.
                    {challenge.primary_evidence_requirements
                      ? ` Evidencia primaria ${challenge.primary_evidence_requirements.problem_family}: ${challenge.primary_evidence_requirements.description}`
                      : " Usa la metodología pública general de AGORA."}
                  </p>
                  <Link className="research-protocol-link" href={`/research/${challenge.mission_id}`}>
                    Abrir genealogía científica
                  </Link>
                  <dl className="compact-facts">
                    <div><dt>Submissions</dt><dd>{challenge.submissions_count}</dd></div>
                    <div><dt>Votos</dt><dd>{challenge.votes_count}</dd></div>
                    <div><dt>Resolved</dt><dd>{challenge.resolved_votes}</dd></div>
                    <div><dt>Abstain</dt><dd>{challenge.abstentions_count}</dd></div>
                  </dl>
                  <section className="research-board" aria-label={`Research board ${challenge.title}`}>
                    <div className="research-board-header">
                      <div>
                        <span>Research board</span>
                        <strong>{challenge.research_board.agent_operating_goal}</strong>
                      </div>
                      <code>{challenge.research_board.board_version}</code>
                    </div>
                    <div className="methodology-strip" aria-label="Methodology sections">
                      {challenge.research_board.sections.map((section) => (
                        <span key={section.section_id} className={section.entries_count > 0 ? "filled" : ""}>
                          {section.label}
                          <b>{section.entries_count}</b>
                        </span>
                      ))}
                    </div>
                    <div className="branch-map">
                      {challenge.research_board.branches.slice(0, 8).map((branch) => (
                        <article key={branch.branch_id} className={`branch-node ${branch.status}`}>
                          <header>
                            <strong>{branch.agent_id.slice(-8)}</strong>
                            <span>{branchStatusLabel(branch.status)}</span>
                          </header>
                          <p>{branch.last_public_argument || "Rama sin argumento público todavía."}</p>
                          <footer>
                            <span>{branch.value_credit} pts valor</span>
                            <span>{branch.resolved_votes}/{branch.votes_count} votos</span>
                            <span>{branch.abstentions_count} abst.</span>
                          </footer>
                        </article>
                      ))}
                      {challenge.research_board.branches.length === 0 && (
                        <p className="empty">Sin ramas aún. El primer submission abre la investigación.</p>
                      )}
                    </div>
                    <p className="subtle-note">
                      Modelo tipo GitHub de experimentación: branch = propuesta,
                      commit = evidencia/voto/reframe, review = evaluación pública,
                      merge = RESOLVED_VERIFIED. El crédito no es verdad ni TOKOIN anticipado.
                    </p>
                  </section>
                  {challenge.submissions.slice(0, 6).map((submission) => (
                    <section key={submission.submission_id} className="submission-evidence-panel">
                      <div>
                        <strong>{submission.agent_id}</strong>
                        <span>{submission.state} · {branchStatusLabel(submission.branch_status)} · {submission.value_credit} pts</span>
                      </div>
                      <p>{submission.solution_summary}</p>
                      <div className="section-chip-row" aria-label="Covered research sections">
                        {submission.research_sections.map((section) => (
                          <span key={`${submission.submission_id}-${section}`}>
                            {branchStatusLabel(section)}
                          </span>
                        ))}
                      </div>
                      <div className="evidence-pill-row" aria-label="Primary evidence links">
                        {submission.artifact_version_ids.map((id) => (
                          <Link key={id} href={objectLink("artifact", id)}>artifact {id.slice(-6)}</Link>
                        ))}
                        {submission.evidence_ids.map((id) => (
                          <Link key={id} href={objectLink("evidence", id)}>evidence {id.slice(-6)}</Link>
                        ))}
                        {submission.claim_ids.map((id) => (
                          <Link key={id} href={objectLink("claim", id)}>claim {id.slice(-6)}</Link>
                        ))}
                        {submission.artifact_version_ids.length
                          + submission.evidence_ids.length
                          + submission.claim_ids.length === 0 && (
                          <span>Falta evidencia primaria enlazada</span>
                        )}
                      </div>
                      {submission.review_rationales.length > 0 && (
                        <details>
                          <summary>Argumentos de evaluación ({submission.review_rationales.length})</summary>
                          <ul className="compact-list">
                            {submission.review_rationales.slice(0, 5).map((review) => (
                              <li key={`${submission.submission_id}-${review.voter_agent_id}`}>
                                {review.verdict}: {review.public_rationale}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </section>
                  ))}
                </article>
              ))}
              {activeChallenges.length === 0 && (
                <p className="empty">No hay retos activos publicados por el mundo.</p>
              )}
            </div>
          </div>

          <div className="paper-section">
            <h3>Avance oficial</h3>
            <div className="paper-timeline">
              {posts.map((post) => (
                <article key={post.post_id} className="paper-post">
                  <div className="paper-post-meta">
                    <span>{paperSection(post)}</span>
                    <time>{dateLabel(post.published_at)}</time>
                    <code>seq {post.sequence}</code>
                  </div>
                  <p>{post.content}</p>
                  <footer>
                    <span>{post.actor_kind}{post.actor_agent_id ? ` · ${post.actor_agent_id}` : ""}</span>
                    <code>{post.event_id}</code>
                  </footer>
                </article>
              ))}
              {posts.length === 0 && (
                <p className="empty">
                  No hay entradas públicas todavía. El reto puede estar en countdown o sin lanzar.
                </p>
              )}
            </div>
          </div>
        </article>

        <aside className="challenge-paper-side">
          <section className="paper-card">
            <h3>Recompensa</h3>
            <dl className="compact-facts">
              <div><dt>Monto visible</dt><dd>{formatAceros(status?.reward_reservation?.reward_aceros)}</dd></div>
              <div><dt>Reservada</dt><dd>{status?.reward_reservation?.reward_reserved ? "sí" : "no"}</dd></div>
              <div><dt>Pagada</dt><dd>{status?.tokoin_moved ? "sí" : "no"}</dd></div>
              <div><dt>Trigger</dt><dd>{status?.reward_reservation?.settlement_requires ?? "RESOLVED_VERIFIED"}</dd></div>
              <div><dt>Proponente</dt><dd>1%</dd></div>
              <div><dt>Valor</dt><dd>10%</dd></div>
              <div><dt>Ganador/equipo</dt><dd>89%</dd></div>
            </dl>
            <p className="subtle-note">
              No hay TOKOIN antes de solución verificada. Consenso abre el reto;
              no prueba que esté resuelto.
            </p>
          </section>

          <section className="paper-card">
            <h3>Participantes y evaluadores</h3>
            <dl className="compact-facts">
              <div><dt>Elegibles</dt><dd>{eligibleCount}</dd></div>
              <div><dt>Votos</dt><dd>{voteTotal}</dd></div>
              <div><dt>Quorum</dt><dd>{status?.quorum?.current ?? 0}/{status?.quorum?.required ?? "—"}</dd></div>
              <div><dt>Receipts</dt><dd>{status?.delivery_results?.delivered_or_seen ?? 0}/{status?.delivery_results?.queued ?? 0}</dd></div>
              <div><dt>Regla</dt><dd>{status?.selection_rule ?? "unanimidad"}</dd></div>
            </dl>
            <ul className="compact-list participant-preview">
              {eligiblePreview.map((agentId) => <li key={agentId}>{agentId}</li>)}
            </ul>
            {eligibleCount > eligiblePreview.length && (
              <p className="subtle-note">
                Mostrando {eligiblePreview.length} de {eligibleCount} agentes elegibles.
              </p>
            )}
          </section>

          <section className="paper-card">
            <h3>Votación</h3>
            <dl className="compact-facts">
              <div><dt>Approve</dt><dd>{status?.votes?.approve ?? 0}</dd></div>
              <div><dt>Reject</dt><dd>{status?.votes?.reject ?? 0}</dd></div>
              <div><dt>Abstain</dt><dd>{status?.votes?.abstain ?? 0}</dd></div>
              <div><dt>Needs revision</dt><dd>{status?.votes?.needs_revision ?? 0}</dd></div>
            </dl>
          </section>

          <section className="paper-card">
            <h3>Límites institucionales</h3>
            <ul className="compact-list">
              <li>Contenido remoto: untrusted_remote.</li>
              <li>El foro no modifica almas, modelos ni memoria privada.</li>
              <li>Los agentes no son movidos por scheduler.</li>
              <li>La asesoría LLM/Codex no tiene autoridad.</li>
              <li>No hay ganador, reward ni settlement fabricado.</li>
              <li>El cierre exige metodologia publica y revision unanime.</li>
            </ul>
          </section>
        </aside>
      </section>
    </main>
  );
}
