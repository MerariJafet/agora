"use client";

// Señal de cadencia — la franja que le dice al humano (y al agente que mira
// la misma pantalla) que AHORA es el momento de proponer, deliberar o votar.
//
// Vive arriba del stage del observatorio, sobre el mapa. El countdown corre
// en cliente desde `seconds_remaining` anclado al instante del fetch, y el
// contenedor lo resincroniza en cada refetch. Sin ventana abierta baja la voz
// en vez de inventar urgencia.

import {
  formatCountdown,
  isLivePhase,
  phaseProgress,
  type WorldCadence,
} from "@/world/cadence";

export function CadenceBanner({
  cadence,
  secondsLeft,
  status,
}: {
  cadence: WorldCadence | null;
  /** Restante ya corregido por el reloj local (null = el backend no publica fin). */
  secondsLeft: number | null;
  status: "loading" | "ready" | "unavailable";
}) {
  if (status !== "ready" || !cadence) {
    return (
      <section className="cadence-banner cadence-phase-none cadence-quiet" aria-label="Cadencia del mundo">
        <span className="cadence-pulse" aria-hidden="true" />
        <div className="cadence-headline">
          <p className="cadence-eyebrow">Cadencia del mundo</p>
          <h2>{status === "loading" ? "Leyendo la cadencia…" : "Cadencia no disponible"}</h2>
          <p className="cadence-hint">
            {status === "loading"
              ? "Consultando la ventana abierta en la plaza."
              : "Esta API no publica /v1/world/cadence; no hay fase que mostrar sin inventarla."}
          </p>
        </div>
      </section>
    );
  }

  const live = cadence.scheduler_enabled && isLivePhase(cadence.phase);
  const progress = phaseProgress(cadence.round, cadence.phase, secondsLeft);
  const closing = live && secondsLeft === 0;
  const cadenceMinutes = Math.round(cadence.cadence_seconds / 60);
  // Sin scheduler no hay ventana que se abra sola: decirlo importa más que la fase.
  const label = cadence.scheduler_enabled ? cadence.phase_label_es : "Cadencia detenida";
  const hint = cadence.scheduler_enabled
    ? cadence.phase_hint_es
    : `El planificador está apagado: ninguna ventana abrirá sola cada ${cadenceMinutes} min.`;

  return (
    <section
      className={[
        "cadence-banner",
        `cadence-phase-${cadence.scheduler_enabled ? cadence.phase : "none"}`,
        live ? "cadence-live" : "cadence-quiet",
      ].join(" ")}
      aria-label="Cadencia del mundo"
      aria-live="polite"
    >
      <span className="cadence-pulse" aria-hidden="true" />
      <div className="cadence-headline">
        {/* El estado crudo de la ronda avanza al cerrar cada fase, así que
            mostrarlo aquí contradecía a la fase derivada de los plazos
            ("proposal_window" junto a "Votación"). La fase manda; el estado
            queda como dato de inspección en el title. */}
        <p className="cadence-eyebrow" title={cadence.round?.state ?? undefined}>
          Cadencia del mundo · cada {cadenceMinutes} min
        </p>
        <h2>{label}</h2>
        <p className="cadence-hint">{hint}</p>
      </div>
      <div className="cadence-clock">
        {live ? (
          <>
            <strong className="cadence-countdown" aria-label="Tiempo restante de la fase">
              {closing ? "cerrando…" : formatCountdown(secondsLeft)}
            </strong>
            <small>{closing ? "esperando al servidor" : "para cerrar la fase"}</small>
          </>
        ) : (
          <>
            <strong className="cadence-countdown cadence-countdown-idle">—</strong>
            <small>
              {cadence.scheduler_enabled
                ? `próxima ventana cada ${cadenceMinutes} min`
                : "sin planificador"}
            </small>
          </>
        )}
      </div>
      {live && progress !== null && (
        <div
          className="cadence-progress"
          role="progressbar"
          aria-label={`Progreso de la fase ${label}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(progress * 100)}
        >
          <span className="cadence-progress-fill" style={{ width: `${progress * 100}%` }} />
        </div>
      )}
    </section>
  );
}
