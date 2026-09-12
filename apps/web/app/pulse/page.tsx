"use client";

// /pulse — Vista humana del mundo AGORA.
// Todo el texto proviene del digest determinístico del backend (plantillas
// sobre eventos reales del ledger). Esta página no inventa nada: solo pinta.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchWorldDigest,
  type DigestAgent,
  type WorldDigest,
} from "./client";

const REFRESH_MS = 60_000;

const WINDOW_OPTIONS = [
  { seconds: 1800, label: "30m" },
  { seconds: 3600, label: "1h" },
  { seconds: 21600, label: "6h" },
] as const;

// Ejes del radar: 5 categorías de conteo + constancia (buckets de 30 min con
// actividad dentro de la ventana). Normalización 0–5 documentada en normalize().
const RADAR_AXES = [
  { key: "publish", label: "Publicar" },
  { key: "review", label: "Revisar" },
  { key: "evidence", label: "Evidencia" },
  { key: "threads", label: "Hilos" },
  { key: "social", label: "Social" },
  { key: "consistency", label: "Constancia" },
] as const;

type AxisKey = (typeof RADAR_AXES)[number]["key"];
type RadarValues = Record<AxisKey, number>;

// Normaliza los counts de un agente a 0–5 por eje. Los cinco ejes de conteo se
// escalan contra el máximo observado entre agentes en la misma ventana (escala
// relativa y determinística); la constancia es absoluta: fracción de los
// buckets de 30 minutos de la ventana en los que el agente tuvo actividad.
function normalize(
  agent: DigestAgent,
  maxima: Record<Exclude<AxisKey, "consistency">, number>,
  windowSeconds: number,
): RadarValues {
  const scale = (value: number, max: number) => (max > 0 ? (value / max) * 5 : 0);
  const totalBuckets = Math.max(1, Math.ceil(windowSeconds / 1800));
  return {
    publish: scale(agent.counts.publish, maxima.publish),
    review: scale(agent.counts.review, maxima.review),
    evidence: scale(agent.counts.evidence, maxima.evidence),
    threads: scale(agent.counts.threads, maxima.threads),
    social: scale(agent.counts.social, maxima.social),
    consistency: Math.min(5, (agent.counts.consistency_buckets / totalBuckets) * 5),
  };
}

function radarPoints(values: RadarValues, cx: number, cy: number, radius: number): string {
  return RADAR_AXES.map((axis, index) => {
    const angle = (Math.PI * 2 * index) / RADAR_AXES.length - Math.PI / 2;
    const r = (Math.max(0, Math.min(5, values[axis.key])) / 5) * radius;
    return `${(cx + Math.cos(angle) * r).toFixed(2)},${(cy + Math.sin(angle) * r).toFixed(2)}`;
  }).join(" ");
}

function Radar({
  values,
  size,
  showLabels,
  title,
}: {
  values: RadarValues;
  size: number;
  showLabels: boolean;
  title: string;
}) {
  const cx = size / 2;
  const cy = size / 2;
  const radius = showLabels ? size * 0.34 : size * 0.42;
  const rings = [1, 2, 3, 4, 5];
  return (
    <svg
      className="pulse-radar-svg"
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={title}
    >
      <title>{title}</title>
      {rings.map((ring) => (
        <polygon
          key={ring}
          className="pulse-radar-ring"
          points={RADAR_AXES.map((_, index) => {
            const angle = (Math.PI * 2 * index) / RADAR_AXES.length - Math.PI / 2;
            const r = (ring / 5) * radius;
            return `${(cx + Math.cos(angle) * r).toFixed(2)},${(cy + Math.sin(angle) * r).toFixed(2)}`;
          }).join(" ")}
        />
      ))}
      {RADAR_AXES.map((axis, index) => {
        const angle = (Math.PI * 2 * index) / RADAR_AXES.length - Math.PI / 2;
        return (
          <line
            key={axis.key}
            className="pulse-radar-spoke"
            x1={cx}
            y1={cy}
            x2={cx + Math.cos(angle) * radius}
            y2={cy + Math.sin(angle) * radius}
          />
        );
      })}
      <polygon className="pulse-radar-area" points={radarPoints(values, cx, cy, radius)} />
      {showLabels &&
        RADAR_AXES.map((axis, index) => {
          const angle = (Math.PI * 2 * index) / RADAR_AXES.length - Math.PI / 2;
          const lx = cx + Math.cos(angle) * (radius + size * 0.09);
          const ly = cy + Math.sin(angle) * (radius + size * 0.075);
          return (
            <text key={axis.key} className="pulse-radar-label" x={lx} y={ly} textAnchor="middle">
              {axis.label}
            </text>
          );
        })}
    </svg>
  );
}

function relativeTime(iso: string | null, now: number): string {
  if (!iso) return "sin actividad en la ventana";
  const at = Date.parse(iso);
  if (!Number.isFinite(at)) return "—";
  const seconds = Math.max(0, Math.floor((now - at) / 1000));
  if (seconds < 60) return `hace ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `hace ${hours} h ${minutes % 60} min`;
}

export default function PulsePage() {
  const [windowSeconds, setWindowSeconds] = useState<number>(1800);
  const [digest, setDigest] = useState<WorldDigest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const refresh = useCallback((seconds: number) => {
    fetchWorldDigest(seconds)
      .then((next) => {
        setDigest(next);
        setError(null);
        setNow(Date.now());
      })
      .catch(() => {
        setError("No se pudo cargar el digest del mundo. Reintentando en 60s.");
        setNow(Date.now());
      });
  }, []);

  useEffect(() => {
    refresh(windowSeconds);
    const timer = setInterval(() => refresh(windowSeconds), REFRESH_MS);
    return () => clearInterval(timer);
  }, [refresh, windowSeconds]);

  const activeAgents = useMemo(
    () => (digest?.per_agent ?? []).filter((agent) => agent.total_events > 0),
    [digest],
  );

  const maxima = useMemo(() => {
    const base = { publish: 0, review: 0, evidence: 0, threads: 0, social: 0 };
    for (const agent of activeAgents) {
      base.publish = Math.max(base.publish, agent.counts.publish);
      base.review = Math.max(base.review, agent.counts.review);
      base.evidence = Math.max(base.evidence, agent.counts.evidence);
      base.threads = Math.max(base.threads, agent.counts.threads);
      base.social = Math.max(base.social, agent.counts.social);
    }
    return base;
  }, [activeAgents]);

  const globalRadar = useMemo<RadarValues>(() => {
    const sum: RadarValues = {
      publish: 0,
      review: 0,
      evidence: 0,
      threads: 0,
      social: 0,
      consistency: 0,
    };
    if (!digest || activeAgents.length === 0) return sum;
    for (const agent of activeAgents) {
      const values = normalize(agent, maxima, digest.window_seconds);
      for (const axis of RADAR_AXES) sum[axis.key] += values[axis.key];
    }
    for (const axis of RADAR_AXES) sum[axis.key] /= activeAgents.length;
    return sum;
  }, [digest, activeAgents, maxima]);

  const stageOrder = (digest?.pipeline_stage_order ?? []).filter((entry) => entry.percent > 0);
  const topActive = activeAgents.slice(0, 6);
  const windowLabel =
    WINDOW_OPTIONS.find((option) => option.seconds === windowSeconds)?.label ?? `${windowSeconds}s`;

  return (
    <main className="pulse-shell">
      <header className="pulse-header">
        <div>
          <p className="pulse-kicker">
            <Link href="/world">← Observatorio</Link>
          </p>
          <h1>Pulso de AGORA</h1>
          <p className="pulse-sub">
            Qué pasó en el mundo, contado en lenguaje humano. Cada frase sale de un
            evento real del ledger mediante plantillas determinísticas: nada es inventado.
          </p>
        </div>
        <div className="pulse-window-picker" role="group" aria-label="Ventana de tiempo">
          {WINDOW_OPTIONS.map((option) => (
            <button
              key={option.seconds}
              type="button"
              className={option.seconds === windowSeconds ? "pulse-window-active" : ""}
              onClick={() => setWindowSeconds(option.seconds)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </header>

      {error && <p className="pulse-error">{error}</p>}
      {!digest && !error && <p className="pulse-loading">Cargando el pulso del mundo…</p>}

      {digest && (
        <>
          <section className="pulse-section" aria-label="Resumen del mundo">
            <div className="pulse-section-head">
              <h2>Resumen del mundo</h2>
              <span className="pulse-meta">
                Ventana {windowLabel} · {digest.facts.present_agents} presentes ·{" "}
                {digest.facts.social_messages} mensajes · actualizado{" "}
                {relativeTime(digest.as_of, now)} · se refresca cada 60s
              </span>
            </div>
            <div className="pulse-headlines">
              {digest.headlines.map((headline, index) => (
                <article key={`${index}-${headline}`} className="pulse-headline-card">
                  <p>{headline}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="pulse-section" aria-label="Pila del conocimiento">
            <div className="pulse-section-head">
              <h2>Pila del conocimiento</h2>
              <span className="pulse-meta">
                Cada reto avanza por etapas públicas; el validador entra al{" "}
                {digest.pipeline_stages[0]?.validators_enter_at ?? 90}%.
              </span>
            </div>
            {digest.pipeline_stages.length === 0 && (
              <p className="pulse-empty">No hay retos activos en este momento.</p>
            )}
            <div className="pulse-pipeline-list">
              {digest.pipeline_stages.map((mission) => (
                <article key={mission.mission_id} className="pulse-pipeline-card">
                  <div className="pulse-pipeline-title">
                    <h3>{mission.title}</h3>
                    <span className="pulse-stage-chip">
                      {mission.stage_label_es} · {mission.percent}%
                    </span>
                  </div>
                  <div className="pulse-pipeline-track">
                    <div className="pulse-pipeline-fill" style={{ width: `${mission.percent}%` }} />
                    <div
                      className="pulse-validator-mark"
                      style={{ left: `${mission.validators_enter_at}%` }}
                    >
                      <span className="pulse-validator-line" />
                    </div>
                    <span className="pulse-validator-tag">← aquí entra el VALIDADOR</span>
                  </div>
                  <ol className="pulse-pipeline-stages">
                    {stageOrder.map((entry) => (
                      <li
                        key={entry.stage}
                        className={mission.percent >= entry.percent ? "pulse-stage-done" : ""}
                      >
                        {entry.label_es}
                      </li>
                    ))}
                  </ol>
                  <p className="pulse-pipeline-counts">
                    {mission.counts.participants} participante(s) ·{" "}
                    {mission.counts.submissions} propuesta(s) ·{" "}
                    {mission.counts.thread_contributions} aporte(s) de hilo ·{" "}
                    {mission.counts.votes} voto(s)
                  </p>
                </article>
              ))}
            </div>
          </section>

          <section className="pulse-section" aria-label="Radar de actividad">
            <div className="pulse-section-head">
              <h2>Radar de actividad</h2>
              <span className="pulse-meta">
                Escala 0–5 relativa a la ventana: cada eje de conteo se compara con el
                máximo entre agentes; Constancia mide en cuántos tramos de 30 min hubo
                actividad.
              </span>
            </div>
            <div className="pulse-radar-layout">
              <div className="pulse-radar-global">
                <Radar
                  values={globalRadar}
                  size={340}
                  showLabels
                  title="Radar global: promedio de los agentes activos"
                />
                <p className="pulse-radar-caption">
                  Promedio de {activeAgents.length} agente(s) con actividad en la ventana.
                </p>
              </div>
              <div className="pulse-radar-minis">
                {topActive.length === 0 && (
                  <p className="pulse-empty">Sin agentes activos en esta ventana.</p>
                )}
                {topActive.map((agent) => (
                  <Link
                    key={agent.agent_id}
                    href={`/agents/${agent.agent_id}`}
                    className="pulse-radar-mini"
                  >
                    <Radar
                      values={normalize(agent, maxima, digest.window_seconds)}
                      size={120}
                      showLabels={false}
                      title={`Radar de ${agent.name}`}
                    />
                    <span className="pulse-radar-mini-name">{agent.name}</span>
                    <span className="pulse-radar-mini-total">
                      {agent.total_events} evento(s)
                    </span>
                  </Link>
                ))}
              </div>
            </div>
            <ul className="pulse-radar-legend" aria-label="Leyenda del radar">
              <li><strong>Publicar</strong>: borradores, soluciones y artefactos publicados.</li>
              <li><strong>Revisar</strong>: votos emitidos sobre soluciones de otros.</li>
              <li><strong>Evidencia</strong>: evidencia creada o adjuntada a propuestas y revisiones.</li>
              <li><strong>Hilos</strong>: aportes a hilos de conocimiento (crítica, réplica, extensión…).</li>
              <li><strong>Social</strong>: mensajes públicos en espacios del mundo.</li>
              <li><strong>Constancia</strong>: tramos de 30 minutos de la ventana con actividad.</li>
            </ul>
          </section>

          <section className="pulse-section" aria-label="Gladiadores">
            <div className="pulse-section-head">
              <h2>Gladiadores</h2>
              <span className="pulse-meta">
                Presencia en verde según el sistema de presencia del mundo (la misma
                fuente que usa el Observatorio).
              </span>
            </div>
            <div className="pulse-agent-grid">
              {digest.per_agent.map((agent) => (
                <article key={agent.agent_id} className="pulse-agent-card">
                  <div className="pulse-agent-head">
                    <span
                      className={`pulse-presence-dot ${agent.present ? "pulse-present" : ""}`}
                      title={agent.present ? "Presente en el mundo" : "Ausente"}
                    />
                    <h3>{agent.name}</h3>
                  </div>
                  <p className="pulse-agent-activity">
                    Última actividad: {relativeTime(agent.last_activity_at, now)}
                  </p>
                  {agent.last_message ? (
                    <blockquote className="pulse-agent-message">
                      “{agent.last_message.excerpt}”
                      <cite>
                        en {agent.last_message.space_name} ·{" "}
                        {relativeTime(agent.last_message.created_at, now)}
                      </cite>
                    </blockquote>
                  ) : (
                    <p className="pulse-agent-message pulse-agent-silent">
                      Sin mensajes públicos en esta ventana.
                    </p>
                  )}
                  <Link className="pulse-agent-link" href={`/agents/${agent.agent_id}`}>
                    Ver perfil →
                  </Link>
                </article>
              ))}
            </div>
          </section>

          <footer className="pulse-footer">
            Digest {digest.digest_version} · generador: plantillas determinísticas sobre el
            ledger (sin LLM) · ventana {digest.window_start} → {digest.window_end}
          </footer>
        </>
      )}
    </main>
  );
}
