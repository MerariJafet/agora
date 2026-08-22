"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import type { AgentDetailView, AgentEventView } from "@agora/sdk-typescript";
import { getAgent, getAgentEvents, revokeDevice } from "@/lib/api";

export default function AgentInspector({
  params,
}: {
  params: Promise<{ agentId: string }>;
}) {
  const { agentId } = use(params);
  const [agent, setAgent] = useState<AgentDetailView | null>(null);
  const [events, setEvents] = useState<AgentEventView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    getAgent(agentId)
      .then(setAgent)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Failed to load agent"),
      );
    getAgentEvents(agentId)
      .then((data) => setEvents(data.events))
      .catch(() => setEvents([]));
  }, [agentId]);

  useEffect(reload, [reload]);

  async function onRevoke(deviceId: string) {
    if (!window.confirm("Revoke this device? Its sessions stop working immediately.")) return;
    setBusy(true);
    try {
      await revokeDevice(deviceId);
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revoke failed");
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
          <p className="sub">Agent Inspector — public identity and device state.</p>
          <dl>
            <dt>agent id</dt>
            <dd>{agent.agent_id}</dd>
            <dt>version</dt>
            <dd>{agent.current_version_id ?? "—"}</dd>
            <dt>status</dt>
            <dd>{agent.status}</dd>
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
              <button
                className="danger"
                disabled={busy || device.status === "revoked"}
                onClick={() => void onRevoke(device.device_id)}
              >
                {device.status === "revoked" ? "revoked" : "Revoke"}
              </button>
            </div>
          ))}

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
