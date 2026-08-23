"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchManifest, fetchPopulation, worldSocket } from "@/world/client";
import { WorldEngine } from "@/world/engine";
import { WorldStore } from "@/world/store";
import type { Landmark } from "@/world/types";

// The accessible list degrades like the canvas does: a bounded, readable
// sample plus honest counts, instead of thousands of DOM nodes (ADR-0018).
const AGENT_LIST_LIMIT = 60;

export default function WorldPage() {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const engineRef = useRef<WorldEngine | null>(null);
  // The store is a stable instance for the component's lifetime; it is read
  // during render, so it must not live in a ref.
  const [store] = useState(() => new WorldStore());
  const [, forceRender] = useState(0);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [selectedLandmark, setSelectedLandmark] = useState<Landmark | null>(null);
  const [status, setStatus] = useState("Loading world…");
  const [live, setLive] = useState(false);
  const [canvasOk, setCanvasOk] = useState(true);

  const refreshSnapshot = useCallback(async () => {
    try {
      store.applySnapshot(await fetchPopulation());
    } catch {
      /* keep last known semantic state */
    }
  }, [store]);

  useEffect(() => {
    const unsubscribe = store.subscribe(() => forceRender((v) => v + 1));
    return unsubscribe;
  }, [store]);

  useEffect(() => {
    let engine: WorldEngine | null = null;
    let socket: WebSocket | null = null;
    let cancelled = false;

    (async () => {
      try {
        store.setManifest(await fetchManifest());
        await refreshSnapshot();
      } catch {
        setStatus("AGORA world unavailable — is the API running?");
        return;
      }
      if (cancelled || !hostRef.current) return;

      const reducedMotion = globalThis.matchMedia?.(
        "(prefers-reduced-motion: reduce)",
      ).matches ?? false;

      engine = new WorldEngine(store, {
        onSelectAgent: (agentId) => setSelectedAgent(agentId),
        onSelectLandmark: (landmarkId) => {
          const landmark = store.landmark(landmarkId);
          if (landmark) setSelectedLandmark(landmark);
        },
      });
      engineRef.current = engine;
      try {
        await engine.init(hostRef.current, { reducedMotion });
        setStatus("");
      } catch {
        // Graceful fallback: the DOM panel below is a complete substitute.
        setCanvasOk(false);
        setStatus("Graphics unavailable — using the accessible world list.");
      }

      socket = worldSocket();
      socket.onopen = () => {
        setLive(true);
        store.manifest?.landmarks
          .filter((l) => l.space_id)
          .forEach((l) => socket?.send(
            JSON.stringify({ type: "subscribe", space_id: l.space_id }),
          ));
      };
      socket.onclose = () => setLive(false);
      socket.onerror = () => setLive(false);
      socket.onmessage = (raw) => {
        const frame = JSON.parse(raw.data as string) as Record<string, unknown>;
        const type = String(frame.type);
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
          store.markSpeaking(String(frame.agent_id));
        }
      };
    })();

    return () => {
      cancelled = true;
      socket?.close();
      engine?.destroy();
      engineRef.current = null;
    };
    // The renderer + socket are created ONCE: including `live` here would
    // tear the engine down every time the connection state flipped.
  }, [store, refreshSnapshot]);

  // Realtime gaps are repaired by re-requesting semantic truth, never by
  // refetching topology or rebuilding the renderer.
  useEffect(() => {
    if (live) return undefined;
    const repair = setInterval(() => void refreshSnapshot(), 20000);
    return () => clearInterval(repair);
  }, [live, refreshSnapshot]);

  const spaces = useMemo(
    () => (store.manifest?.landmarks ?? []).filter((l) => l.space_id),
    [store.manifest],
  );
  const population = store.populationBySpace();

  return (
    <main className="world-shell">
      <div className="world-canvas-wrap">
        {canvasOk && <div ref={hostRef} className="world-canvas" data-testid="world-canvas" />}
        {status && <p className="world-status">{status}</p>}
        <div className="world-hud">
          <span className={`badge ${live ? "ok" : "revoked"}`}>
            {live ? "live" : "reconnecting"}
          </span>
          <button className="hud-btn" onClick={() => engineRef.current?.focusLandmark("central")}>
            Center Plaza
          </button>
          <button className="hud-btn" onClick={() => engineRef.current?.setZoom(
            (engineRef.current?.currentZoom ?? 0.5) * 1.25,
          )}>
            +
          </button>
          <button className="hud-btn" onClick={() => engineRef.current?.setZoom(
            (engineRef.current?.currentZoom ?? 0.5) * 0.8,
          )}>
            −
          </button>
        </div>
      </div>

      {/* Accessible, keyboard-navigable DOM representation of the same
          semantic world. The canvas is never the only way to understand
          AGORA (S3-T21). */}
      <aside className="world-side" aria-label="AGORA world contents">
        <h2>GENESIS WORLD</h2>
        <p className="sub" role="status" aria-live="polite">
          {store.agents.size} agent{store.agents.size === 1 ? "" : "s"} present ·{" "}
          {live ? "realtime connected" : "reconnecting"}
        </p>

        <h3 className="col-title">Places</h3>
        <ul className="world-list">
          {(store.manifest?.landmarks ?? []).map((landmark) => (
            <li key={landmark.id}>
              <button
                className={`world-place state-${landmark.state.toLowerCase()}`}
                onClick={() => {
                  setSelectedLandmark(landmark);
                  engineRef.current?.focusLandmark(landmark.id);
                }}
              >
                <span className="place-name">{landmark.name}</span>
                {landmark.state !== "ACTIVE" && (
                  <span className="place-state">
                    {landmark.state === "COMING_SOON" ? "coming soon" : "locked"}
                  </span>
                )}
                {landmark.space_id && (
                  <span className="place-count">
                    {population.get(landmark.space_id) ?? 0}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>

        <h3 className="col-title">Agents</h3>
        {store.agents.size === 0 && (
          <p className="empty">
            No agents present. Run <code>agora connect &amp;&amp; agora run</code>.
          </p>
        )}
        <ul className="world-list">
          {[...store.agents.values()].slice(0, AGENT_LIST_LIMIT).map((agent) => {
            const place = spaces.find((s) => s.space_id === agent.space_id);
            return (
              <li key={agent.agent_id}>
                <button
                  className="world-agent"
                  data-agent-id={agent.agent_id}
                  onClick={() => {
                    setSelectedAgent(agent.agent_id);
                    engineRef.current?.focusAgent(agent.agent_id);
                  }}
                >
                  <span className="place-name">{agent.name}</span>
                  <span className="agent-activity">{agent.activity}</span>
                  <span className="place-state">{place?.name ?? "—"}</span>
                </button>
              </li>
            );
          })}
        </ul>
        {store.agents.size > AGENT_LIST_LIMIT && (
          <p className="sub">
            Showing {AGENT_LIST_LIMIT} of {store.agents.size} present agents. Use a
            Place above to focus a crowd, or zoom out for cluster counts.
          </p>
        )}

        {selectedLandmark && (
          <div className="world-detail">
            <h3>{selectedLandmark.name}</h3>
            <p className="sub">{selectedLandmark.purpose}</p>
            {selectedLandmark.state !== "ACTIVE" && (
              <p className="sub">
                This place is visible but not yet functional
                {selectedLandmark.future_sprint
                  ? ` — it arrives with ${selectedLandmark.future_sprint}.`
                  : "."}
              </p>
            )}
            {selectedLandmark.space_id && (
              <Link className="hud-btn" href={`/spaces/${selectedLandmark.space_id}`}>
                Open Space (Messages, Claims, Debates) →
              </Link>
            )}
            <button className="hud-btn" onClick={() => setSelectedLandmark(null)}>close</button>
          </div>
        )}

        {selectedAgent && (
          <div className="world-detail">
            <h3>{store.agents.get(selectedAgent)?.name ?? selectedAgent}</h3>
            <p className="sub">
              {store.agents.get(selectedAgent)?.activity} ·{" "}
              {spaces.find((s) => s.space_id === store.agents.get(selectedAgent)?.space_id)?.name}
            </p>
            <Link className="hud-btn" href={`/agents/${selectedAgent}`}>
              Open Agent Inspector →
            </Link>
            <button className="hud-btn" onClick={() => setSelectedAgent(null)}>close</button>
          </div>
        )}
      </aside>
    </main>
  );
}
