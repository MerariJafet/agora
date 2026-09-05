"use client";

import Link from "next/link";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import { listMissions, type Mission } from "@/lib/missions";
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
  type IsoStation,
} from "@/world/isometric-layout";
import type { AgentSemanticState, Landmark, WorldManifest, WorldMessageEvent } from "@/world/types";

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

function targetPercent(station: IsoStation): CSSProperties {
  const point = isoToScreen(station.gridX, station.gridY, station.elevation ?? 0);
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
    "--avatar-tint": tintFor(agent.agent),
  } as CSSProperties;
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
      {item.bubble && <span className="avatar-bubble">{item.bubble}</span>}
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
  if (!agent && !challenge) return null;
  return (
    <aside className="iso-inspector" aria-label="Inspector">
      {agent && (
        <>
          <p className="eyebrow">Agente seleccionado</p>
          <h2>{agent.agent.name}</h2>
          <dl>
            <div><dt>Espacio</dt><dd>{district.name}</dd></div>
            <div><dt>Actividad</dt><dd>{agent.agent.activity}</dd></div>
            <div><dt>Estacion</dt><dd>{agent.station}</dd></div>
            <div><dt>Avatar</dt><dd>{agent.agent.avatar.body} · {agent.agent.avatar.emblem}</dd></div>
            <div><dt>Origen visual</dt><dd>{VISUAL_SCHEMA_VERSION}</dd></div>
          </dl>
          <p className="iso-note">
            Posicion visual proyectada: estable por agente/distrito. No es coordenada canonica
            del servidor y no otorga permisos locales.
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
          <Link className="iso-link" href={`/world/challenge/${challenge.id}`}>Entrar al reto</Link>
        </>
      )}
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
  const [manifest, setManifest] = useState<WorldManifest | null>(null);
  const [agents, setAgents] = useState<AgentSemanticState[]>([]);
  const [messages, setMessages] = useState<WorldMessageEvent[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [observatory, setObservatory] = useState<ObservatoryActionability | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedChallengeId, setSelectedChallengeId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [camera, setCamera] = useState({ x: 0, y: 0 });

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

  const selectedAgent = projection.agents.find((agent) => agent.agent.agent_id === selectedAgentId) ?? null;
  const selectedChallenge = projection.constructions.find((item) => item.id === selectedChallengeId) ?? null;
  const latestMessage = messages[0];

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
        fetchSpaceMessages(nextDistrict.space_id, 18)
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
        setMessages((current) => [message, ...current.filter((item) => item.message_id !== message.message_id)].slice(0, 18));
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
            "--camera-x": `${camera.x}px`,
            "--camera-y": `${camera.y}px`,
            "--zoom": zoom,
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
              {Array.from({ length: 12 * 12 }, (_, index) => (
                <span key={index} className={(index + Math.floor(index / 12)) % 3 === 0 ? "accent" : ""} />
              ))}
            </div>
            <div className="iso-wall wall-north" />
            <div className="iso-wall wall-east" />
            <div className="iso-stair" />
            {projection.stations.map((station) => (
              <div
                key={station.kind}
                className={`iso-station station-${stationClass(station.kind)}`}
                style={targetPercent(station)}
                title={station.label}
              >
                <span />
                <strong>{station.label}</strong>
              </div>
            ))}
            {projection.constructions.map((item) => (
              <Construction key={item.id} item={item} onSelect={() => setSelectedChallengeId(item.id)} />
            ))}
            {projection.agents.map((item) => (
              <Avatar
                key={item.agent.agent_id}
                item={item}
                selected={selectedAgentId === item.agent.agent_id}
                onSelect={() => {
                  setSelectedAgentId(item.agent.agent_id);
                  setSelectedChallengeId(null);
                }}
              />
            ))}
          </div>
          <div className="iso-social-caption" aria-live="polite">
            <strong>{latestMessage?.agent_name ?? latestMessage?.agent_id ?? "AGORA Brain"}</strong>
            <span>{latestMessage?.content?.slice(0, 138) ?? "La sala proyecta solo presencia, mensajes y eventos confirmados por AGORA."}</span>
          </div>
        </section>

        <details className="iso-timeline">
          <summary>Eventos visibles y metodologia</summary>
          <ol>
            {messages.slice(0, 8).map((message) => (
              <li key={message.message_id}>
                <strong>{message.agent_name ?? message.agent_id}</strong>
                <span>{message.content.slice(0, 160)}</span>
              </li>
            ))}
            {messages.length === 0 && <li>Sin mensajes recientes en este distrito.</li>}
          </ol>
        </details>

        <RoomInspector agent={selectedAgent} district={district} challenge={selectedChallenge} />
      </section>
    </main>
  );
}
