"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  listKnowledgeSources,
  listWorldPulseEvents,
  type KnowledgeSource,
  type WorldPulseEvent,
} from "@/lib/knowledge";

export default function WorldPulsePage() {
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [events, setEvents] = useState<WorldPulseEvent[]>([]);

  useEffect(() => {
    listKnowledgeSources().then((r) => setSources(r.sources)).catch(() => setSources([]));
    listWorldPulseEvents().then((r) => setEvents(r.events)).catch(() => setEvents([]));
  }, []);

  return (
    <main className="plaza">
      <Link className="back" href="/world">← back to World</Link>
      <h2>World Pulse</h2>
      <p className="sub">
        Public-source snapshots, freshness contracts and clustered events.
        Freshness is source-defined; AGORA does not turn consensus into truth.
      </p>

      <section className="columns">
        <div>
          <h3 className="col-title">Clustered Events</h3>
          <div className="claim-list">
            {events.map((event) => (
              <article key={event.pulse_event_id} className="claim-card">
                <span className="badge">{event.freshness_contract}</span>
                <h4>{event.title}</h4>
                <p>{event.summary}</p>
                <p className="sub">
                  {event.source_count} source(s) · snapshot {event.latest_snapshot_id}
                </p>
              </article>
            ))}
            {events.length === 0 && (
              <p className="empty">No clustered public-source events yet.</p>
            )}
          </div>
        </div>

        <div>
          <h3 className="col-title">Adapter Registry</h3>
          <ul className="world-list">
            {sources.map((source) => (
              <li key={source.source_id} className="world-place">
                <span className="badge">{source.freshness_contract}</span>
                <span className="place-name">{source.name}</span>
                <span>{source.domain}</span>
                <span>{source.allowed_hosts.join(", ")}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}
