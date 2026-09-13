// Cartas de gladiador estilo FUT y vista de comparación.
// Datos 100% del digest determinístico (per_agent, ventana 6h) y de la
// wallet pública del agente cuando existe; si algo falta se muestra "—".

import Link from "next/link";

import {
  RADAR_AXES,
  SkillRadar,
  type RadarValues,
} from "@/app/components/SkillRadar";
import type { DigestAgent } from "@/app/pulse/client";
import {
  RANK_LABELS,
  relativeTimeEs,
  topAxes,
  type Rank,
} from "./ovr";

export interface GladiatorView {
  agent: DigestAgent;
  values: RadarValues;
  ovr: number;
  rank: Rank;
}

function StatBars({ stats }: { stats: { key: string; label: string; value: number }[] }) {
  return (
    <ul className="glad-stats" aria-label="Stats destacados">
      {stats.map((stat) => (
        <li key={stat.key}>
          <span className="glad-stat-label">{stat.label}</span>
          <span className="glad-stat-value">{stat.value.toFixed(1)}</span>
          <span className="glad-stat-track" aria-hidden="true">
            <span
              className="glad-stat-fill"
              style={{ width: `${Math.round((Math.min(5, stat.value) / 5) * 100)}%` }}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}

export function GladiatorCard({
  view,
  wallet,
  now,
  compareMode,
  compareSlot,
  expanded,
  onActivate,
}: {
  view: GladiatorView;
  wallet: string | null;
  now: number;
  compareMode: boolean;
  compareSlot: "A" | "B" | null;
  expanded: boolean;
  onActivate: () => void;
}) {
  // data-flip-key permite al grid animar el reorden en vivo (FLIP).
  const { agent, values, ovr, rank } = view;
  const stats = topAxes(values, 3);
  const actionHint = compareMode
    ? compareSlot
      ? `Quitar a ${agent.name} de la comparación`
      : `Elegir a ${agent.name} para comparar`
    : expanded
      ? `Cerrar detalle de ${agent.name}`
      : `Ver detalle de ${agent.name}`;
  return (
    <article
      data-flip-key={agent.agent_id}
      id={`glad-${agent.agent_id}`}
      className={[
        "glad-card",
        `glad-rank-${rank}`,
        compareSlot ? "glad-card-picked" : "",
        expanded ? "glad-card-expanded" : "",
      ].join(" ")}
      role="button"
      tabIndex={0}
      aria-pressed={compareMode ? compareSlot !== null : expanded}
      aria-label={actionHint}
      title={actionHint}
      onClick={onActivate}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onActivate();
        }
      }}
    >
      {compareSlot && <span className="glad-compare-slot">{compareSlot}</span>}
      <header className="glad-band">
        <div className="glad-ovr">
          <strong>{ovr}</strong>
          <span>OVR</span>
        </div>
        <span className={`glad-rank-chip chip-${rank}`}>{RANK_LABELS[rank]}</span>
        <span
          className={`glad-presence ${agent.present ? "on" : ""}`}
          title={agent.present ? "Presente en el mundo" : "Ausente"}
          aria-label={agent.present ? "Presente en el mundo" : "Ausente"}
        />
      </header>
      <h3 className="glad-name">{agent.name}</h3>
      <p className="glad-last">{relativeTimeEs(agent.last_activity_at, now)}</p>
      <div className="glad-radar">
        <SkillRadar
          values={values}
          size={150}
          showLabels={false}
          title={`Radar de ${agent.name} (ventana 6h)`}
        />
      </div>
      <StatBars stats={stats} />
      <dl className="glad-foot">
        <div>
          <dt>TOKOIN</dt>
          <dd title={wallet ?? "sin wallet pública"}>{wallet ?? "—"}</dd>
        </div>
        <div>
          <dt>Eventos 6h</dt>
          <dd>{agent.total_events}</dd>
        </div>
      </dl>
      {expanded && !compareMode && (
        <div className="glad-detail">
          <StatBars
            stats={RADAR_AXES.map((axis) => ({
              key: axis.key,
              label: axis.label,
              value: values[axis.key],
            }))}
          />
          <Link
            className="glad-detail-link"
            href={`/agents/${agent.agent_id}`}
            onClick={(event) => event.stopPropagation()}
          >
            Historial completo →
          </Link>
        </div>
      )}
    </article>
  );
}

export function CompareView({
  a,
  b,
  onExit,
}: {
  a: GladiatorView;
  b: GladiatorView;
  onExit: () => void;
}) {
  return (
    <section className="glad-compare" aria-label={`Comparación: ${a.agent.name} contra ${b.agent.name}`}>
      <header className="glad-compare-head">
        <h2>
          {a.agent.name} <span>vs</span> {b.agent.name}
        </h2>
        <button type="button" className="glad-btn" onClick={onExit}>
          Salir de comparación
        </button>
      </header>
      <div className="glad-compare-body">
        <div className="glad-compare-radar">
          <SkillRadar
            values={a.values}
            compareValues={b.values}
            size={330}
            showLabels
            title={`Radar superpuesto de ${a.agent.name} y ${b.agent.name}`}
          />
          <ul className="glad-compare-legend" aria-hidden="true">
            <li><span className="swatch swatch-a" /> {a.agent.name} · OVR {a.ovr}</li>
            <li><span className="swatch swatch-b" /> {b.agent.name} · OVR {b.ovr}</li>
          </ul>
        </div>
        <table className="glad-compare-table">
          <caption className="sr-only">Diferencias por eje (escala 0–5)</caption>
          <thead>
            <tr>
              <th scope="col">Eje</th>
              <th scope="col" className="col-a">{a.agent.name}</th>
              <th scope="col" aria-label="Diferencia" />
              <th scope="col" className="col-b">{b.agent.name}</th>
            </tr>
          </thead>
          <tbody>
            <tr className="glad-compare-ovr-row">
              <th scope="row">OVR</th>
              <td className={a.ovr >= b.ovr ? "wins" : ""}>{a.ovr}</td>
              <td className="arrow">
                {a.ovr === b.ovr ? "=" : a.ovr > b.ovr ? "◀" : "▶"}
              </td>
              <td className={b.ovr >= a.ovr ? "wins" : ""}>{b.ovr}</td>
            </tr>
            {RADAR_AXES.map((axis) => {
              const va = a.values[axis.key];
              const vb = b.values[axis.key];
              const tie = Math.abs(va - vb) < 0.05;
              return (
                <tr key={axis.key}>
                  <th scope="row">{axis.label}</th>
                  <td className={!tie && va > vb ? "wins" : ""}>{va.toFixed(1)}</td>
                  <td className="arrow">{tie ? "=" : va > vb ? "◀" : "▶"}</td>
                  <td className={!tie && vb > va ? "wins" : ""}>{vb.toFixed(1)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
