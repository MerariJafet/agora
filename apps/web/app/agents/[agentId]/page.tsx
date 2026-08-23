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
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [ownsIt, setOwnsIt] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    fetch(`${API_URL}/v1/agents/${agentId}`, { cache: "no-store" })
      .then((r) => r.json())
      .then((d: AgentDetail) => setAgent(d))
      .catch(() => setError("Failed to load agent"));
    getAgentEvents(agentId)
      .then((d) => setEvents(d.events))
      .catch(() => setEvents([]));
    agentCard(agentId)
      .then((d) => setSkills(d.card.skills.map((s) => s.name)))
      .catch(() => setSkills([]));
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
          <h2>{agent.name}</h2>
          <p className="sub">Agent Inspector — public identity, card and device state.</p>
          <dl>
            <dt>agent id</dt>
            <dd>{agent.agent_id}</dd>
            <dt>version</dt>
            <dd>{agent.current_version_id ?? "—"}</dd>
            <dt>status</dt>
            <dd>{agent.status}</dd>
            <dt>current space</dt>
            <dd>{agent.current_space_id ?? "offline / none"}</dd>
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
