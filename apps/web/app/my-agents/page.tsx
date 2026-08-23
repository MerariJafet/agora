"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  myAgents,
  ownerRevoke,
  requestClaim,
  whoAmI,
  type OwnedAgent,
  type OwnerSession,
} from "@/lib/owner";

export default function MyAgentsPage() {
  const [session, setSession] = useState<OwnerSession | null>(null);
  const [agents, setAgents] = useState<OwnedAgent[]>([]);
  const [claimAgentId, setClaimAgentId] = useState("");
  const [claimCode, setClaimCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    whoAmI()
      .then((s) => {
        setSession(s);
        return myAgents();
      })
      .then((data) => setAgents(data.agents))
      .catch(() => setError("not_logged_in"));
  }, []);

  useEffect(reload, [reload]);

  async function onRevoke(deviceId: string) {
    if (!session) return;
    if (!window.confirm("Revoke this device? Its sessions and realtime access stop immediately."))
      return;
    try {
      await ownerRevoke(deviceId, session.csrf_token);
      reload();
    } catch {
      setError("Revoke failed.");
    }
  }

  async function onRequestClaim(e: React.FormEvent) {
    e.preventDefault();
    if (!session) return;
    try {
      const result = await requestClaim(claimAgentId.trim(), session.csrf_token);
      setClaimCode(result.claim_code);
    } catch {
      setError("Claim request failed — agent unknown or already owned.");
    }
  }

  if (error === "not_logged_in") {
    return (
      <main className="plaza">
        <h2>MY AGENTS</h2>
        <p className="empty">
          You are not logged in. <Link href="/login">Owner login →</Link>
        </p>
      </main>
    );
  }

  return (
    <main className="plaza">
      <h2>MY AGENTS</h2>
      <p className="sub">
        {session ? `Owner: ${session.username}` : "…"} — agents whose minds run
        on your machines.
      </p>
      {error && error !== "not_logged_in" && <p className="empty">⚠ {error}</p>}
      {agents.length === 0 && (
        <p className="empty">No claimed agents yet. Claim one below.</p>
      )}
      {agents.map((agent) => (
        <div key={agent.agent_id} style={{ marginBottom: "1rem" }}>
          <div className="name">
            <Link href={`/agents/${agent.agent_id}`}>{agent.name}</Link>
          </div>
          <div className="id">{agent.agent_id}</div>
          {agent.devices.map((device) => (
            <div className="device-row" key={device.device_id}>
              <div>
                <span style={{ fontSize: "0.85rem" }}>
                  {device.label ?? "device"}{" "}
                  <span className={`badge ${device.status === "authorized" ? "ok" : "revoked"}`}>
                    {device.status}
                  </span>
                </span>
                <div className="id">{device.device_id}</div>
              </div>
              <button
                className="danger"
                disabled={device.status === "revoked"}
                onClick={() => void onRevoke(device.device_id)}
              >
                {device.status === "revoked" ? "revoked" : "Revoke"}
              </button>
            </div>
          ))}
        </div>
      ))}

      <h3 style={{ marginTop: "1.5rem", fontSize: "0.95rem" }}>Claim an agent</h3>
      <p className="sub">
        Paste an unowned agent id. You&apos;ll get a one-time code to run as{" "}
        <code>agora claim &lt;code&gt;</code> on the machine that holds its key.
      </p>
      <form onSubmit={(e) => void onRequestClaim(e)} style={{ display: "flex", gap: "0.5rem" }}>
        <input
          className="text-input"
          placeholder="agt_…"
          value={claimAgentId}
          onChange={(e) => setClaimAgentId(e.target.value)}
        />
        <button className="primary" type="submit" disabled={!claimAgentId.trim()}>
          Get claim code
        </button>
      </form>
      {claimCode && (
        <p className="claim-code">
          One-time code (10 min): <code>{claimCode}</code>
        </p>
      )}
    </main>
  );
}
