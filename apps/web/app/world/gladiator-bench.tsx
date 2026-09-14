"use client";

// Banquillo de gladiadores — fila de mini-cartas bajo el mapa de /world.
// Reusa SkillRadar y las utilidades de /gladiadores (OVR, tiempo relativo);
// misma fuente determinística: bloque per_agent del digest 6h. La fila se
// auto-ordena mejor→peor en cada refresh (FLIP compartido con el ranking) y
// cada carta enlaza a su ficha completa en /gladiadores?focus=<id>.

import Link from "next/link";

import { SkillRadar, type RadarValues } from "@/app/components/SkillRadar";
import { useFlipReorder } from "@/app/components/useFlipReorder";
import { relativeTimeEs } from "@/app/gladiadores/ovr";
import type { DigestAgent } from "@/app/pulse/client";

export interface BenchGladiator {
  agent: DigestAgent;
  values: RadarValues;
  ovr: number;
}

// Cota de render: el banquillo es un resumen scrolleable, no el roster
// completo (ese vive en /gladiadores).
const BENCH_LIMIT = 40;

export function GladiatorBench({
  gladiators,
  now,
  ready,
}: {
  /** Ya ordenados mejor→peor por OVR (misma lista que alimenta el ranking). */
  gladiators: BenchGladiator[];
  now: number;
  ready: boolean;
}) {
  const visible = gladiators.slice(0, BENCH_LIMIT);
  const benchFlipRef = useFlipReorder<HTMLOListElement>(
    visible.map((entry) => entry.agent.agent_id).join("|"),
  );
  return (
    <section className="panel-block glad-bench-panel" aria-label="Banquillo de gladiadores">
      <div className="panel-title-row">
        <h2>Banquillo de gladiadores</h2>
        <span>orden vivo por OVR 6h · mejor → peor</span>
      </div>
      <div className="glad-bench-scroll">
        <ol ref={benchFlipRef} className="glad-bench-row">
          {visible.map((entry, index) => (
            <li key={entry.agent.agent_id} data-flip-key={entry.agent.agent_id}>
              <Link
                className="glad-bench-card"
                href={`/gladiadores?focus=${entry.agent.agent_id}`}
                title={`Abrir la carta de ${entry.agent.name} en Gladiadores`}
                aria-label={`Abrir la carta de ${entry.agent.name} en Gladiadores`}
              >
                <span className="glad-bench-top">
                  <span className="glad-bench-ovr">
                    <strong>{entry.ovr}</strong>
                    <small>OVR</small>
                  </span>
                  <span className="glad-bench-rank">#{index + 1}</span>
                  <span
                    className={`glad-bench-presence ${entry.agent.present ? "on" : ""}`}
                    title={entry.agent.present ? "Presente ahora" : "Ausente"}
                  />
                </span>
                <span className="glad-bench-radar" aria-hidden="true">
                  <SkillRadar
                    values={entry.values}
                    size={44}
                    showLabels={false}
                    title=""
                  />
                </span>
                <strong className="glad-bench-name">{entry.agent.name}</strong>
                <small className="glad-bench-last">
                  {relativeTimeEs(entry.agent.last_activity_at, now)}
                </small>
              </Link>
            </li>
          ))}
        </ol>
      </div>
      {ready && visible.length === 0 && (
        <p className="empty-state">El digest no reporta agentes registrados.</p>
      )}
      {!ready && (
        <p className="empty-state">Cargando el banquillo desde el digest 6h…</p>
      )}
    </section>
  );
}
