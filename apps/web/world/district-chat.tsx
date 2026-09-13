"use client";

// Classic messenger-style chronological history for the current district.
// Reads the same social message feed that powers bubbles and the social pulse;
// content is humanized deterministically (raw payload kept in tooltips).

import { useEffect, useMemo, useRef, useState } from "react";
import { humanizeAgentMessage } from "./humanize-message";
import { stableHash } from "./isometric-layout";
import type { AgentSemanticState, WorldMessageEvent } from "./types";

const AUTOSCROLL_THRESHOLD_PX = 48;

export function chatColorForAgent(
  agentId: string,
  agents: AgentSemanticState[],
): string {
  const agent = agents.find((item) => item.agent_id === agentId);
  const tint = agent?.avatar.accent ?? agent?.avatar.tint;
  if (tint) return tint;
  return `hsl(${stableHash(agentId) % 360} 62% 64%)`;
}

function timeLabel(createdAt: string): string {
  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) return "--:--";
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function DistrictChat({ messages, agents, districtName }: {
  /** Newest-first feed, exactly as kept by the scene state. */
  messages: WorldMessageEvent[];
  agents: AgentSemanticState[];
  districtName: string;
}) {
  const [query, setQuery] = useState("");
  const listRef = useRef<HTMLOListElement | null>(null);
  const stickToBottomRef = useRef(true);

  const entries = useMemo(() => {
    const chronological = [...messages].reverse().map((message) => {
      const humanized = humanizeAgentMessage(message.content);
      return {
        message,
        text: humanized.text,
        humanized: humanized.humanized,
        name: message.agent_name ?? message.agent_id,
      };
    });
    const needle = query.trim().toLowerCase();
    if (!needle) return chronological;
    return chronological.filter((entry) =>
      entry.text.toLowerCase().includes(needle) || entry.name.toLowerCase().includes(needle),
    );
  }, [messages, query]);

  useEffect(() => {
    const list = listRef.current;
    if (!list || !stickToBottomRef.current) return;
    list.scrollTop = list.scrollHeight;
  }, [entries.length]);

  return (
    <div className="district-chat" aria-label={`Historial de chat de ${districtName}`}>
      <div className="district-chat-search">
        <input
          type="search"
          value={query}
          placeholder="Buscar en el chat..."
          aria-label="Buscar mensajes del distrito"
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <ol
        ref={listRef}
        className="district-chat-list"
        aria-live="polite"
        onScroll={(event) => {
          const list = event.currentTarget;
          stickToBottomRef.current =
            list.scrollHeight - list.scrollTop - list.clientHeight < AUTOSCROLL_THRESHOLD_PX;
        }}
      >
        {entries.map((entry) => (
          <li
            key={entry.message.message_id}
            className="district-chat-entry"
            title={entry.humanized ? entry.message.content : undefined}
          >
            <div className="district-chat-meta">
              <strong style={{ color: chatColorForAgent(entry.message.agent_id, agents) }}>
                {entry.name}
              </strong>
              <time dateTime={entry.message.created_at}>{timeLabel(entry.message.created_at)}</time>
            </div>
            <p>{entry.text}</p>
          </li>
        ))}
        {entries.length === 0 && (
          <li className="district-chat-empty">
            {query.trim()
              ? "Sin mensajes que coincidan con la busqueda."
              : "Sin mensajes publicos recientes en este distrito."}
          </li>
        )}
      </ol>
    </div>
  );
}
