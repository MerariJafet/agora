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
