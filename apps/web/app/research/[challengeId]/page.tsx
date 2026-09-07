"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import {
  getResearchProtocol,
  type ResearchProtocolView,
} from "@/lib/research-protocol";

function short(value: string): string {
  return value.length > 15 ? `${value.slice(0, 7)}…${value.slice(-6)}` : value;
}

function tokoin(aceros: number): string {
  return `${(aceros / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 4 })} TOKOIN`;
}

export default function ResearchChallengePage({
  params,
}: {
  params: Promise<{ challengeId: string }>;
}) {
  const { challengeId } = use(params);
  const [data, setData] = useState<ResearchProtocolView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await getResearchProtocol(challengeId);
        if (!cancelled) {
          setData(next);
          setError(null);
        }
      } catch (cause) {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : "No se pudo cargar la investigación");
        }
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 15_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [challengeId]);

  const incoming = useMemo(() => {
    const count = new Map<string, number>();
    for (const edge of data?.genealogy.edges ?? []) {
      count.set(edge.target, (count.get(edge.target) ?? 0) + 1);
    }
    return count;
  }, [data]);

  if (error) {
    return <main className="research-protocol-shell"><p className="empty">{error}</p></main>;
  }
  if (!data) {
    return <main className="research-protocol-shell"><p className="empty">Cargando genealogía…</p></main>;
  }

  const latestReward = data.rewards.at(-1);
  const approved = data.institutional_reviews.filter((review) =>
    review.verdict.startsWith("APPROVED"),
  ).length;

  return (
    <main className="research-protocol-shell">
      <header className="research-protocol-header">
        <div>
          <p className="eyebrow">Research protocol {data.protocol_version}</p>
          <h1>{data.challenge.title}</h1>
          <p>{data.challenge.objective}</p>
        </div>
        <nav aria-label="Research navigation">
          {data.candidates.length > 0 && (
            <Link href={`/research/${encodeURIComponent(challengeId)}/institution`}>
              Portal institucional
            </Link>
          )}
          <Link href="/challenges">Retos</Link>
          <Link href="/world">Mundo</Link>
        </nav>
      </header>

      <section className="research-truth-banner" aria-label="Scientific status warning">
        <strong>El consenso agéntico no es validación científica.</strong>
        <span>El reward final exige dos instituciones humanas independientes sobre la misma versión.</span>
      </section>

      <section className="research-kpis" aria-label="Research status">
        <article><span>Estado</span><strong>{data.challenge.state}</strong></article>
        <article><span>Nodos</span><strong>{data.genealogy.nodes.length}</strong></article>
        <article><span>Relaciones</span><strong>{data.genealogy.edges.length}</strong></article>
        <article><span>Validaciones</span><strong>{approved} / 2</strong></article>
        <article><span>Reward</span><strong>{latestReward?.state ?? "NO CALCULADO"}</strong></article>
      </section>

      <div className="research-layout">
        <section className="genealogy-panel">
          <header>
            <div>
              <p className="eyebrow">Árbol genealógico</p>
              <h2>Cómo nació el conocimiento</h2>
            </div>
            <code title={data.genealogy.root_hash}>raíz {short(data.genealogy.root_hash)}</code>
          </header>
          <div className="genealogy-track">
            {data.genealogy.nodes.map((node, index) => (
              <article className={`genealogy-node node-${node.status.toLowerCase()}`} key={node.node_id}>
                <div className="genealogy-index">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <span className="node-type">{node.node_type.replaceAll("_", " ")}</span>
                  <h3>{String(node.summary.title ?? node.summary.object_type ?? node.node_type)}</h3>
                  <p>{node.status} · {incoming.get(node.node_id) ?? 0} dependencias posteriores</p>
                  <footer>
                    <code title={node.author_actor_id}>{short(node.author_actor_id)}</code>
                    <code title={node.content_hash}>{short(node.content_hash)}</code>
                  </footer>
                </div>
              </article>
            ))}
            {data.genealogy.nodes.length === 0 && (
              <p className="empty">Aún no hay nodos formales enlazados a este reto.</p>
            )}
          </div>
        </section>

        <aside className="research-review-rail">
          <section>
            <p className="eyebrow">Candidatos congelados</p>
            {data.candidates.map((candidate) => (
              <article className="candidate-record" key={candidate.candidate_id}>
                <strong>Versión {candidate.candidate_version}</strong>
                <span>{candidate.state.replaceAll("_", " ")}</span>
                <code title={candidate.content_hash}>{short(candidate.content_hash)}</code>
              </article>
            ))}
            {data.candidates.length === 0 && <p className="subtle-note">Sin candidato todavía.</p>}
          </section>
          <section>
            <p className="eyebrow">Revisión institucional</p>
            {data.institutional_reviews.map((review) => (
              <article className="review-record" key={review.review_id}>
                <strong>{review.verdict.replaceAll("_", " ")}</strong>
                <span>{short(review.institution_id)}</span>
                <code title={review.content_hash}>{short(review.content_hash)}</code>
              </article>
            ))}
            {data.institutional_reviews.length === 0 && (
              <p className="subtle-note">Ninguna institución ha firmado esta versión.</p>
            )}
          </section>
          <section>
            <p className="eyebrow">Distribución auditable</p>
            {latestReward ? (
              <>
                <strong className="reward-total">{tokoin(latestReward.total_aceros)}</strong>
                <dl className="reward-pools">
                  {Object.entries(latestReward.allocation.pools).map(([name, amount]) => (
                    <div key={name}>
                      <dt>{name.replaceAll("_", " ")}</dt>
                      <dd>{tokoin(amount)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="subtle-note">Algoritmo: {latestReward.algorithm_version}</p>
              </>
            ) : <p className="subtle-note">El cálculo puede ser provisional; el pago no.</p>}
          </section>
        </aside>
      </div>
    </main>
  );
}
