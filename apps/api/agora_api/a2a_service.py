"""A2A service (S2-T14/T15/T16/T18, ADR-0010).

Uses the OFFICIAL a2a-sdk (1.1.2, protocol 1.0.x) canonical protobuf types
for every wire object — AgentCard, Message, Task, TaskStatus, Artifact —
serialized with proto3 JSON mapping (the A2A JSON representation).
`ParseDict` rejects unknown fields, so malformed cards/messages fail loudly.

Relay model: AGORA accepts standards-compliant JSON-RPC requests on behalf of
registered agents and routes the work over the target Bridge's EXISTING
outbound realtime connection (no inbound port on the owner's machine, and
AGORA Cloud never executes the target model — SEC-008).

Supported JSON-RPC methods in Sprint 02: `message/send`, `tasks/get`
(documented subset; streaming and push notifications are later sprints).

AGORA-specific metadata (nonce, initiator) travels in the Message/Task
`metadata` field — a standards-provided extension point — never as invented
wire fields.
"""

import hashlib
import json
import secrets
from typing import Any

import a2a.types as a2a_types
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.errors import AgoraError, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_task_id
from agora_api.logging import get_logger
from agora_api.models import A2ATask, Agent
from agora_api.realtime import gateway

log = get_logger("agora.api.a2a")

A2A_PROTOCOL_VERSION = "1.0"
FIRST_CONTACT_SKILL = "first_contact"


class A2AError(AgoraError):
    status_code = 400
    code = "a2a_invalid"


def build_agent_card(agent: Agent, base_url: str) -> dict[str, Any]:
    """Standards-compliant Agent Card built with official SDK types."""
    card = a2a_types.AgentCard(
        name=agent.name,
        description=(
            f"AGORA agent {agent.name}. Intelligence lives at the edge; this "
            "endpoint is the AGORA relay for its owner-operated runtime."
        ),
        version=agent.current_version_id or "1",
        capabilities=a2a_types.AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text/plain", "application/json"],
        default_output_modes=["application/json"],
        skills=[
            a2a_types.AgentSkill(
                id=FIRST_CONTACT_SKILL,
                name="First Contact",
                description=(
                    "Responds to a first-contact greeting task with a "
                    "hash-attributed note artifact."
                ),
                tags=["social", "agora"],
            )
        ],
    )
    card.supported_interfaces.add(
        url=f"{base_url}/v1/a2a/agents/{agent.agent_id}/jsonrpc",
        protocol_binding="JSONRPC",
        protocol_version=A2A_PROTOCOL_VERSION,
    )
    return MessageToDict(card)


def validate_agent_card(card: dict[str, Any]) -> None:
    """Strict validation against the official implementation types."""
    try:
        parsed = ParseDict(card, a2a_types.AgentCard())
    except ParseError as exc:
        raise A2AError(f"Invalid Agent Card: {str(exc)[:200]}") from exc
    if not parsed.name or not parsed.version:
        raise A2AError("Agent Card missing required identity fields.")


def parse_wire_message(message: dict[str, Any]) -> a2a_types.Message:
    try:
        parsed = ParseDict(message, a2a_types.Message())
    except ParseError as exc:
        raise A2AError(f"Invalid A2A Message: {str(exc)[:200]}") from exc
    if not parsed.message_id:
        raise A2AError("A2A Message requires messageId.")
    return parsed


def task_wire(row: A2ATask) -> dict[str, Any]:
    """Serialize our task row back into a canonical A2A Task."""
    state = {
        "submitted": a2a_types.TaskState.TASK_STATE_SUBMITTED,
        "working": a2a_types.TaskState.TASK_STATE_WORKING,
        "completed": a2a_types.TaskState.TASK_STATE_COMPLETED,
        "failed": a2a_types.TaskState.TASK_STATE_FAILED,
        "rejected": a2a_types.TaskState.TASK_STATE_REJECTED,
    }[row.status]
    task = a2a_types.Task(id=row.task_id, context_id=row.context_id,
                          status=a2a_types.TaskStatus(state=state))
    wire = MessageToDict(task)
    wire["history"] = [row.message]
    if row.artifacts:
        wire["artifacts"] = row.artifacts
    return wire


async def create_task(
    session: AsyncSession,
    *,
    initiator_agent_id: str,
    target: Agent,
    message: dict[str, Any],
    trace_id: str | None,
) -> A2ATask:
    parsed = parse_wire_message(message)
    task = A2ATask(
        task_id=parsed.task_id or new_task_id(),
        context_id=parsed.context_id or new_task_id(),
        initiator_agent_id=initiator_agent_id,
        target_agent_id=target.agent_id,
        status="submitted",
        message=message,
        nonce=secrets.token_hex(16),  # server-issued, verified in the artifact
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(task)
    await append_event(
        session,
        event_type="a2a.task.created",
        actor={"agent_id": initiator_agent_id},
        payload={"task_id": task.task_id, "target_agent_id": target.agent_id},
        trace_id=trace_id,
    )
    await session.commit()
    await deliver_task(task)
    return task


def _relay_frame(task: A2ATask) -> dict[str, Any]:
    """Payload is remote content: the Bridge must treat it as untrusted."""
    return {
        "task_id": task.task_id,
        "context_id": task.context_id,
        "message": task.message,
        "agora": {
            "nonce": task.nonce,
            "initiator_agent_id": task.initiator_agent_id,
            "target_agent_id": task.target_agent_id,
        },
    }


async def deliver_task(task: A2ATask) -> bool:
    """Relay over the target's outbound connection. Offline targets stay in
    `submitted` and receive pending tasks at their next connect (predictable
    offline handling). No payload contents are logged."""
    await gateway.publish(task.target_agent_id, "a2a_task", _relay_frame(task))
    log.info("a2a.task_relayed", task_id=task.task_id, target=task.target_agent_id)
    return True


async def pending_tasks_for(session: AsyncSession, agent_id: str) -> list[A2ATask]:
    return list(
        (
            await session.execute(
                select(A2ATask).where(
                    A2ATask.target_agent_id == agent_id, A2ATask.status == "submitted"
                )
            )
        ).scalars()
    )


def artifact_hash(artifact: dict[str, Any]) -> str:
    """Integrity hash over the artifact's parts (stable serialization)."""
    return hashlib.sha256(
        json.dumps(artifact.get("parts", []), sort_keys=True).encode()
    ).hexdigest()


async def complete_task(
    session: AsyncSession, task_id: str, artifacts: list[dict[str, Any]]
) -> bool:
    """Idempotent completion (SEC-009): the conditional UPDATE is the single
    logical transition — duplicate results from re-delivered tasks are
    ignored. Artifacts are validated against official SDK types."""
    for artifact in artifacts:
        try:
            ParseDict(artifact, a2a_types.Artifact())
        except ParseError as exc:
            raise A2AError(f"Invalid A2A Artifact: {str(exc)[:200]}") from exc

    result = await session.execute(
        update(A2ATask)
        .where(A2ATask.task_id == task_id, A2ATask.status.in_(["submitted", "working"]))
        .values(status="completed", artifacts=artifacts, updated_at=now_utc())
    )
    if getattr(result, "rowcount", 0) != 1:
        log.info("a2a.duplicate_completion_ignored", task_id=task_id)
        return False

    task = await session.get(A2ATask, task_id)
    assert task is not None
    await append_event(
        session,
        event_type="a2a.task.completed",
        actor={"agent_id": task.target_agent_id},
        payload={
            "task_id": task_id,
            "initiator_agent_id": task.initiator_agent_id,
            "artifact_hashes": [artifact_hash(a) for a in artifacts],
        },
    )
    await session.commit()
    await gateway.publish(
        task.initiator_agent_id, "a2a_completed", {"task_id": task_id}
    )
    return True


async def get_task_for(session: AsyncSession, task_id: str, agent_id: str) -> A2ATask:
    task = await session.get(A2ATask, task_id)
    if task is None or agent_id not in (task.initiator_agent_id, task.target_agent_id):
        raise NotFound("Task not found.")
    return task


def jsonrpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def validate_jsonrpc(body: Any) -> tuple[Any, str, dict]:
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
        raise ValidationFailed("Expected JSON-RPC 2.0 request.")
    method, params = body.get("method"), body.get("params", {})
    if not isinstance(method, str) or not isinstance(params, dict):
        raise ValidationFailed("Invalid JSON-RPC method/params.")
    return body.get("id"), method, params
