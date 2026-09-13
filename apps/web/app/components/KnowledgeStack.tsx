// KnowledgeStack — "pila del conocimiento" compartida.
// Extraída de /pulse para reutilizarse en /world. Pinta el avance por etapas
// de cada reto (pipeline_stages del digest determinístico) con la marca
// "← aquí entra el VALIDADOR" al 90%. Solo pinta hechos del backend.

import type { DigestPipelineStage, DigestStageOrderEntry } from "@/app/pulse/client";

export function KnowledgeStack({
  missions,
  stageOrder,
  compact = false,
}: {
  missions: DigestPipelineStage[];
  stageOrder: DigestStageOrderEntry[];
  compact?: boolean;
}) {
  const visibleStages = stageOrder.filter((entry) => entry.percent > 0);
  if (missions.length === 0) {
    return <p className="pulse-empty">No hay retos activos en este momento.</p>;
  }
  return (
    <div className={`pulse-pipeline-list ${compact ? "knowledge-stack-compact" : ""}`}>
      {missions.map((mission) => (
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
            {visibleStages.map((entry) => (
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
  );
}
