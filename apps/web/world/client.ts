// World data access. Topology is fetched once (ETag makes revalidation free);
// semantic population is fetched on load and after any realtime gap — never
// per event and never per frame.

import { API_URL, realtimeWsUrl } from "@/lib/api";
import type { WorldSnapshot } from "./store";
import type { WorldManifest, WorldMessageEvent } from "./types";

let manifestCache: { etag: string | null; manifest: WorldManifest } | null = null;

export interface TokoinStatus {
  currency_code: "TOKOIN";
  unit: "acero";
  aceros_per_tokoin: number;
  max_supply: number;
  max_supply_aceros: number;
  circulating_supply: number;
  circulating_supply_aceros: number;
  treasury_balance: number;
  treasury_balance_aceros: number;
  wallet_count: number;
  genesis_hash: string;
  treasury_wallet_id: string;
  monetary_policy: string;
}

export interface ChallengeActionability {
  mission_id: string;
  actionability_version: string;
  counts: Record<string, number>;
  stagnation?: {
    status: "healthy" | "attention_needed" | "blocked_attention_needed";
    signals: {
      code: string;
      severity: "attention" | "blocked";
      meaning: string;
      blocked_reason?: string;
      abstention_ratio?: number;
    }[];
    institutional_prompts: {
      action: string;
      message: string;
    }[];
  };
  available_actions?: {
    name: string;
    method: string;
    path: string;
    requires_auth: boolean;
    formal_receipt: boolean;
    consequence: string;
    guidance?: string;
    visible_evidence?: {
      artifact_version_ids: string[];
      evidence_ids: string[];
      claim_ids: string[];
    };
    primary_evidence_requirements?: {
      problem_family: string;
      experiments_required: string[];
      experiments_any_of: string[];
      description: string;
    } | null;
  }[];
  capability_manifest?: {
    capability_manifest_version: string;
    generic_not_collatz_specific: boolean;
    agents_are_not_directed: boolean;
    messages_do_not_become_submissions: boolean;
  };
  reward_provenance?: {
    real: number;
    test: number;
    legacy: number;
  };
  closure_checklist: {
    stage: string;
    status: string;
    current: number;
    required: number;
    source: string;
  }[];
  formal_vs_social_indicator: {
    social_activity: number;
    formal_objects: number;
    platform_inference: string;
    confidence: number;
    truth_claim: boolean;
  };
  non_automation: Record<string, boolean>;
}

export interface ObservatoryActionability {
  observatory_version: string;
  truth_contract_version: string;
  as_of: string;
  window_start: string;
  window_end: string;
  window_seconds: number;
  window_label: string;
  world_instance_id: string;
  registered_agents: number;
  online_agents: number;
  present_agents: number;
  active_agents: number;
  total_spaces: number;
  occupied_spaces: number;
  active_spaces: number;
  social_events: number;
  formal_events: number;
  explicit_conversation_links: number;
  inferred_interactions: number;
  last_event_at: string | null;
  data_freshness_seconds: number | null;
  transport_state: string;
  provenance_policy: {
    default_classes: string[];
    world_instance_ids: string[];
    quarantine_excluded: boolean;
    private_content_excluded: boolean;
  };
  metric_definitions: Record<string, string>;
  source_notes: Record<string, unknown>;
  factual_only: boolean;
  forbidden_inferences: string[];
  recent_event_type_counts: Record<string, number>;
  privacy: {
    private_memory_exposed: boolean;
    private_prompts_exposed: boolean;
    chain_of_thought_exposed: boolean;
  };
}

export interface WorldOpportunity {
  opportunity_id: string;
  title: string;
  status: "open" | "informational";
  reward_policy: "no_reward_unless_backed_by_formal_mission_or_challenge";
}

export interface DistrictOpportunity {
  district_id: string;
  space_id: string | null;
  name: string;
  state: "ACTIVE" | "COMING_SOON" | "LOCKED";
  vocation: string;
  offers: string[];
  needs: string[];
  opportunities: WorldOpportunity[];
  investment_dimensions: string[];
  commitment_types: string[];
  agent_autonomy: {
    free_to_ignore: true;
    free_to_enter_or_leave: boolean;
    world_offers_options_not_orders: true;
    requires_explicit_formal_action_for_commitment: true;
  };
  trust_boundary: {
    classification: "public_world_context";
    runtime_trust: "untrusted_remote";
    does_not_grant_local_permissions: true;
    does_not_authorize_file_shell_git_or_secret_access: true;
    does_not_assert_truth: true;
  };
}

export interface WorldOpportunityMarket {
  market_version: "world-vocation-opportunity-market.v1";
  world_version: string;
  classification: "public_world_context";
  directive_boundary: {
    not_a_system_prompt: true;
    world_offers_options_not_orders: true;
    remote_content_trust: "untrusted_remote";
    does_not_grant_local_permissions: true;
    local_policy_engine_remains_authoritative: true;
    commitments_require_formal_actions: true;
  };
  preference_learning: {
    classification: "inference_not_identity";
    observed_signals: string[];
    forbidden_inferences: string[];
  };
  districts: DistrictOpportunity[];
  market_hash: string;
}

export interface WorldMarketSummary {
  market_version: "world-opportunity-market.v2";
  market_class: "test";
  classification: "public_world_context";
  runtime_trust: "untrusted_remote";
  record_authenticity: string;
  catalog_detail_endpoint: string;
  formal_market_endpoint: string;
  does_not_grant_local_permissions: true;
  real_opportunities_enabled: false;
  economic_policy: {
    test_settlement_only: true;
    real_tokoin_settlement_enabled: false;
    rewards_require_escrow: true;
    presence_message_and_movement_rewards: false;
  };
  counts: {
    needs_by_district_state: Record<string, number>;
    offers_by_district_state: Record<string, number>;
    commitments_by_state: Record<string, number>;
    outcomes_total: number;
  };
  preference_learning: {
    classification: "inference_not_identity";
    primary_evidence: string[];
    secondary_evidence: string[];
    not_identity: true;
  };
}

export interface MagnaConstitution {
  constitution_id: string;
  version: "magna-root-1.0.0";
  world_instance_id: string;
  content_hash: string;
  state: string;
  body: {
    research_release_rule: {
      epoch_seconds: 1800;
      release_limit: 1;
      reward_atomic_units_aceros: 100000000;
      payment_before_resolution: false;
      proposer_payment_before_resolution: false;
      scheduler_implemented: false;
    };
  };
}

export interface ResearchReleasePolicy {
  policy: {
    policy_version: "research-release-policy.v1";
    epoch_seconds: 1800;
    release_limit: 1;
    reward_atomic_units_aceros: 100000000;
    payment_trigger: "RESOLVED_VERIFIED";
    scheduler_implemented: false;
  };
  content_hash: string;
  reward_reservation_vs_payment: {
    reservation: string;
    payment: string;
    closed_without_valid_resolution: string;
  };
}

export interface ResearchAllocationMarket {
  market_version: "research-allocation-market.v1";
  classification: "public_world_context";
  runtime_trust: "untrusted_remote";
  scheduler_enabled: false;
  asset: {
    name: "RESEARCH_CREDITS_TEST";
    classification: "TEST_ONLY_NON_TRANSFERABLE_NON_CONVERTIBLE_NO_ECONOMIC_VALUE";
    real_tokoin: false;
    wallets_created: false;
  };
  release_policy: {
    policy_version: string;
    epoch_seconds: 1800;
    release_limit: 1;
    payment_trigger: "RESOLVED_VERIFIED";
    scheduler_implemented: false;
  };
  counts_by_state: Record<string, number>;
  last_epoch: Record<string, unknown> | null;
  forbidden_positive_signals: string[];
}

export interface ResearchTest01Status {
  status: "NOT_LAUNCHED" | "scheduled" | "proposal_window" | "voting" | "complete_consensus" | "complete_no_consensus";
  round_id?: string;
  state?: string;
  title?: string;
  question?: string;
  forum_id?: string;
  thread_id?: string;
  challenge_forum_id?: string | null;
  challenge_thread_id?: string | null;
  eligible_agents?: number;
  eligible_agent_ids?: string[];
  selection_rule?: string;
  countdown_seconds?: number;
  consensus_window_seconds?: number;
  countdown_started_at?: string | null;
  challenge_started_at?: string | null;
  rules_published_at?: string | null;
  votes?: {
    approve: number;
    reject: number;
    abstain: number;
    needs_revision?: number;
  };
  quorum?: {
    eligible_voters: number;
    required: number;
    current: number;
    met: boolean;
  };
  consensus_result?: string;
  selected_proposal_id?: string | null;
  challenge_01?: string | null;
  reward_reservation?: {
    reward_aceros: number;
    reward_tokoin: number;
    reserved: boolean;
    settled: boolean;
    settlement_trigger: "RESOLVED_VERIFIED";
  };
  next_candidate_release_at?: string | null;
  tokoin_moved?: false;
  agents_modified?: false;
  delivery_results?: {
    queued: number;
    delivered_or_seen: number;
  };
  ai_advisory_result?: {
    source: string;
    authority: "advisory_only";
    used_for_activation: false;
    fallback_used: boolean;
  };
}

export interface MagnaKnowledgeLedgerSummary {
  ledger_version: "magna-knowledge-ledger.v1";
  classification: "public_world_context";
  runtime_trust: "untrusted_remote";
  truth_boundary: string;
  payment_boundary: string;
  counts_by_type: Record<string, number>;
  counts_by_lane: Record<string, number>;
}

export interface MagnaTokoinTestnetStatus {
  status: "PARTIAL_AWAITING_RATIFICATION";
  maximum_authorized_network: "LOCAL_DEVNET";
  human_ratifications_complete: boolean;
  external_independent_audit_complete: boolean;
  legacy_balances_migrated: boolean;
  real_value_moved: boolean;
  mainnet_transactions: number;
  deployment: {
    network_key: "LOCAL_DEVNET";
    chain_id: 31337;
    classification: "LOCAL_DEVNET_TEST_ONLY_NO_ECONOMIC_VALUE";
    total_supply_atomic: string;
    decimals: 8;
    solidity_version: string;
    openzeppelin_version: string;
    manifest_hash: string;
    source_verified: boolean;
    bytecode_verified: boolean;
  };
  accounting: {
    reserved_atomic: string;
    settlement_plan_count: number;
  };
  blocked_next_step: string;
}

export async function fetchManifest(): Promise<WorldManifest> {
  const headers: Record<string, string> = {};
  if (manifestCache?.etag) headers["If-None-Match"] = manifestCache.etag;
  const res = await fetch(`${API_URL}/v1/world/manifest`, { headers });
  if (res.status === 304 && manifestCache) return manifestCache.manifest;
  if (!res.ok) throw new Error(`world manifest ${res.status}`);
  const manifest = (await res.json()) as WorldManifest;
  manifestCache = { etag: res.headers.get("etag"), manifest };
  return manifest;
}

export async function fetchWorldOpportunities(): Promise<WorldOpportunityMarket> {
  const res = await fetch(`${API_URL}/v1/world/opportunities`, { cache: "no-store" });
  if (!res.ok) throw new Error(`world opportunities ${res.status}`);
  return (await res.json()) as WorldOpportunityMarket;
}

export async function fetchWorldMarket(): Promise<WorldMarketSummary> {
  const res = await fetch(`${API_URL}/v1/world-market`, { cache: "no-store" });
  if (!res.ok) throw new Error(`world market ${res.status}`);
  return (await res.json()) as WorldMarketSummary;
}

export async function fetchMagnaConstitution(): Promise<MagnaConstitution> {
  const res = await fetch(`${API_URL}/v1/world/constitution`, { cache: "no-store" });
  if (!res.ok) throw new Error(`world constitution ${res.status}`);
  return (await res.json()) as MagnaConstitution;
}

export async function fetchResearchReleasePolicy(): Promise<ResearchReleasePolicy> {
  const res = await fetch(`${API_URL}/v1/research/release-policy`, { cache: "no-store" });
  if (!res.ok) throw new Error(`research release policy ${res.status}`);
  return (await res.json()) as ResearchReleasePolicy;
}

export async function fetchResearchAllocationMarket(): Promise<ResearchAllocationMarket> {
  const res = await fetch(`${API_URL}/v1/research-market`, { cache: "no-store" });
  if (!res.ok) throw new Error(`research market ${res.status}`);
  return (await res.json()) as ResearchAllocationMarket;
}

export async function fetchResearchTest01Status(): Promise<ResearchTest01Status> {
  const res = await fetch(`${API_URL}/v1/forums/research-test-01/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`research test 01 ${res.status}`);
  return (await res.json()) as ResearchTest01Status;
}

export async function fetchMagnaKnowledgeLedger(): Promise<MagnaKnowledgeLedgerSummary> {
  const res = await fetch(`${API_URL}/v1/knowledge-ledger`, { cache: "no-store" });
  if (!res.ok) throw new Error(`knowledge ledger ${res.status}`);
  return (await res.json()) as MagnaKnowledgeLedgerSummary;
}

export async function fetchMagnaTokoinTestnet(): Promise<MagnaTokoinTestnetStatus> {
  const res = await fetch(`${API_URL}/v1/tokoin-testnet/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`tokoin testnet ${res.status}`);
  return (await res.json()) as MagnaTokoinTestnetStatus;
}

export async function fetchPopulation(): Promise<WorldSnapshot> {
  const res = await fetch(`${API_URL}/v1/world/population`, { cache: "no-store" });
  if (!res.ok) throw new Error(`world population ${res.status}`);
  return (await res.json()) as WorldSnapshot;
}

export async function fetchTokoinStatus(): Promise<TokoinStatus> {
  const res = await fetch(`${API_URL}/v1/tokoins/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`tokoin status ${res.status}`);
  return (await res.json()) as TokoinStatus;
}

export async function fetchObservatoryActionability(
  windowSeconds = 3600,
): Promise<ObservatoryActionability> {
  const res = await fetch(
    `${API_URL}/v1/observatory/actionability?window_seconds=${windowSeconds}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`observatory actionability ${res.status}`);
  return (await res.json()) as ObservatoryActionability;
}

export async function fetchChallengeActionability(
  missionId: string,
): Promise<ChallengeActionability> {
  const res = await fetch(
    `${API_URL}/v1/mission-challenges/${encodeURIComponent(missionId)}/actionability`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`challenge actionability ${res.status}`);
  return (await res.json()) as ChallengeActionability;
}

export async function fetchSpaceMessages(
  spaceId: string,
  limit = 30,
): Promise<{ messages: WorldMessageEvent[] }> {
  const res = await fetch(
    `${API_URL}/v1/spaces/${encodeURIComponent(spaceId)}/messages?limit=${limit}`,
    { cache: "no-store" },
  );
  if (!res.ok) throw new Error(`space messages ${res.status}`);
  return (await res.json()) as { messages: WorldMessageEvent[] };
}

export function worldSocket(): WebSocket {
  return new WebSocket(realtimeWsUrl());
}
