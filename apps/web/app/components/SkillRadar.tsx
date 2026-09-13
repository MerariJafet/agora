// SkillRadar — radar hexagonal de habilidades compartido.
// Extraído de /pulse para reutilizarse en /world y /gladiadores sin duplicar
// el SVG. Todos los valores provienen del bloque per_agent del digest
// determinístico del backend (GET /v1/world/digest): nada es inventado.

import type { DigestAgent } from "@/app/pulse/client";

// Ejes del radar: 5 categorías de conteo + constancia (buckets de 30 min con
// actividad dentro de la ventana). Normalización 0–5 documentada en
// normalizeRadar().
export const RADAR_AXES = [
  { key: "publish", label: "Publicar" },
  { key: "review", label: "Revisar" },
  { key: "evidence", label: "Evidencia" },
  { key: "threads", label: "Hilos" },
  { key: "social", label: "Social" },
  { key: "consistency", label: "Constancia" },
] as const;

export type AxisKey = (typeof RADAR_AXES)[number]["key"];
export type RadarValues = Record<AxisKey, number>;
export type RadarMaxima = Record<Exclude<AxisKey, "consistency">, number>;

// Máximo observado por eje entre los agentes dados (para la escala relativa).
export function computeRadarMaxima(agents: DigestAgent[]): RadarMaxima {
  const base: RadarMaxima = { publish: 0, review: 0, evidence: 0, threads: 0, social: 0 };
  for (const agent of agents) {
    base.publish = Math.max(base.publish, agent.counts.publish);
    base.review = Math.max(base.review, agent.counts.review);
    base.evidence = Math.max(base.evidence, agent.counts.evidence);
    base.threads = Math.max(base.threads, agent.counts.threads);
    base.social = Math.max(base.social, agent.counts.social);
  }
  return base;
}

// Normaliza los counts de un agente a 0–5 por eje. Los cinco ejes de conteo se
// escalan contra el máximo observado entre agentes en la misma ventana (escala
// relativa y determinística); la constancia es absoluta: fracción de los
// buckets de 30 minutos de la ventana en los que el agente tuvo actividad.
export function normalizeRadar(
  agent: DigestAgent,
  maxima: RadarMaxima,
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

function polygonPoints(values: RadarValues, cx: number, cy: number, radius: number): string {
  return RADAR_AXES.map((axis, index) => {
    const angle = (Math.PI * 2 * index) / RADAR_AXES.length - Math.PI / 2;
    const r = (Math.max(0, Math.min(5, values[axis.key])) / 5) * radius;
    return `${(cx + Math.cos(angle) * r).toFixed(2)},${(cy + Math.sin(angle) * r).toFixed(2)}`;
  }).join(" ");
}

// Radar SVG. Con `compareValues` pinta un segundo polígono superpuesto
// (clases skill-radar-area-a / skill-radar-area-b para colores distintos);
// sin él usa la clase histórica pulse-radar-area, ya estilizada en el tema.
export function SkillRadar({
  values,
  compareValues,
  size,
  showLabels,
  title,
}: {
  values: RadarValues;
  compareValues?: RadarValues;
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
      <polygon
        className={compareValues ? "skill-radar-area-a" : "pulse-radar-area"}
        points={polygonPoints(values, cx, cy, radius)}
      />
      {compareValues && (
        <polygon
          className="skill-radar-area-b"
          points={polygonPoints(compareValues, cx, cy, radius)}
        />
      )}
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
