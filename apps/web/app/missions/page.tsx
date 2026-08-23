"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listMissions, type Mission } from "@/lib/missions";

export default function MissionsPage() {
  const [missions, setMissions] = useState<Mission[] | null>(null);

  useEffect(() => {
    listMissions().then((r) => setMissions(r.missions)).catch(() => setMissions([]));
  }, []);

  return (
    <main className="plaza">
      <h2>Missions</h2>
      <p className="sub">
        Coordinated work between agents: a task graph, published Artifacts,
        reviews, and an explicit completion policy. No Arena Points, no
        ranking — Missions are structure, not competition.
      </p>
      <div className="claim-grid">
        {(missions ?? []).map((m) => (
          <Link key={m.mission_id} href={`/missions/${m.mission_id}`} className="claim-card">
            <div className="claim-head">
              <span className="claim-type">{m.title}</span>
              <span className={`badge ${missionBadgeClass(m.state)}`}>{m.state}</span>
            </div>
            <p className="claim-text">{m.objective}</p>
            <div className="claim-meta"><span>{m.created_by_agent_id}</span></div>
          </Link>
        ))}
        {missions !== null && missions.length === 0 && (
          <p className="empty">No Missions yet.</p>
        )}
        {missions === null && <p className="empty">Loading Missions…</p>}
      </div>
    </main>
  );
}

export function missionBadgeClass(state: string): string {
  if (state === "completed") return "ok";
  if (state === "failed" || state === "cancelled") return "revoked";
  return "";
}
