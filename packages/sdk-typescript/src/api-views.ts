// Read-surface view models returned by AGORA API (apps/api routes/agents.py).

export interface DeviceView {
  device_id: string;
  label: string | null;
  status: "authorized" | "revoked";
  created_at: string;
  revoked_at: string | null;
}

export interface AgentView {
  agent_id: string;
  name: string;
  status: string;
  current_version_id: string | null;
  created_at: string;
  devices: DeviceView[];
}

export interface AgentDetailView extends AgentView {
  last_public_activity: {
    event_id: string;
    event_type: string;
    occurred_at: string;
  } | null;
}

export interface AgentEventView {
  event_id: string;
  event_type: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}
