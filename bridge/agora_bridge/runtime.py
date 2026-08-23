"""RuntimeAdapter boundary (S2-T13, ADR-0014).

AGORA Bridge is runtime-neutral: it never imports a model provider SDK and
never holds provider credentials on AGORA's behalf. A runtime is anything
that can look at untrusted pending work and produce a response — a local
LLM through MCP, Claude Code attached to `agora mcp-serve`, or the
deterministic runtime below (which lets every automated test and the whole
First Contact E2E run WITHOUT model credentials).

Connecting a real MCP-capable runtime (e.g. Claude Code) manually:
    claude mcp add agora -- <repo>/.venv/bin/agora mcp-serve
The runtime then drives the same agora.* tools the deterministic runtime
uses. No provider secret ever enters Bridge configuration.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol

from agora_bridge.audit import LocalAuditLog
from agora_bridge.trust import is_untrusted


@dataclass(frozen=True)
class TaskResult:
    accepted: bool
    artifacts: list[dict[str, Any]]
    reason: str = ""


class RuntimeAdapter(Protocol):
    """A runtime may accept, reject or respond to a task. It receives ONLY
    the untrusted-wrapped task — no Bridge internals, no policy handles."""

    def handle_task(self, wrapped_task: dict[str, Any]) -> TaskResult: ...


class DeterministicRuntime:
    """Credential-free runtime for tests and the First Contact scenario.
    Produces the First Contact Note artifact: responder id, initiator id,
    the server-issued nonce and a short result, with a sha256 integrity
    hash over the parts (stable serialization)."""

    def __init__(self, agent_id: str, agent_name: str):
        self.agent_id = agent_id
        self.agent_name = agent_name

    def handle_task(self, wrapped_task: dict[str, Any]) -> TaskResult:
        if not is_untrusted(wrapped_task):
            return TaskResult(False, [], "refusing task without untrusted_remote envelope")
        frame = wrapped_task["content"]
        agora_meta = frame.get("agora", {})
        note = {
            "kind": "first_contact_note",
            "responder_agent_id": self.agent_id,
            "responder_name": self.agent_name,
            "initiator_agent_id": agora_meta.get("initiator_agent_id"),
            "nonce": agora_meta.get("nonce"),
            "result": f"{self.agent_name} acknowledges first contact. The plaza is open.",
        }
        parts = [{"text": json.dumps(note, sort_keys=True), "mediaType": "application/json"}]
        digest = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
        artifact = {
            "artifactId": f"art-{frame.get('task_id', 'unknown')}",
            "name": "First Contact Note",
            "description": f"Deterministic first-contact response from {self.agent_name}",
            "parts": parts,
            "metadata": {"sha256": digest, "creator_agent_id": self.agent_id},
        }
        return TaskResult(True, [artifact])


@dataclass(frozen=True)
class MissionDelegationHandler:
    """Operator-declared, single-mission-task work order: exactly which
    local file to publish and which Mission API calls to make once this
    specific MissionTask arrives over A2A. NOT a generic auto-executor —
    only mission_task_ids explicitly registered here are ever acted on, and
    the file path still goes through the same local publication boundary
    (LocalPolicyEngine, symlink/secret-filename refusal) as any other
    `agora publish-artifact` call."""

    artifact_id: str
    file_path: str
    media_type: str = "application/octet-stream"
    parent_artifact_version_id: str | None = None


class MissionAwareRuntime:
    """Recognizes AGORA Mission delegation metadata (`agora_mission_task_id`
    in the A2A Message's own `metadata` field — a standards extension point,
    never an invented wire field) inside an otherwise-ordinary A2A task.

    For any task WITHOUT that metadata, falls back to `fallback` (typically
    `DeterministicRuntime`) so this class is a strict superset, not a
    replacement, of existing A2A behavior (e.g. First Contact).

    For a recognized mission_task_id with a registered handler: publishes
    the ALREADY-EXPLICIT local file through the existing publication
    boundary and submits the MissionTask through the existing, already-
    accepted Mission API — this class invents no new execution path, it
    only wires the real A2A delivery to those existing calls."""

    def __init__(
        self,
        client,  # agora_bridge.client.ConnectionClient
        token: str,
        handlers: dict[str, MissionDelegationHandler],
        fallback: RuntimeAdapter | None = None,
        audit: LocalAuditLog | None = None,
    ):
        self._client = client
        self._token = token
        self._handlers = handlers
        self._fallback = fallback
        self._audit = audit

    def handle_task(self, wrapped_task: dict[str, Any]) -> TaskResult:
        if not is_untrusted(wrapped_task):
            return TaskResult(False, [], "refusing task without untrusted_remote envelope")
        frame = wrapped_task["content"]
        message = frame.get("message", {})
        metadata = message.get("metadata") if isinstance(message, dict) else None
        mission_task_id = (
            metadata.get("agora_mission_task_id") if isinstance(metadata, dict) else None
        )
        if not mission_task_id or not isinstance(metadata, dict):
            if self._fallback is not None:
                return self._fallback.handle_task(wrapped_task)
            return TaskResult(False, [], "not a Mission delegation and no fallback runtime")

        handler = self._handlers.get(mission_task_id)
        if handler is None:
            return TaskResult(
                False, [], f"no local handler registered for mission task {mission_task_id}"
            )

        from agora_bridge.publish_boundary import PublishDenied, validate_local_publish_path

        try:
            from agora_bridge.config import load_config

            safe_path = validate_local_publish_path(
                load_config(), handler.file_path, audit=self._audit or LocalAuditLog()
            )
        except PublishDenied as exc:
            return TaskResult(False, [], f"publish boundary denied: {exc}")

        publish_metadata: dict[str, Any] = {
            "display_filename": safe_path.name, "declared_media_type": handler.media_type,
            "mission_id": metadata.get("agora_mission_id"),
            "mission_task_ids": [mission_task_id],
        }
        if handler.parent_artifact_version_id:
            publish_metadata["parent_artifact_version_ids"] = [handler.parent_artifact_version_id]

        version = self._client.publish_artifact_version(
            self._token, handler.artifact_id, file_path=str(safe_path),
            media_type=handler.media_type, metadata=publish_metadata,
        )
        self._client.submit_mission_task(
            self._token, mission_task_id,
            {"artifact_version_id": version["artifact_version_id"],
             "attempt": metadata.get("agora_attempt")},
        )

        ack = {
            "artifactId": f"art-mission-ack-{mission_task_id}",
            "name": "Mission Delegation Acknowledgement",
            "description": "Confirms the delegated MissionTask was submitted through the "
                            "existing Mission API; this A2A artifact is NOT the Mission's "
                            "own ArtifactVersion.",
            "parts": [{"text": json.dumps(
                {"mission_task_id": mission_task_id,
                 "artifact_version_id": version["artifact_version_id"]},
                sort_keys=True,
            ), "mediaType": "application/json"}],
        }
        return TaskResult(True, [ack])
