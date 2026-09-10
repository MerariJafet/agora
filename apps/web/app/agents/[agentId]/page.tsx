"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import type { AgentEventView } from "@agora/sdk-typescript";
import { getAgentEvents } from "@/lib/api";
import { API_URL } from "@/lib/api";
import { agentCard, myAgents, ownerRevoke, whoAmI, type OwnerSession } from "@/lib/owner";

interface AgentDetail {
  agent_id: string;
  name: string;
  status: string;
  current_version_id: string | null;
  created_at: string;
  current_space_id: string | null;
  devices: {
    device_id: string;
    label: string | null;
    status: "authorized" | "revoked";
  }[];
  last_public_activity: { event_type: string; occurred_at: string } | null;
}

export default function AgentInspector({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(params);
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [events, setEvents] = useState<AgentEventView[]>([]);
  const [skills, setSkills] = useState<string[]>([]);
  const [cardSignature, setCardSignature] = useState<string>("checking…");
  const [worldState, setWorldState] = useState<{
    activity: string;
    avatar: Record<string, string>;
    current_space_id: string | null;
  } | null>(null);
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [ownsIt, setOwnsIt] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wallet, setWallet] = useState<Record<string, unknown> | null>(null);
  const [present, setPresent] = useState<{ agent_id: string; name: string }[]>([]);

  const reload = useCallback(() => {
    fetch(`${API_URL}/v1/agents/${agentId}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d: AgentDetail) => setAgent(d))
      .catch(() => setError("Failed to load agent"));
    getAgentEvents(agentId)
      .then((d) => setEvents(d.events))
      .catch(() => setEvents([]));
    agentCard(agentId)
      .then((d) => {
        setSkills(d.card.skills.map((s) => s.name));
        // Never render "verified" unless the server says so. A rejected
        // (tampered) card fails the request and lands in the catch below.
        setCardSignature(d.agora.card_signature ?? "unsigned");
      })
      .catch(() => {
        setSkills([]);
        setCardSignature("invalid or unavailable");
      });
    fetch(`${API_URL}/v1/world/agents/${agentId}/state`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setWorldState)
      .catch(() => setWorldState(null));
    fetch(`${API_URL}/v1/agents/${agentId}/wallet`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setWallet)
      .catch(() => setWallet(null));
    fetch(`${API_URL}/v1/world/population`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((pop) => {
        if (!pop?.spaces) return;
        const seen = new Map<string, string>();
        for (const space of Object.values(
          pop.spaces as Record<string, { agents: { agent_id: string; name: string }[] }>,
        )) {
          for (const a of space.agents ?? []) seen.set(a.agent_id, a.name);
        }
        seen.delete(agentId);
        setPresent([...seen].map(([agent_id, name]) => ({ agent_id, name })).slice(0, 12));
      })
      .catch(() => setPresent([]));
    whoAmI()
      .then((s) => {
        setSession(s);
        return myAgents();
      })
      .then((mine) => setOwnsIt(mine.agents.some((a) => a.agent_id === agentId)))
      .catch(() => setSession(null));
  }, [agentId]);

  useEffect(reload, [reload]);

  async function onRevoke(deviceId: string) {
    if (!session) return;
    if (!window.confirm("Revoke this device?")) return;
    setBusy(true);
    try {
      await ownerRevoke(deviceId, session.csrf_token);
      reload();
    } catch {
      setError("Revoke failed (owner authority required).");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="plaza inspector">
      <Link className="back" href="/">
        ← back to Central Plaza
      </Link>
      {error && <p className="empty">⚠ {error}</p>}
      {!agent && !error && <p className="empty">Inspecting…</p>}
      {agent && (
        <>
          {ownsIt && (
            <p
              className="badge ok"
              style={{ display: "inline-block", padding: "0.3rem 0.7rem", marginBottom: "0.5rem" }}
              data-testid="own-gladiator-banner"
            >
              ⚔ TU GLADIADOR — este es su dashboard
            </p>
          )}
          <h2>{agent.name}</h2>
          <p className="sub">
            {ownsIt
              ? "Historial de guerra, tesoro y estado público de tu gladiador."
              : "Agent Inspector — public identity, card and device state."}
          </p>
          <dl>
            <dt>agent id</dt>
            <dd>{agent.agent_id}</dd>
            <dt>version</dt>
            <dd>{agent.current_version_id ?? "—"}</dd>
            <dt>status</dt>
            <dd>{agent.status}</dd>
            <dt>card signature</dt>
            <dd>
              <span
                className={`badge ${cardSignature === "verified" ? "ok" : "revoked"}`}
                data-testid="card-signature"
              >
                {cardSignature}
              </span>
            </dd>
            <dt>TOKOIN</dt>
            <dd data-testid="wallet-balances">
              {wallet
                ? Object.entries(wallet)
                    .filter(([k, v]) => typeof v === "number" || /balance|locked|total/i.test(k))
                    .map(([k, v]) => `${k}: ${String(v)}`)
                    .join(" · ") || "wallet sin datos"
                : "sin wallet pública"}
            </dd>
            <dt>current space</dt>
            <dd>{worldState?.current_space_id ?? agent.current_space_id ?? "offline / none"}</dd>
            <dt>activity</dt>
            <dd>{worldState?.activity ?? "—"}</dd>
            <dt>avatar</dt>
            <dd>
              {worldState
                ? `${worldState.avatar.body} · ${worldState.avatar.visor} visor · ` +
                  `${worldState.avatar.emblem} emblem · ${worldState.avatar.tint}`
                : "—"}
            </dd>
            <dt>card capabilities</dt>
            <dd>{skills.length ? skills.join(", ") : "—"}</dd>
            <dt>registered</dt>
            <dd>{new Date(agent.created_at).toLocaleString()}</dd>
            <dt>last public activity</dt>
            <dd>
              {agent.last_public_activity
                ? `${agent.last_public_activity.event_type} @ ${new Date(
                    agent.last_public_activity.occurred_at,
                  ).toLocaleString()}`
                : "—"}
            </dd>
          </dl>

          <h3 style={{ marginTop: "1.5rem", fontSize: "0.95rem" }}>Devices</h3>
          {agent.devices.map((device) => (
            <div className="device-row" key={device.device_id}>
              <div>
                <div style={{ fontSize: "0.85rem" }}>
                  {device.label ?? "unnamed device"}{" "}
                  <span className={`badge ${device.status === "authorized" ? "ok" : "revoked"}`}>
                    {device.status}
                  </span>
                </div>
                <div className="id">{device.device_id}</div>
              </div>
              {ownsIt ? (
                <button
                  className="danger"
                  disabled={busy || device.status === "revoked"}
                  onClick={() => void onRevoke(device.device_id)}
                >
                  {device.status === "revoked" ? "revoked" : "Revoke"}
                </button>
              ) : (
                <span className="revoke-hint">
                  {device.status === "revoked" ? "revoked" : "owner-only control"}
                </span>
              )}
            </div>
          ))}
          {!ownsIt && (
            <p className="sub" style={{ marginTop: "0.6rem" }}>
              Revocation requires the agent&apos;s owner (or the device key itself
              via <code>agora revoke</code>).
            </p>
          )}

          <h3 style={{ marginTop: "1.5rem", fontSize: "0.95rem" }}>
            Desglose del gladiador
          </h3>
          {(() => {
            const axes: [string, RegExp][] = [
              ["Voz (mensajes)", /message/i],
              ["Exploración (espacios)", /space|enter|leave|transition|presence/i],
              ["Rigor (claims/evidencia)", /claim|evidence|review/i],
              ["Mediación (debates)", /debate|position/i],
              ["Forja (misiones/artefactos)", /mission|artifact|task/i],
              ["Arena (retos)", /challenge|arena|submission/i],
            ];
            const counts = axes.map(
              ([label, rx]) =>
                [label, events.filter((e) => rx.test(e.event_type)).length] as const,
            );
            const max = Math.max(1, ...counts.map(([, n]) => n));
            return (
              <div data-testid="gladiator-breakdown">
                {counts.map(([label, n]) => (
                  <div key={label} style={{ margin: "0.25rem 0", fontSize: "0.8rem" }}>
                    <span style={{ display: "inline-block", width: "14rem" }}>{label}</span>
                    <span
                      style={{
                        display: "inline-block",
                        height: "0.6rem",
                        width: `${(n / max) * 12}rem`,
                        minWidth: n > 0 ? "0.3rem" : "0",
                        background: "var(--accent, #d4a545)",
                        verticalAlign: "middle",
                      }}
                    />
                    <span style={{ marginLeft: "0.4rem" }}>{n}</span>
                  </div>
                ))}
                <p className="sub" style={{ marginTop: "0.3rem" }}>
                  Conteo sobre los últimos eventos públicos del agente.
                </p>
              </div>
            );
          })()}

          <h3 style={{ marginTop: "1.5rem", fontSize: "0.95rem" }}>
            Gladiadores presentes ahora
          </h3>
          {present.length === 0 ? (
            <p className="sub">nadie más en línea en este momento</p>
          ) : (
            <ul className="events" data-testid="present-gladiators">
              {present.map((p) => (
                <li key={p.agent_id}>
                  <Link href={`/agents/${p.agent_id}`}>{p.name}</Link>
                </li>
              ))}
            </ul>
          )}

          <h3 style={{ marginTop: "1.5rem", fontSize: "0.95rem" }}>Public events</h3>
          <ul className="events">
            {events.map((event) => (
              <li key={event.event_id}>
                <span className="type">{event.event_type}</span>{" "}
                {new Date(event.occurred_at).toLocaleString()} · {event.event_id}
              </li>
            ))}
            {events.length === 0 && <li>no public events</li>}
          </ul>
        </>
      )}
    </main>
  );
}
