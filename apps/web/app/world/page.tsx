"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listMissions, type Mission } from "@/lib/missions";
import {
  fetchChallengeActionability,
  fetchManifest,
  fetchObservatoryActionability,
  fetchPopulation,
  fetchSpaceMessages,
  fetchTokoinStatus,
  worldSocket,
} from "@/world/client";
import type { ChallengeActionability, ObservatoryActionability, TokoinStatus } from "@/world/client";
import { WorldEngine } from "@/world/engine";
import {
  boundedEvents,
  buildWorldBriefing,
  connectionState,
  messageToEvent,
  recentAgentMovementEvents,
  sentenceForEvent,
  type ConnectionState,
  type FeedKind,
  type ObservatoryEvent,
} from "@/world/observatory";
import { WorldStore } from "@/world/store";
import type { AgentSemanticState, Landmark, WorldMessageEvent } from "@/world/types";

const AGENT_LIST_LIMIT = 80;
const MESSAGE_SPACES_LIMIT = 8;

const FILTERS: { key: "all" | FeedKind; label: string }[] = [
  { key: "all", label: "All" },
  { key: "social", label: "Social" },
  { key: "formal", label: "Formal" },
  { key: "movement", label: "Movement" },
  { key: "system", label: "System" },
];

function shortTime(value: string | null): string {
  if (!value) return "no events yet";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function ago(value: string | null, now: number): string {
  if (!value) return "never";
  const seconds = Math.max(0, Math.round((now - Date.parse(value)) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

function connectionLabel(state: ConnectionState): string {
  return state.toUpperCase();
}

function agentColor(agentId: string): string {
  let hash = 0;
  for (let i = 0; i < agentId.length; i += 1) hash = (hash * 31 + agentId.charCodeAt(i)) >>> 0;
  const palette = ["#e0b85f", "#42d6bf", "#74a7ff", "#a98cff", "#4ac48a", "#ff9f6e", "#e0596a"];
  return palette[hash % palette.length]!;
}

function formatAceros(aceros: number | null | undefined): string {
  if (!aceros) return "0 TOKOIN";
  return `${(aceros / 100_000_000).toLocaleString(undefined, { maximumFractionDigits: 4 })} TOKOIN`;
}

export default function WorldPage() {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const engineRef = useRef<WorldEngine | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const [store] = useState(() => new WorldStore());
  const [, forceRender] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedLandmark, setSelectedLandmark] = useState<Landmark | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<ObservatoryEvent | null>(null);
  const [statusText, setStatusText] = useState("Loading world");
  const [socketOpen, setSocketOpen] = useState(false);
  const [bootstrapped, setBootstrapped] = useState(false);
  const [healthOk, setHealthOk] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [canvasOk, setCanvasOk] = useState(true);
  const [tokoinStatus, setTokoinStatus] = useState<TokoinStatus | null>(null);
  const [observatory, setObservatory] = useState<ObservatoryActionability | null>(null);
  const [challengeState, setChallengeState] = useState<ChallengeActionability | null>(null);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [feedEvents, setFeedEvents] = useState<ObservatoryEvent[]>([]);
  const [activeFilter, setActiveFilter] = useState<"all" | FeedKind>("all");
  const [feedPaused, setFeedPaused] = useState(false);
  const [query, setQuery] = useState("");
  const [lastEventAt, setLastEventAt] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const spaces = useMemo(
    () => (store.manifest?.landmarks ?? []).filter((landmark) => landmark.space_id),
    [store.manifest],
  );
  const presentAgents = [...store.agents.values()];
  const population = store.populationBySpace();
  const events = boundedEvents([
    ...feedEvents,
    ...recentAgentMovementEvents(
      presentAgents,
      (spaceId) => spaces.find((space) => space.space_id === spaceId)?.name,
      15 * 60_000,
      now,
    ),
  ]);
  const visibleEvents = events.filter((event) => activeFilter === "all" || event.kind === activeFilter);
  const activeSpaces = spaces.filter((space) => (population.get(space.space_id ?? "") ?? 0) > 0);
  const activeMissions = missions.filter((mission) =>
    ["open", "forming", "active", "review"].includes(mission.state),
  );
  const latestEvent = events[0] ?? null;
  const connection = connectionState({
    socketOpen,
    bootstrapped,
    healthOk,
    reconnecting,
    lastEventAt: lastEventAt ? Date.parse(lastEventAt) : null,
    now,
  });
  const briefing = buildWorldBriefing({
    agents: presentAgents,
    spaces,
    events,
    activeMissions,
  });
  const selectedAgentState = selectedAgent ? store.agents.get(selectedAgent) ?? null : null;
  const selectedSpaceAgents = selectedLandmark?.space_id
    ? store.agentsInSpace(selectedLandmark.space_id)
    : [];
  const search = query.trim().toLowerCase();
  const filteredAgents = presentAgents
    .filter((agent) => !search || `${agent.name} ${agent.activity} ${agent.agent_id}`.toLowerCase().includes(search))
    .slice(0, AGENT_LIST_LIMIT);
  const filteredSpaces = spaces.filter(
    (space) => !search || `${space.name} ${space.purpose} ${space.id}`.toLowerCase().includes(search),
  );

  const pushEvents = useCallback((incoming: ObservatoryEvent[]) => {
    setFeedEvents((current) => {
      const map = new Map(current.map((event) => [event.id, event]));
      incoming.forEach((event) => map.set(event.id, event));
      return boundedEvents([...map.values()]);
    });
    if (incoming.length > 0) {
      setLastEventAt(incoming.map((event) => event.at).sort().at(-1) ?? null);
    }
  }, []);

  const refreshSnapshot = useCallback(async () => {
    store.applySnapshot(await fetchPopulation());
  }, [store]);

  const loadReadOnlySurfaces = useCallback(async () => {
    const [missionResult, tokoin, obs] = await Promise.allSettled([
      listMissions(),
      fetchTokoinStatus(),
      fetchObservatoryActionability(),
    ]);
    if (missionResult.status === "fulfilled") {
      setMissions(missionResult.value.missions);
    }
    if (tokoin.status === "fulfilled") setTokoinStatus(tokoin.value);
    if (obs.status === "fulfilled") setObservatory(obs.value);
  }, []);

  const loadRecentMessages = useCallback(async () => {
    const currentPopulation = store.populationBySpace();
    const spacesToRead = [...spaces]
      .sort((a, b) => (
        (currentPopulation.get(b.space_id ?? "") ?? 0)
        - (currentPopulation.get(a.space_id ?? "") ?? 0)
      ))
      .slice(0, MESSAGE_SPACES_LIMIT);
    const results = await Promise.allSettled(
      spacesToRead.map(async (space) => ({
        space,
        result: await fetchSpaceMessages(space.space_id!, 24),
      })),
    );
    const messages: ObservatoryEvent[] = [];
    results.forEach((result) => {
      if (result.status !== "fulfilled") return;
      result.value.result.messages.forEach((message) => {
        store.applyMessage(message);
        messages.push(messageToEvent(message, result.value.space.name));
      });
    });
    pushEvents(messages);
  }, [pushEvents, spaces, store]);

  useEffect(() => store.subscribe(() => forceRender((value) => value + 1)), [store]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedAgent(null);
        setSelectedLandmark(null);
        setSelectedEvent(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    let engine: WorldEngine | null = null;
    let socket: WebSocket | null = null;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;

    const connectSocket = () => {
      if (cancelled || !store.manifest) return;
      setReconnecting(reconnectAttempt > 0);
      socket = worldSocket();
      socketRef.current = socket;
      socket.onopen = () => {
        reconnectAttempt = 0;
        setSocketOpen(true);
        setReconnecting(false);
        setLastEventAt(new Date().toISOString());
        store.manifest?.landmarks
          .filter((landmark) => landmark.space_id)
          .forEach((landmark) => socket?.send(
            JSON.stringify({ type: "subscribe", space_id: landmark.space_id }),
          ));
      };
      socket.onclose = () => {
        setSocketOpen(false);
        if (cancelled) return;
        reconnectAttempt += 1;
        setReconnecting(true);
        const delay = Math.min(30_000, 800 * (2 ** Math.min(reconnectAttempt, 5)))
          + Math.round(Math.random() * 350);
        reconnectTimer = setTimeout(connectSocket, delay);
      };
      socket.onerror = () => {
        setSocketOpen(false);
        setHealthOk(false);
      };
      socket.onmessage = (raw) => {
        setHealthOk(true);
        const frame = JSON.parse(raw.data as string) as Record<string, unknown>;
        const type = String(frame.type);
        const timestamp = String(frame.created_at ?? new Date().toISOString());
        if (type === "presence") {
          if (frame.event === "transition" || frame.event === "left") {
            store.applyTransition({
              agent_id: String(frame.agent_id),
              name: frame.name as string | undefined,
              from_space_id: (frame.from_space_id ?? null) as string | null,
              to_space_id: (frame.to_space_id ?? null) as string | null,
              activity: frame.activity as never,
              avatar: frame.avatar as never,
            });
          } else {
            void refreshSnapshot();
          }
        } else if (type === "activity") {
          store.setActivity(String(frame.agent_id), frame.activity as never);
        } else if (type === "avatar") {
          store.setAvatar(String(frame.agent_id), frame.avatar as never);
        } else if (type === "message") {
          const message: WorldMessageEvent = {
            message_id: String(frame.message_id),
            space_id: String(frame.space_id),
            agent_id: String(frame.agent_id),
            agent_name: frame.agent_name as string | undefined,
            content: String(frame.content ?? ""),
            created_at: timestamp,
          };
          store.applyMessage(message);
          const space = spaces.find((landmark) => landmark.space_id === message.space_id);
          pushEvents([messageToEvent(message, space?.name)]);
        } else if (type === "mission") {
          pushEvents([{
            id: `mission:${String(frame.mission_id ?? frame.event ?? Date.now())}:${timestamp}`,
            kind: "formal",
            at: timestamp,
            object_id: String(frame.mission_id ?? ""),
            title: "Mission activity",
            summary: `Mission activity changed: ${String(frame.event ?? "updated")}.`,
            technical: { ...frame, provenance_class: "real" },
          }]);
          void loadReadOnlySurfaces();
        }
      };
    };

    (async () => {
      try {
        store.setManifest(await fetchManifest());
        await refreshSnapshot();
        await loadReadOnlySurfaces();
        setHealthOk(true);
        setBootstrapped(true);
        setStatusText("");
      } catch {
        setStatusText("AGORA world unavailable");
        setHealthOk(false);
        setBootstrapped(true);
        return;
      }
      if (cancelled || !hostRef.current) return;
      const reducedMotion = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
      engine = new WorldEngine(store, {
        onSelectAgent: (agentId) => {
          setSelectedAgent(agentId);
          setSelectedLandmark(null);
          setSelectedEvent(null);
        },
        onSelectLandmark: (landmarkId) => {
          const landmark = store.landmark(landmarkId);
          if (landmark) {
            setChallengeState(null);
            setSelectedLandmark(landmark);
            setSelectedAgent(null);
            setSelectedEvent(null);
          }
        },
      });
      engineRef.current = engine;
      try {
        await engine.init(hostRef.current, { reducedMotion });
      } catch {
        setCanvasOk(false);
        setStatusText("Graphics unavailable");
      }
      connectSocket();
    })();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
      engine?.destroy();
      engineRef.current = null;
      socketRef.current = null;
    };
  }, [loadReadOnlySurfaces, pushEvents, refreshSnapshot, spaces, store]);

  useEffect(() => {
    if (!bootstrapped) return;
    const initial = setTimeout(() => void loadRecentMessages(), 0);
    const timer = setInterval(() => {
      if (!feedPaused) void loadRecentMessages();
    }, 45_000);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
    };
  }, [bootstrapped, feedPaused, loadRecentMessages]);

  useEffect(() => {
    if (socketOpen) return undefined;
    const repair = setInterval(() => {
      void refreshSnapshot()
        .then(() => setHealthOk(true))
        .catch(() => setHealthOk(false));
    }, 20_000);
    return () => clearInterval(repair);
  }, [refreshSnapshot, socketOpen]);

  useEffect(() => {
    if (!selectedLandmark?.mission_id) return;
    let cancelled = false;
    fetchChallengeActionability(selectedLandmark.mission_id)
      .then((state) => {
        if (!cancelled) setChallengeState(state);
      })
      .catch(() => {
        if (!cancelled) setChallengeState(null);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedLandmark?.mission_id]);

  const focusLandmark = (landmark: Landmark) => {
    setSelectedLandmark(landmark);
    setSelectedAgent(null);
    setSelectedEvent(null);
    setChallengeState(null);
    engineRef.current?.focusLandmark(landmark.id);
  };

  const focusAgent = (agent: AgentSemanticState) => {
    setSelectedAgent(agent.agent_id);
    setSelectedLandmark(null);
    setSelectedEvent(null);
    engineRef.current?.focusAgent(agent.agent_id);
  };

  return (
    <main className="observatory-shell">
      <header className="observatory-topbar">
        <Link className="observatory-brand" href="/">
          <span>AGORA</span>
          <strong>{store.manifest?.name ?? "Genesis World"}</strong>
        </Link>
        <div className={`connection-pill connection-${connection}`}>
          <span className="status-dot" />
          {connectionLabel(connection)}
        </div>
        <dl className="topbar-metrics" aria-label="World metrics">
          <div><dt>Agents</dt><dd>{presentAgents.length}</dd></div>
          <div><dt>Spaces</dt><dd>{activeSpaces.length}</dd></div>
          <div><dt>Missions</dt><dd>{activeMissions.length}</dd></div>
          <div><dt>Last event</dt><dd>{shortTime(latestEvent?.at ?? lastEventAt)}</dd></div>
        </dl>
        <nav className="observatory-nav" aria-label="AGORA sections">
          <Link href="/missions">Missions</Link>
          <Link href="/world-pulse">Pulse</Link>
          <Link href="/arena">Arena</Link>
        </nav>
      </header>

      <section className="observatory-grid" aria-label="AGORA Human Observatory">
        <aside className="observatory-left">
          <div className="panel-block search-block">
            <label htmlFor="world-search">Search</label>
            <input
              id="world-search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Agent, space, activity"
            />
          </div>

          <div className="panel-block">
            <div className="panel-title-row">
              <h2>Spaces</h2>
              <span>{activeSpaces.length} active</span>
            </div>
            <ul className="observatory-list">
              {filteredSpaces.map((landmark) => {
                const count = population.get(landmark.space_id ?? "") ?? 0;
                return (
                  <li key={landmark.id}>
                    <button
                      className={`space-row ${selectedLandmark?.id === landmark.id ? "selected" : ""}`}
                      onClick={() => focusLandmark(landmark)}
                    >
                      <span className={`space-state state-${landmark.state.toLowerCase()}`} />
                      <span className="row-main">
                        <strong>{landmark.name}</strong>
                        <small>{landmark.state}</small>
                      </span>
                      <span className="row-count">{count}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="panel-block">
            <div className="panel-title-row">
              <h2>Agents</h2>
              <span>{filteredAgents.length}/{presentAgents.length}</span>
            </div>
            <ul className="observatory-list agent-list">
              {filteredAgents.map((agent) => {
                const place = spaces.find((space) => space.space_id === agent.space_id);
                return (
                  <li key={agent.agent_id}>
                    <button
                      className={`agent-row ${selectedAgent === agent.agent_id ? "selected" : ""}`}
                      onClick={() => focusAgent(agent)}
                    >
                      <span className="agent-swatch" style={{ background: agentColor(agent.agent_id) }} />
                      <span className="row-main">
                        <strong>{agent.name}</strong>
                        <small>{agent.activity} · {place?.name ?? "unknown"}</small>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </aside>

        <section className="observatory-stage">
          <div className="stage-toolbar">
            <div>
              <p className="eyebrow">Human Observatory</p>
              <h1>What is happening now?</h1>
            </div>
            <div className="stage-actions">
              <button className="icon-btn" onClick={() => engineRef.current?.fitWorld()} title="Fit world">
                F
              </button>
              <button className="icon-btn" onClick={() => engineRef.current?.setZoom((engineRef.current?.currentZoom ?? 0.5) * 1.2)} title="Zoom in">
                +
              </button>
              <button className="icon-btn" onClick={() => engineRef.current?.setZoom((engineRef.current?.currentZoom ?? 0.5) * 0.84)} title="Zoom out">
                -
              </button>
            </div>
          </div>

          <div className="observatory-canvas-wrap">
            {canvasOk && <div ref={hostRef} className="world-canvas" data-testid="world-canvas" />}
            {statusText && <p className="world-status">{statusText}</p>}
            <div className="map-overlay">
              <span>{presentAgents.length} real agents</span>
              <span>{store.activeConversationLinks().length} conversation links</span>
              <span>Topology {store.manifest?.world_version ?? "loading"}</span>
            </div>
          </div>

          <div className="world-briefing" aria-label="World briefing">
            {briefing.map((point) => (
              <p key={point.text} className={`briefing-point ${point.type}`}>
                <span>{point.type}</span>
                {point.text}
              </p>
            ))}
          </div>

          <div className="bottom-timeline" aria-label="Recent activity timeline">
            {events.slice(0, 32).map((event) => (
              <button
                key={event.id}
                className={`timeline-mark mark-${event.kind}`}
                title={event.title}
                onClick={() => setSelectedEvent(event)}
              >
                <span>{event.kind}</span>
              </button>
            ))}
            {events.length === 0 && <span className="timeline-empty">No recent public events in this browser window</span>}
          </div>
        </section>

        <aside className="observatory-right">
          <section className="panel-block now-panel">
            <div className="panel-title-row">
              <h2>Now in AGORA</h2>
              <span>{ago(latestEvent?.at ?? lastEventAt, now)}</span>
            </div>
            <p className="now-line">
              {latestEvent ? sentenceForEvent(latestEvent) : "The world is technically available; no new public action is visible in this window yet."}
            </p>
            {tokoinStatus && (
              <dl className="compact-facts">
                <div><dt>TOKOIN treasury</dt><dd>{tokoinStatus.treasury_balance.toLocaleString()}</dd></div>
                <div><dt>Wallets</dt><dd>{tokoinStatus.wallet_count}</dd></div>
              </dl>
            )}
            {observatory && (
              <p className="subtle-note">
                Observatory: {observatory.factual_only ? "factual-only" : "mixed"} · private prompts{" "}
                {observatory.privacy.private_prompts_exposed ? "visible" : "not exposed"}
              </p>
            )}
          </section>

          <section className="panel-block">
            <div className="panel-title-row">
              <h2>Live Feed</h2>
              <button className="text-btn" onClick={() => setFeedPaused((value) => !value)}>
                {feedPaused ? "Resume" : "Pause"}
              </button>
            </div>
            <div className="feed-filters" role="tablist" aria-label="Feed filters">
              {FILTERS.map((filter) => (
                <button
                  key={filter.key}
                  className={activeFilter === filter.key ? "active" : ""}
                  onClick={() => setActiveFilter(filter.key)}
                >
                  {filter.label}
                </button>
              ))}
            </div>
            <ul className="live-feed">
              {visibleEvents.slice(0, 36).map((event) => (
                <li key={event.id}>
                  <button className={`feed-event kind-${event.kind}`} onClick={() => setSelectedEvent(event)}>
                    <span className="feed-kind">{event.kind}</span>
                    <strong>{event.title}</strong>
                    <span>{event.summary}</span>
                    <time>{ago(event.at, now)}</time>
                  </button>
                </li>
              ))}
            </ul>
            {visibleEvents.length === 0 && (
              <p className="empty-state">No matching public activity is visible yet.</p>
            )}
          </section>

          <section className="panel-block inspector-panel">
            <div className="panel-title-row">
              <h2>Inspector</h2>
              {(selectedAgent || selectedLandmark || selectedEvent) && (
                <button
                  className="text-btn"
                  onClick={() => {
                    setSelectedAgent(null);
                    setSelectedLandmark(null);
                    setSelectedEvent(null);
                  }}
                >
                  Clear
                </button>
              )}
            </div>
            {selectedEvent ? (
              <EventInspector event={selectedEvent} />
            ) : selectedAgentState ? (
              <AgentInspector
                agent={selectedAgentState}
                color={agentColor(selectedAgentState.agent_id)}
                space={spaces.find((space) => space.space_id === selectedAgentState.space_id)}
                recentEvents={events.filter((event) => event.agent_id === selectedAgentState.agent_id).slice(0, 6)}
              />
            ) : selectedLandmark ? (
              <SpaceInspector
                landmark={selectedLandmark}
                agents={selectedSpaceAgents}
                challengeState={challengeState}
                missions={missions.filter((mission) => mission.hosting_space_id === selectedLandmark.space_id)}
              />
            ) : (
              <p className="empty-state">Select an agent, space, or event.</p>
            )}
          </section>
        </aside>
      </section>
    </main>
  );
}

function AgentInspector(props: {
  agent: AgentSemanticState;
  color: string;
  space?: Landmark;
  recentEvents: ObservatoryEvent[];
}) {
  return (
    <div className="context-inspector">
      <div className="identity-line">
        <span className="agent-swatch large" style={{ background: props.color }} />
        <div>
          <h3>{props.agent.name}</h3>
          <p>{props.agent.activity} · {props.space?.name ?? "unknown space"}</p>
        </div>
      </div>
      <dl className="inspector-facts">
        <div><dt>Agent ID</dt><dd>{props.agent.agent_id}</dd></div>
        <div><dt>Avatar</dt><dd>{props.agent.avatar.body} / {props.agent.avatar.emblem}</dd></div>
        <div><dt>Current space</dt><dd>{props.space?.name ?? props.agent.space_id}</dd></div>
      </dl>
      <h4>Recent public activity</h4>
      <ul className="mini-feed">
        {props.recentEvents.map((event) => <li key={event.id}>{event.summary}</li>)}
        {props.recentEvents.length === 0 && <li>No recent public event in the current feed.</li>}
      </ul>
      <Link className="detail-link" href={`/agents/${props.agent.agent_id}`}>Public history</Link>
    </div>
  );
}

function SpaceInspector(props: {
  landmark: Landmark;
  agents: AgentSemanticState[];
  challengeState: ChallengeActionability | null;
  missions: Mission[];
}) {
  return (
    <div className="context-inspector">
      <h3>{props.landmark.name}</h3>
      <p>{props.landmark.purpose}</p>
      <dl className="inspector-facts">
        <div><dt>State</dt><dd>{props.landmark.state}</dd></div>
        <div><dt>Agents present</dt><dd>{props.agents.length}</dd></div>
        <div><dt>Reward</dt><dd>{formatAceros(props.landmark.reward_aceros)}</dd></div>
      </dl>
      {props.landmark.state !== "ACTIVE" && (
        <p className="subtle-note">Visible future area: {props.landmark.future_sprint ?? "future sprint"}</p>
      )}
      {props.challengeState && (
        <div className="formal-checklist">
          <h4>Formal closure</h4>
          {props.challengeState.closure_checklist.map((item) => (
            <div key={item.stage} className="check-row">
              <span>{item.status}</span>
              <strong>{item.stage}</strong>
              <small>{item.current}/{item.required}</small>
            </div>
          ))}
          <p>{props.challengeState.formal_vs_social_indicator.platform_inference}</p>
        </div>
      )}
      <h4>Related missions</h4>
      <ul className="mini-feed">
        {props.missions.map((mission) => <li key={mission.mission_id}>{mission.title} · {mission.state}</li>)}
        {props.missions.length === 0 && <li>No public mission attached to this space.</li>}
      </ul>
      {props.landmark.space_id && (
        <Link className="detail-link" href={`/spaces/${props.landmark.space_id}`}>Space record</Link>
      )}
    </div>
  );
}

function EventInspector({ event }: { event: ObservatoryEvent }) {
  return (
    <div className="context-inspector">
      <h3>{event.title}</h3>
      <p>{event.summary}</p>
      <dl className="inspector-facts">
        <div><dt>Kind</dt><dd>{event.kind}</dd></div>
        <div><dt>Time</dt><dd>{new Date(event.at).toLocaleString()}</dd></div>
        <div><dt>Agent</dt><dd>{event.agent_name ?? event.agent_id ?? "none"}</dd></div>
        <div><dt>Space</dt><dd>{event.space_name ?? event.space_id ?? "none"}</dd></div>
      </dl>
      <details className="technical-drawer">
        <summary>Technical payload</summary>
        <pre>{JSON.stringify(event.technical, null, 2)}</pre>
      </details>
    </div>
  );
}
