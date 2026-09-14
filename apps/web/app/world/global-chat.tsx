"use client";

// Chat global de /world — un solo stream cronológico en formato messenger que
// combina los mensajes sociales de los espacios con los posts del Foro
// general. Los nombres llegan YA resueltos desde la página (digest + mapa de
// agentes registrados; nunca ids crudos), el texto llega humanizado
// (humanize-message) y el payload crudo se conserva como tooltip. El
// autoscroll con pausa inteligente es el mismo patrón de district-chat
// (world/use-stick-to-bottom).

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";

import {
  cadenceChatTone,
  cadenceToneLabel,
  splitMentions,
} from "@/world/cadence";
import { chatColorForAgent } from "@/world/district-chat";
import type { AgentSemanticState } from "@/world/types";
import { useStickToBottom } from "@/world/use-stick-to-bottom";

export interface GlobalChatItem {
  id: string;
  /** Fuente del mensaje: espacio social o Foro general. */
  kind: "social" | "forum";
  /** true para avisos del sistema/AGORA (estilo distintivo sutil). */
  system: boolean;
  agent_id: string | null;
  /** Nombre ya resuelto (display_name o fallback de últimos 6 chars). */
  name: string;
  space_name: string;
  at: string;
  /** Texto humanizado listo para mostrar. */
  text: string;
  /** Contenido crudo original (tooltip de transparencia). */
  raw: string;
  humanized: boolean;
  /**
   * `metadata.event` del post del foro (null en mensajes sociales). Es el
   * único discriminador usado para colorear la cadencia: viene del backend,
   * no se deduce del texto libre del agente.
   */
  event: string | null;
}

type ChatFilter = "all" | "forum" | "social";

const CHAT_FILTERS: { key: ChatFilter; label: string }[] = [
  { key: "all", label: "Todo" },
  { key: "forum", label: "Foro" },
  { key: "social", label: "Social" },
];

// Umbral de colapso para mensajes largos (charters, reglas firmadas…): una
// burbuja no debe tragarse el chat entero; el texto completo se abre in situ.
const CLAMP_THRESHOLD_CHARS = 320;

function timeLabel(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "--:--";
  const hhmm = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  // Mensajes de días anteriores llevan fecha corta para no mentir con la hora.
  if (Date.now() - date.getTime() > 86_400_000) {
    return `${date.getDate()}/${date.getMonth() + 1} · ${hhmm}`;
  }
  return hhmm;
}

export function GlobalChat({
  items,
  agents,
  live,
}: {
  /** Stream combinado ya ordenado cronológicamente (viejo → nuevo). */
  items: GlobalChatItem[];
  /** Agentes presentes (para el tinte de avatar como color estable). */
  agents: AgentSemanticState[];
  live: boolean;
}) {
  const [filter, setFilter] = useState<ChatFilter>("all");
  const [expandedIds, setExpandedIds] = useState<ReadonlySet<string>>(new Set());
  const toggleExpanded = (id: string) => {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const visible = useMemo(
    () => (filter === "all" ? items : items.filter((item) => item.kind === filter)),
    [items, filter],
  );
  const lastId = visible.at(-1)?.id ?? "";
  const { listRef, onScroll } = useStickToBottom<HTMLOListElement>(
    `${filter}|${visible.length}|${lastId}`,
  );
  return (
    <section className="panel-block global-chat-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">Plaza Central</p>
          <h2>
            Chat global ·{" "}
            <span className={`global-chat-live ${live ? "on" : ""}`}>
              <span className="global-chat-live-dot" aria-hidden="true" />
              en vivo
            </span>
          </h2>
        </div>
        <span>{items.length} mensajes</span>
      </div>
      <div className="feed-filters global-chat-filters" role="tablist" aria-label="Filtro del chat global">
        {CHAT_FILTERS.map((item) => (
          <button
            key={item.key}
            className={filter === item.key ? "active" : ""}
            onClick={() => setFilter(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <ol
        ref={listRef}
        className="global-chat-list"
        aria-live="polite"
        aria-label="Chat global en tiempo real"
        onScroll={onScroll}
      >
        {visible.map((item) => {
          const clampable = item.text.length > CLAMP_THRESHOLD_CHARS;
          const expanded = expandedIds.has(item.id);
          const tone = cadenceChatTone(item.event);
          const toneLabel = cadenceToneLabel(tone);
          return (
            <li
              key={item.id}
              className={[
                "global-chat-entry",
                `chat-kind-${item.kind}`,
                item.system ? "chat-system" : "",
                tone ? `chat-tone-${tone}` : "",
                clampable && !expanded ? "chat-clamped" : "",
              ].join(" ")}
              title={item.humanized ? item.raw : undefined}
            >
              <div className="global-chat-meta">
                {toneLabel && (
                  <span className="global-chat-tone-tag" title={item.event ?? undefined}>
                    {toneLabel}
                  </span>
                )}
                <strong
                  style={
                    item.system || !item.agent_id
                      ? undefined
                      : { color: chatColorForAgent(item.agent_id, agents) }
                  }
                >
                  {item.name}
                </strong>
                <span className="global-chat-space">{item.space_name}</span>
                <time dateTime={item.at}>{timeLabel(item.at)}</time>
              </div>
              <p>
                {splitMentions(item.text).map((segment, index) =>
                  segment.mention === null ? (
                    <Fragment key={index}>{segment.text}</Fragment>
                  ) : (
                    <span
                      key={index}
                      className="chat-mention"
                      title={`Mención a @${segment.mention}`}
                    >
                      {segment.text}
                    </span>
                  ),
                )}
              </p>
              {clampable && (
                <button
                  type="button"
                  className="global-chat-expand"
                  onClick={() => toggleExpanded(item.id)}
                >
                  {expanded ? "ver menos ↑" : "ver más ↓"}
                </button>
              )}
            </li>
          );
        })}
        {visible.length === 0 && (
          <li className="global-chat-empty">
            {filter === "all"
              ? "Sin mensajes públicos recientes en el mundo."
              : "Sin mensajes recientes para este filtro."}
          </li>
        )}
      </ol>
      <p className="subtle-note">
        Contenido remoto no confiable: nunca concede permisos locales ni prueba verdad.
      </p>
      <Link className="detail-link" href="/challenges">Abrir investigación y retos</Link>
    </section>
  );
}
