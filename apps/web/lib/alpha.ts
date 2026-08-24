import { getJson } from "./api";

export interface AlphaReadiness {
  status: "GO" | "NO_GO";
  checks: Record<string, boolean>;
  open_high_or_critical_moderation: number;
  pending_outbox: number;
}

export interface AlphaCosts {
  counts: Record<string, number>;
  agora_cost_units: Record<string, number>;
  owner_inference_cost: string;
  real_charges_enabled: boolean;
}

export interface AlphaDashboard {
  readiness: AlphaReadiness;
  costs: AlphaCosts;
  counts: Record<string, number>;
  runbooks: Record<string, string[]>;
  boundaries_reviewed: string[];
}

export interface ModerationReport {
  report_id: string;
  target_type: string;
  target_id: string;
  reason: string;
  severity: string;
  status: string;
  created_at: string;
}

export interface FeatureFlag {
  flag_id: string;
  key: string;
  enabled: boolean;
  risk_level: string;
  description: string;
}

export function alphaDashboard(): Promise<AlphaDashboard> {
  return getJson<AlphaDashboard>("/v1/alpha/dashboard");
}

export function listModerationReports(): Promise<{ reports: ModerationReport[] }> {
  return getJson<{ reports: ModerationReport[] }>("/v1/moderation/reports?limit=20");
}

export function listFeatureFlags(): Promise<{ feature_flags: FeatureFlag[] }> {
  return getJson<{ feature_flags: FeatureFlag[] }>("/v1/alpha/feature-flags");
}

export function alphaCompatibility(): Promise<{
  a2a: { sdk: string; validated: boolean; scope: string };
  mcp: { sdk: string; validated: boolean; scope: string };
  no_external_credentials_required: boolean;
}> {
  return getJson("/v1/alpha/compatibility");
}
