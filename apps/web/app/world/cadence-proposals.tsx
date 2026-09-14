"use client";

// Propuestas en la mesa — una barra por propuesta con las aprobaciones que el
// ledger de la ronda realmente tiene, la marca del quórum y el liderazgo.
//
// El backend ya devuelve `proposals` de mejor a peor: aquí se respeta ese
// orden y el salto de posición se anima con useFlipReorder (FLIP, sin
// librerías, respetando prefers-reduced-motion).

import { useFlipReorder } from "@/app/components/useFlipReorder";
import { isLivePhase, quorumShare, type WorldCadence } from "@/world/cadence";

const VOTE_CHIPS: { key: "approve" | "reject" | "abstain" | "needs_revision"; label: string }[] = [
  { key: "approve", label: "aprobar" },
  { key: "reject", label: "rechazar" },
  { key: "abstain", label: "abstener" },
  { key: "needs_revision", label: "revisar" },
];

function percent(value: number): string {
  return `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%`;
}

export function CadenceProposals({
  cadence,
  status,
}: {
  cadence: WorldCadence | null;
  status: "loading" | "ready" | "unavailable";
}) {
  const proposals = cadence?.proposals ?? [];
  const round = cadence?.round ?? null;
  const flipRef = useFlipReorder<HTMLOListElement>(
    proposals.map((proposal) => proposal.proposal_id).join("|"),
  );
  const quorum = quorumShare(round);
  const eligible = round?.eligible_agents ?? 0;
  const live = Boolean(cadence && cadence.scheduler_enabled && isLivePhase(cadence.phase));

  return (
    <section
      className={`panel-block cadence-proposals-panel ${live ? `cadence-phase-${cadence!.phase}` : "cadence-phase-none"}`}
      aria-label="Propuestas de la ronda en curso"
    >
      <div className="panel-title-row">
        <h2>Propuestas en la mesa</h2>
        <span className="cadence-panel-phase">
          {status === "ready" && cadence ? cadence.phase_label_es : "—"}
        </span>
      </div>

      {status !== "ready" || !cadence ? (
        <p className="empty-state">
          {status === "loading"
            ? "Leyendo las propuestas de la ronda…"
            : "Esta API no publica la cadencia; no hay propuestas que mostrar."}
        </p>
      ) : (
        <>
          <ul className="cadence-vote-chips" aria-label="Votos emitidos en esta ronda">
            {VOTE_CHIPS.map((chip) => (
              <li key={chip.key} className={`cadence-chip cadence-chip-${chip.key}`}>
                <span>{chip.label}</span>
                <strong>{round?.votes[chip.key] ?? 0}</strong>
              </li>
            ))}
          </ul>
          <p className="cadence-quorum-line">
            {round ? (
              <>
                quórum <strong>{round.quorum_count}/{round.quorum_required}</strong>
                {" · "}
                {round.votes.total} voto(s) de {eligible} elegibles
              </>
            ) : (
              "Sin ronda abierta: el quórum se fija cuando la cadencia abre la ventana."
            )}
          </p>

          <ol ref={flipRef} className="cadence-proposal-list">
            {proposals.map((proposal) => {
              const share = Math.min(1, Math.max(0, proposal.approval_share_of_eligible));
              const tooltip = proposal.question
                ? `${proposal.title}\n\n${proposal.question}`
                : proposal.title;
              return (
                <li
                  key={proposal.proposal_id}
                  data-flip-key={proposal.proposal_id}
                  className={[
                    "cadence-proposal",
                    proposal.is_leader ? "is-leader" : "",
                    proposal.is_selected ? "is-selected" : "",
                  ].join(" ")}
                >
                  <div className="cadence-proposal-head">
                    {proposal.is_leader && (
                      <span className="cadence-crown" title="Más aprobaciones de la ronda">
                        👑
                      </span>
                    )}
                    <strong className="cadence-proposal-title" title={tooltip}>
                      {proposal.title}
                    </strong>
                    {proposal.is_selected && (
                      <span className="cadence-selected-badge">Seleccionada</span>
                    )}
                  </div>
                  <p className="cadence-proposal-meta">
                    <span title={proposal.author_agent_id ?? "autor no publicado"}>
                      {proposal.author_name ?? "—"}
                    </span>
                    <span className="cadence-proposal-state">{proposal.state}</span>
                  </p>
                  <div
                    className="cadence-bar"
                    role="img"
                    aria-label={`${proposal.approvals} de ${eligible} agentes elegibles aprobaron`}
                  >
                    <span className="cadence-bar-fill" style={{ width: percent(share) }} />
                    {quorum !== null && (
                      <span
                        className="cadence-bar-quorum"
                        style={{ left: percent(quorum) }}
                        title={`Quórum: ${round?.quorum_required} de ${eligible} elegibles`}
                      />
                    )}
                  </div>
                  <p className="cadence-bar-legend">
                    <strong>{proposal.approvals}</strong>/{eligible || "—"} aprobaciones
                    <span>{proposal.votes_received} voto(s) recibidos</span>
                  </p>
                </li>
              );
            })}
          </ol>

          {proposals.length === 0 && (
            <p className="empty-state">Aún no hay propuestas en esta ventana.</p>
          )}
          <p className="subtle-note">
            Las barras salen de filas de voto del ledger de esta ronda; el consenso
            no es verdad, sólo decide qué reto se publica.
          </p>
        </>
      )}
    </section>
  );
}
