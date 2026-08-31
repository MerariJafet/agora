import { getJson } from "@/lib/api";

export interface TokoinStatus {
  currency_code: "TOKOIN";
  unit: "acero";
  aceros_per_tokoin: number;
  max_supply: number;
  max_supply_aceros: number;
  circulating_supply_aceros: number;
  treasury_balance_aceros: number;
  wallet_count: number;
  genesis_hash: string;
  treasury_wallet_id: string;
  monetary_policy: string;
  blockchain: {
    valid: boolean;
    blocks: number;
    sealed_entries: number;
    pending_entries: number;
    tip_hash: string | null;
  };
}

export interface TokoinWallet {
  wallet_id: string;
  wallet_address: string;
  address_scheme: string;
  agent_id: string | null;
  label: string;
  balance_aceros: number;
}

export interface TokoinLedgerEntry {
  entry_id: string;
  sequence: number;
  entry_type: string;
  from_wallet_id: string | null;
  to_wallet_id: string | null;
  amount: number;
  currency_code: "TOKOIN";
  reason: string;
  mission_id: string | null;
  event_id: string | null;
  previous_hash: string | null;
  created_at: string;
  entry_hash: string;
  authorization: {
    authorization_id: string;
    authorization_type: string;
    signer_agent_id: string | null;
    signer_device_id: string | null;
    nonce: string | null;
    message_hash: string;
    signature_present: boolean;
    created_at: string;
  } | null;
}

export interface TokoinBlock {
  block_id: string;
  height: number;
  first_sequence: number;
  last_sequence: number;
  entry_count: number;
  transaction_merkle_root: string;
  previous_block_hash: string | null;
  block_hash: string;
  proof_bundle_hash: string;
  created_at: string;
}

export interface TokoinChainExport {
  schema: "agora.tokoin.chain_export.v1";
  currency_code: "TOKOIN";
  unit: "acero";
  aceros_per_tokoin: number;
  max_supply_aceros: number;
  wallets: TokoinWallet[];
  ledger_entries: TokoinLedgerEntry[];
  ledger_entries_returned: number;
  ledger_entry_limit: number;
  blocks: TokoinBlock[];
  verification: {
    valid: boolean;
    scheme: string;
    blocks: number;
    sealed_entries: number;
    pending_entries: number;
    tip_hash: string | null;
    signed_transfer_entries: number;
    unsigned_legacy_transfer_entries: number;
    security_model: string;
  };
  trust_boundary: string;
}

export function getTokoinStatus(): Promise<TokoinStatus> {
  return getJson("/v1/tokoins/status");
}

export function getTokoinChainExport(limitEntries = 200): Promise<TokoinChainExport> {
  return getJson(`/v1/tokoins/blockchain/export?limit_entries=${limitEntries}`);
}
