import { getJson } from "./api";

export interface ModuleView {
  module_id: string;
  name: string;
  type: string;
  state: string;
  current_version_id: string | null;
  rollback_version_id: string | null;
}

export interface WorldPlot {
  plot_id: string;
  slug: string;
  name: string;
  state: string;
  runtime_state: string;
  module_id: string | null;
  active_lease_id: string | null;
}

export function listModules(): Promise<{ modules: ModuleView[] }> {
  return getJson<{ modules: ModuleView[] }>("/v1/modules");
}

export function listWorldBuilderPlots(): Promise<{ plots: WorldPlot[] }> {
  return getJson<{ plots: WorldPlot[] }>("/v1/world-builder/plots");
}
