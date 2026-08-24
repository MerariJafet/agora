"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  listModules,
  listWorldBuilderPlots,
  type ModuleView,
  type WorldPlot,
} from "@/lib/modules";

export default function WorldBuilderPage() {
  const [modules, setModules] = useState<ModuleView[]>([]);
  const [plots, setPlots] = useState<WorldPlot[]>([]);

  useEffect(() => {
    listModules().then((r) => setModules(r.modules)).catch(() => setModules([]));
    listWorldBuilderPlots().then((r) => setPlots(r.plots)).catch(() => setPlots([]));
  }, []);

  return (
    <main className="plaza">
      <Link className="back" href="/world">← back to World</Link>
      <h2>Community Frontier</h2>
      <p className="sub">
        Declarative modules, games and buildings move through static analysis,
        review and resource leasing before becoming part of AGORA.
      </p>

      <section className="columns">
        <div>
          <h3 className="col-title">World Plots</h3>
          <ul className="world-list">
            {plots.map((plot) => (
              <li key={plot.plot_id} className="world-place">
                <span className="badge">{plot.runtime_state}</span>
                <span className="place-name">{plot.name}</span>
                <span>{plot.state}</span>
                <span>{plot.module_id ?? "empty"}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className="col-title">Modules</h3>
          <div className="claim-list">
            {modules.map((module) => (
              <article key={module.module_id} className="claim-card">
                <span className="badge">{module.state}</span>
                <h4>{module.name}</h4>
                <p>{module.type}</p>
                <p className="sub">
                  capabilities are platform-scoped, never local device permissions
                </p>
              </article>
            ))}
            {modules.length === 0 && (
              <p className="empty">No modules have passed the pipeline yet.</p>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
