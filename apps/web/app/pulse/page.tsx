"use client";

// /pulse — Vista humana del mundo AGORA.
// Todo el texto proviene del digest determinístico del backend (plantillas
// sobre eventos reales del ledger). Esta página no inventa nada: solo pinta.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { KnowledgeStack } from "@/app/components/KnowledgeStack";
import {
  computeRadarMaxima,
  normalizeRadar,
  RADAR_AXES,
  SkillRadar,
  type RadarValues,
} from "@/app/components/SkillRadar";
import { fetchWorldDigest, type WorldDigest } from "./client";

const REFRESH_MS = 60_000;

const WINDOW_OPTIONS = [
  { seconds: 1800, label: "30m" },
  { seconds: 3600, label: "1h" },
  { seconds: 21600, label: "6h" },
] as const;

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

  const maxima = useMemo(() => computeRadarMaxima(activeAgents), [activeAgents]);

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
      const values = normalizeRadar(agent, maxima, digest.window_seconds);
      for (const axis of RADAR_AXES) sum[axis.key] += values[axis.key];
    }
    for (const axis of RADAR_AXES) sum[axis.key] /= activeAgents.length;
    return sum;
  }, [digest, activeAgents, maxima]);

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
            <KnowledgeStack
              missions={digest.pipeline_stages}
              stageOrder={digest.pipeline_stage_order}
            />
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
                <SkillRadar
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
                    <SkillRadar
                      values={normalizeRadar(agent, maxima, digest.window_seconds)}
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
