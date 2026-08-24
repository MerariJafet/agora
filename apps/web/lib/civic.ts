import { getJson } from "./api";

export interface CivicRole {
  role_id: string;
  role: string;
  name: string;
  status: string;
}

export interface SummaryArtifact {
  summary_id: string;
  content: string;
  explicit_uncertainty: string;
  disagreement_group_id: string | null;
  trust: string;
}

export interface CivicFinding {
  finding_id: string;
  finding_type: string;
  severity: string;
  description: string;
  trust: string;
}

export interface ForgeRfc {
  rfc_id: string;
  title: string;
  status: string;
  decision: string | null;
}

export interface CivicDashboard {
  roles: number;
  summaries: number;
  findings: number;
  rfcs: number;
  improvement_proposals: number;
  reputation_events: number;
  single_universal_karma: null;
  truth_score: null;
}

export function civicDashboard(): Promise<CivicDashboard> {
  return getJson<CivicDashboard>("/v1/civic/dashboard");
}

export function listCivicRoles(): Promise<{ roles: CivicRole[] }> {
  return getJson<{ roles: CivicRole[] }>("/v1/civic/roles");
}

export function listSummaries(): Promise<{ summaries: SummaryArtifact[] }> {
  return getJson<{ summaries: SummaryArtifact[] }>("/v1/civic/summaries");
}

export function listFindings(): Promise<{ findings: CivicFinding[] }> {
  return getJson<{ findings: CivicFinding[] }>("/v1/civic/findings");
}

export function listRfcs(): Promise<{ rfcs: ForgeRfc[] }> {
  return getJson<{ rfcs: ForgeRfc[] }>("/v1/forge/rfcs");
}
