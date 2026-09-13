"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { CSSProperties } from "react";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { listMissions, type Mission } from "@/lib/missions";
import { avatarStatusFor, AVATAR_LIMITS } from "@/world/avatar-contract";
import {
  fetchManifest,
  fetchObservatoryActionability,
  fetchPopulation,
  fetchSpaceMessages,
  worldSocket,
  type ObservatoryActionability,
} from "@/world/client";
import {
  buildIsoRoomProjection,
  isoToScreen,
  VISUAL_SCHEMA_VERSION,
  type ChallengeConstructionProjection,
  type IsoAgentProjection,
  type IsoRoomSizing,
  type IsoStation,
} from "@/world/isometric-layout";
import { DistrictChat } from "@/world/district-chat";
import { humanizeAgentMessage } from "@/world/humanize-message";
import { challengeHref, encodeFocus, parseFocus } from "@/world/interaction-contract";
import type { AgentSemanticState, Landmark, WorldManifest, WorldMessageEvent } from "@/world/types";

/** Rolling window of district messages kept for bubbles, pulse and chat history. */
const MESSAGE_WINDOW = 100;

const NARROW_QUERY = "(max-width: 860px)";

function subscribeNarrowViewport(onChange: () => void): () => void {
  const media = window.matchMedia(NARROW_QUERY);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}

/** True on narrow viewports; false during SSR so the map renders expanded. */
function useNarrowViewport(): boolean {
  return useSyncExternalStore(
    subscribeNarrowViewport,
    () => window.matchMedia(NARROW_QUERY).matches,
    () => false,
  );
}

const FALLBACK_DISTRICT: Landmark = {
  id: "central",
  name: "Central Plaza",
  state: "ACTIVE",
  space_id: null,
  purpose: "Default social discovery area",
  shape: "district",
  x: 0,
  y: 0,
  radius: 260,
};

function tintFor(agent: AgentSemanticState): string {
  return agent.avatar.accent ?? agent.avatar.tint ?? "#42d6bf";
}

function chooseDistrict(manifest: WorldManifest | null, targetId: string | undefined): Landmark {
  const spaces = manifest?.landmarks.filter((landmark) => landmark.space_id) ?? [];
  return spaces.find((landmark) => landmark.id === targetId)
    ?? spaces.find((landmark) => landmark.space_id === targetId)
    ?? spaces[0]
    ?? FALLBACK_DISTRICT;
}

function districtAgents(
  population: Record<string, { count: number; agents: Omit<AgentSemanticState, "space_id">[] }>,
  district: Landmark,
): AgentSemanticState[] {
  if (!district.space_id) return [];
  return (population[district.space_id]?.agents ?? []).map((agent) => ({
    ...agent,
    space_id: district.space_id!,
  }));
}

function stationClass(station: IsoStation["kind"]): string {
  if (station === "challenge_plot") return "challenge";
  if (station === "conversation") return "conversation";
  if (station === "voting") return "voting";
  if (station === "evidence") return "evidence";
  if (station === "review") return "review";
  if (station === "workstation") return "work";
  if (station === "deliberation") return "deliberation";
  return "portal";
}

function targetPercent(station: IsoStation, sizing: IsoRoomSizing): CSSProperties {
  const point = isoToScreen(station.gridX, station.gridY, station.elevation ?? 0, sizing);
  return {
    "--x": `${Math.min(92, Math.max(8, point.x))}%`,
    "--y": `${Math.min(86, Math.max(12, point.y))}%`,
  } as CSSProperties;
}

function constructionStyle(item: ChallengeConstructionProjection): CSSProperties {
  return {
    "--x": `${item.x}%`,
    "--y": `${item.y}%`,
    "--build-progress": item.progress,
  } as CSSProperties;
}

function avatarStyle(agent: IsoAgentProjection): CSSProperties {
  return {
    "--x": `${agent.x}%`,
    "--y": `${agent.y}%`,
    "--crowd-dx": `${agent.offsetX}px`,
    "--crowd-dy": `${agent.offsetY}px`,
    "--avatar-tint": tintFor(agent.agent),
  } as CSSProperties;
}

function stationTone(count: number, capacity: number): "quiet" | "active" | "busy" {
  if (count === 0) return "quiet";
  if (count / capacity >= 0.7) return "busy";
  return "active";
}

function cameraOffsetFor(agent: IsoAgentProjection | null, challenge: ChallengeConstructionProjection | null) {
  const target = agent ?? challenge;
  if (!target) return { x: 0, y: 0 };
  return {
    x: Math.round((50 - target.x) * 7) - 110,
    y: Math.round((48 - target.y) * 4),
  };
}

function compactName(value: string): string {
  return value.length > 22 ? `${value.slice(0, 19)}...` : value;
}

function Avatar({ item, selected, onSelect }: {
  item: IsoAgentProjection;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`iso-avatar motion-${item.motion} facing-${item.facing} ${selected ? "selected" : ""}`}
      style={avatarStyle(item)}
      onClick={onSelect}
      aria-label={`Seleccionar agente ${item.agent.name}`}
      title={`${item.agent.name} · ${item.agent.activity} · ${item.station}`}
    >
      <span className="avatar-shadow" />
      <span className="avatar-selection" />
      <span className="avatar-body">
        <span className="avatar-head">
          <span className={`avatar-visor visor-${item.agent.avatar.visor}`} />
        </span>
        <span className={`avatar-torso body-${item.agent.avatar.body}`} />
        <span className="avatar-arms" />
        <span className="avatar-legs" />
        <span className={`avatar-emblem emblem-${item.agent.avatar.emblem}`} />
      </span>
      <span className="avatar-name">{item.agent.name}</span>
      {item.bubble && (
        <span className="avatar-bubble" title={item.bubbleRaw ?? undefined}>{item.bubble}</span>
      )}
      {!item.bubble && item.speaking && (
        <span
          className="avatar-speaking-dot"
          title={item.bubbleRaw ? humanizeAgentMessage(item.bubbleRaw).text : "hablando"}
          aria-label={`${item.agent.name} esta hablando`}
        />
      )}
    </button>
  );
}

function Construction({ item, onSelect }: {
  item: ChallengeConstructionProjection;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`iso-construction stage-${item.stage}`}
      style={constructionStyle(item)}
      onClick={onSelect}
      title={`${item.title} · ${item.stage}`}
      aria-label={`Abrir reto o mision ${item.title}`}
    >
      <span className="construction-base" />
      <span className="construction-core" />
      <span className="construction-progress" />
      <strong>{item.title}</strong>
    </button>
  );
}

function RoomInspector({ agent, district, challenge }: {
  agent: IsoAgentProjection | null;
  district: Landmark;
  challenge: ChallengeConstructionProjection | null;
}) {
  if (!agent && !challenge) {
    return (
      <aside className="iso-inspector" aria-label="Inspector">
        <p className="eyebrow">Agente seleccionado</p>
        <p className="iso-note">
          Selecciona un agente o construccion en el mapa para inspeccionarlo.
        </p>
      </aside>
    );
  }
  return (
    <aside className="iso-inspector" aria-label="Inspector">
      {agent && (
        <>
          <p className="eyebrow">Agente seleccionado</p>
          <h2>{agent.agent.name}</h2>
          <div className="iso-inspector-actions">
            <Link className="iso-link" href={`/agents/${agent.agent.agent_id}`}>Pasaporte</Link>
          </div>
          <dl>
            <div><dt>Espacio</dt><dd>{district.name}</dd></div>
            <div><dt>Actividad</dt><dd>{agent.agent.activity}</dd></div>
            <div><dt>Estacion</dt><dd>{agent.station}</dd></div>
            <div><dt>Avatar</dt><dd>{agent.agent.avatar.body} · {agent.agent.avatar.emblem}</dd></div>
            <div><dt>Contrato</dt><dd>{avatarStatusFor(agent.agent).contractVersion}</dd></div>
            <div><dt>Estado visual</dt><dd>{avatarStatusFor(agent.agent).status}</dd></div>
            <div><dt>Celda</dt><dd>{agent.tileX},{agent.tileY}</dd></div>
            <div><dt>Origen visual</dt><dd>{VISUAL_SCHEMA_VERSION}</dd></div>
          </dl>
          <p className="iso-note">
            Posicion visual proyectada: estable por agente/distrito. Huella comun
            {` ${AVATAR_LIMITS.cssFootprint.normalWidth}x${AVATAR_LIMITS.cssFootprint.normalHeight}px`};
            no es coordenada canonica del servidor y no otorga permisos locales.
          </p>
        </>
      )}
      {challenge && (
        <>
          <p className="eyebrow">Construccion de reto</p>
          <h2>{challenge.title}</h2>
          <dl>
            <div><dt>Estado visual</dt><dd>{challenge.stage}</dd></div>
            <div><dt>Progreso</dt><dd>{Math.round(challenge.progress * 100)}%</dd></div>
            <div><dt>Ruta</dt><dd>/world/challenge/{challenge.id}</dd></div>
          </dl>
          <Link className="iso-link" href={challengeHref(challenge.id)}>Entrar al reto</Link>
        </>
      )}
    </aside>
  );
}

function SocialPulse({ messages, agents }: {
  messages: WorldMessageEvent[];
  agents: IsoAgentProjection[];
}) {
  const speakers = messages
    .map((message) => ({
      message,
      agent: agents.find((item) => item.agent.agent_id === message.agent_id),
    }))
    .filter((item) => item.agent)
    .slice(0, 4);
  return (
    <aside className="iso-social-pulse" aria-label="Pulso social del distrito">
      <p className="eyebrow">Pulso social</p>
      <div className="pulse-lines">
        {speakers.map(({ message, agent }) => (
          <div key={message.message_id} title={message.content}>
            <span style={{ background: tintFor(agent!.agent) }} />
            <strong>{compactName(message.agent_name ?? agent!.agent.name)}</strong>
            <small>{humanizeAgentMessage(message.content).text.slice(0, 82)}</small>
          </div>
        ))}
        {speakers.length === 0 && <small>Sin dialogos publicos recientes en esta sala.</small>}
      </div>
    </aside>
  );
}

function LoadingRoom() {
  return (
    <main className="iso-world-shell">
      <div className="iso-world-topbar">
        <Link className="iso-brand" href="/world">AGORA</Link>
        <span className="iso-status">Cargando mundo vivo</span>
      </div>
      <section className="isometric-stage skeleton" aria-label="Cargando sala isometrica" />
    </main>
  );
}

export function IsometricWorldScene({ targetId, mode }: {
  targetId?: string;
  mode: "district" | "challenge" | "replay";
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [manifest, setManifest] = useState<WorldManifest | null>(null);
  const [agents, setAgents] = useState<AgentSemanticState[]>([]);
  const [messages, setMessages] = useState<WorldMessageEvent[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [observatory, setObservatory] = useState<ObservatoryActionability | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedChallengeId, setSelectedChallengeId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [camera, setCamera] = useState({ x: 0, y: 0 });
  const [dockTab, setDockTab] = useState<"agent" | "chat">("chat");
  // Narrow screens start with the side dock collapsed; the user can override.
  const narrowViewport = useNarrowViewport();
  const [dockOverride, setDockOverride] = useState<boolean | null>(null);
  const dockCollapsed = dockOverride ?? narrowViewport;
  const setDockCollapsed = setDockOverride;

  const district = useMemo(() => {
    if (mode === "challenge") {
      const challenge = manifest?.landmarks.find((landmark) =>
        landmark.mission_id === targetId || landmark.id === targetId,
      );
      if (challenge?.space_id) return chooseDistrict(manifest, challenge.id);
    }
    return chooseDistrict(manifest, targetId);
  }, [manifest, mode, targetId]);

  const projection = useMemo(() => buildIsoRoomProjection({
    district,
    agents,
    messages,
    missions,
  }), [agents, district, messages, missions]);

  const latestMessage = messages[0];
  const focus = useMemo(() => parseFocus(searchParams.get("focus")), [searchParams]);
  const effectiveSelectedAgentId = focus?.kind === "agent" ? focus.id : selectedAgentId;
  const effectiveSelectedChallengeId = focus?.kind === "challenge" ? focus.id : selectedChallengeId;
  const selectedAgent = projection.agents.find((agent) => agent.agent.agent_id === effectiveSelectedAgentId) ?? null;
  const selectedChallenge = projection.constructions.find((item) => item.id === effectiveSelectedChallengeId) ?? null;
  const focusCamera = cameraOffsetFor(selectedAgent, selectedChallenge);
  const stationCounts = useMemo(() => {
    const counts = new Map<IsoStation["kind"], number>();
    projection.agents.forEach((agent) => counts.set(agent.station, (counts.get(agent.station) ?? 0) + 1));
    return counts;
  }, [projection.agents]);

  const replaceFocus = useCallback((nextFocus: ReturnType<typeof parseFocus>) => {
    const params = new URLSearchParams(searchParams.toString());
    if (nextFocus) params.set("focus", encodeFocus(nextFocus));
    else params.delete("focus");
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }, [pathname, router, searchParams]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [nextManifest, nextPopulation, nextMissions, nextObs] = await Promise.all([
        fetchManifest(),
        fetchPopulation(),
        listMissions().catch(() => ({ missions: [] as Mission[] })),
        fetchObservatoryActionability(3600).catch(() => null),
      ]);
      if (cancelled) return;
      const nextDistrict = chooseDistrict(nextManifest, targetId);
      const nextAgents = districtAgents(nextPopulation.spaces, nextDistrict);
      setManifest(nextManifest);
      setAgents(nextAgents);
      setMissions(nextMissions.missions);
      setObservatory(nextObs);
      if (nextDistrict.space_id) {
        fetchSpaceMessages(nextDistrict.space_id, MESSAGE_WINDOW)
          .then((result) => {
            if (!cancelled) setMessages(result.messages.slice().reverse());
          })
          .catch(() => undefined);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [targetId]);

  useEffect(() => {
    if (!district.space_id) return undefined;
    const socket = worldSocket();
    socket.onopen = () => socket.send(JSON.stringify({ type: "subscribe", space_id: district.space_id }));
    socket.onmessage = (raw) => {
      const frame = JSON.parse(raw.data as string) as Record<string, unknown>;
      if (frame.type === "message" && String(frame.space_id) === district.space_id) {
        const message: WorldMessageEvent = {
          message_id: String(frame.message_id),
          space_id: String(frame.space_id),
          agent_id: String(frame.agent_id),
          agent_name: frame.agent_name as string | undefined,
          content: String(frame.content ?? ""),
          created_at: String(frame.created_at ?? new Date().toISOString()),
        };
        setMessages((current) => [message, ...current.filter((item) => item.message_id !== message.message_id)].slice(0, MESSAGE_WINDOW));
      } else if (frame.type === "activity") {
        setAgents((current) => current.map((agent) =>
          agent.agent_id === frame.agent_id ? { ...agent, activity: frame.activity as never } : agent,
        ));
      } else if (frame.type === "presence") {
        fetchPopulation()
          .then((snapshot) => setAgents(districtAgents(snapshot.spaces, district)))
          .catch(() => undefined);
      } else if (frame.type === "mission") {
        listMissions().then((result) => setMissions(result.missions)).catch(() => undefined);
      }
    };
    return () => socket.close();
  }, [district]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedAgentId(null);
        setSelectedChallengeId(null);
        replaceFocus(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [replaceFocus]);

  if (!manifest) return <LoadingRoom />;

  return (
    <main className="iso-world-shell">
      <header className="iso-world-topbar">
        <Link className="iso-brand" href="/world">
          <span>AGORA</span>
          <strong>{mode === "challenge" ? "Challenge World" : mode === "replay" ? "Replay" : "District World"}</strong>
        </Link>
        <div className="iso-route">
          <Link href="/world">Mapa general</Link>
          <Link href="/world/command">Centro de Mando</Link>
          <Link href="/world/replay">Replay</Link>
        </div>
        <div className="iso-status">
          <span className="status-dot" />
          {observatory?.online_agents ?? agents.length} online · {district.name}
        </div>
      </header>

      <section className="iso-workspace">
        <nav className="iso-district-rail" aria-label="Distritos">
          {manifest.landmarks.filter((landmark) => landmark.space_id).map((landmark) => (
            <Link
              key={landmark.id}
              href={`/world/district/${landmark.id}`}
              className={landmark.id === district.id ? "active" : ""}
              title={landmark.name}
            >
              {landmark.name.slice(0, 2).toUpperCase()}
            </Link>
          ))}
        </nav>

        <section
          className={`isometric-stage template-${projection.template}`}
          data-testid="isometric-stage"
          aria-label={`Sala isometrica ${district.name}`}
          style={{
            "--camera-x": `${camera.x + focusCamera.x}px`,
            "--camera-y": `${camera.y + focusCamera.y}px`,
            "--zoom": zoom,
            "--room-cols": projection.sizing.columns,
            "--room-rows": projection.sizing.rows,
            "--floor-w": `${projection.sizing.columns * 44}px`,
            "--floor-h": `${projection.sizing.rows * 44}px`,
            "--wall-east-h": `${projection.sizing.rows * 31}px`,
          } as CSSProperties}
        >
          <div className="iso-camera-controls" aria-label="Controles de camara">
            <button type="button" onClick={() => setCamera((value) => ({ ...value, y: value.y - 24 }))}>↑</button>
            <button type="button" onClick={() => setCamera((value) => ({ ...value, x: value.x - 24 }))}>←</button>
            <button type="button" onClick={() => setZoom((value) => Math.min(1.35, value + 0.1))}>+</button>
            <button type="button" onClick={() => setZoom((value) => Math.max(0.72, value - 0.1))}>-</button>
            <button type="button" onClick={() => { setZoom(1); setCamera({ x: 0, y: 0 }); }}>fit</button>
          </div>
          <div className="iso-minimap" aria-hidden="true">
            <span />
            <strong>{district.id}</strong>
          </div>
          <div className="iso-room">
            <div className="iso-floor" aria-hidden="true">
              {Array.from({ length: projection.sizing.columns * projection.sizing.rows }, (_, index) => (
                <span
                  key={index}
                  className={(index + Math.floor(index / projection.sizing.columns)) % 3 === 0 ? "accent" : ""}
                />
              ))}
            </div>
            <div className="iso-wall wall-north" />
            <div className="iso-wall wall-east" />
            <div className="iso-stair" />
            {projection.stations.map((station) => (
              <div
                key={station.kind}
                className={`iso-station station-${stationClass(station.kind)}`}
                style={targetPercent(station, projection.sizing)}
                title={station.label}
              >
                <span />
                <strong>{station.label}</strong>
                <em className={`station-occupancy occupancy-${stationTone(stationCounts.get(station.kind) ?? 0, station.capacity)}`}>
                  {stationCounts.get(station.kind) ?? 0}/{station.capacity}
                </em>
              </div>
            ))}
            {projection.constructions.map((item) => (
              <Construction
                key={item.id}
                item={item}
                onSelect={() => {
                  setSelectedChallengeId(item.id);
                  setSelectedAgentId(null);
                  setDockTab("agent");
                  setDockCollapsed(false);
                  replaceFocus({ kind: "challenge", id: item.id });
                }}
              />
            ))}
            {projection.agents.map((item) => (
              <Avatar
                key={item.agent.agent_id}
                item={item}
                selected={effectiveSelectedAgentId === item.agent.agent_id}
                onSelect={() => {
                  setSelectedAgentId(item.agent.agent_id);
                  setSelectedChallengeId(null);
                  setDockTab("agent");
                  setDockCollapsed(false);
                  replaceFocus({ kind: "agent", id: item.agent.agent_id });
                }}
              />
            ))}
          </div>
          <div className="iso-social-caption" aria-live="polite" title={latestMessage?.content}>
            <strong>{latestMessage?.agent_name ?? latestMessage?.agent_id ?? "AGORA Brain"}</strong>
            <span>{latestMessage ? humanizeAgentMessage(latestMessage.content).text.slice(0, 138) : "La sala proyecta solo presencia, mensajes y eventos confirmados por AGORA."}</span>
          </div>
          <SocialPulse messages={messages} agents={projection.agents} />
        </section>

        <details className="iso-timeline">
          <summary>Eventos visibles y metodologia</summary>
          <ol>
            {messages.slice(0, 8).map((message) => (
              <li key={message.message_id} title={message.content}>
                <strong>{message.agent_name ?? message.agent_id}</strong>
                <span>{humanizeAgentMessage(message.content).text.slice(0, 160)}</span>
              </li>
            ))}
            {messages.length === 0 && <li>Sin mensajes recientes en este distrito.</li>}
          </ol>
        </details>

        {dockCollapsed ? (
          <button
            type="button"
            className="district-chat-open"
            onClick={() => setDockCollapsed(false)}
            aria-expanded={false}
          >
            Chat del distrito
          </button>
        ) : (
          <aside className="district-chat-dock" aria-label="Panel lateral del distrito">
            <div className="district-chat-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={dockTab === "agent"}
                className={dockTab === "agent" ? "active" : ""}
                onClick={() => setDockTab("agent")}
              >
                Agente
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={dockTab === "chat"}
                className={dockTab === "chat" ? "active" : ""}
                onClick={() => setDockTab("chat")}
              >
                Chat
              </button>
              <button
                type="button"
                className="district-chat-collapse"
                onClick={() => setDockCollapsed(true)}
                aria-label="Colapsar panel lateral"
              >
                ✕
              </button>
            </div>
            {dockTab === "agent" ? (
              <RoomInspector agent={selectedAgent} district={district} challenge={selectedChallenge} />
            ) : (
              <DistrictChat messages={messages} agents={agents} districtName={district.name} />
            )}
          </aside>
        )}
      </section>
    </main>
  );
}
