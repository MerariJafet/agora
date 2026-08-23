"""Canonical A2A adapter for MissionTask delegation (S5.1-T02/T03, ADR-0026,
ADR-0029).

MissionTask stays AGORA's own social/domain object and the sole source of
truth for Mission workflow state (ready/assigned/submitted/accepted/...).
The A2A Task this module creates is a *transport* for handing the work to a
different connected Agent over the existing outbound-only relay
(a2a_service.py) — it is the source of truth only for the interoperable
execution exchange itself (submitted/working/completed/failed/rejected).
Neither state machine is duplicated inside the other:

- Delegating a task assigns it in Mission tables (`missions_service.assign_task`)
  AND creates/relays a canonical A2A Task in the same transaction, so the
  MissionTask row always durably remembers which A2A Task carries its
  current attempt (`mission_tasks.a2a_task_id`).
- The A2A Task completing does NOT, by itself, move the MissionTask to
  `accepted` or publish anything. It only proves the execution exchange
  finished — mission_state_for_a2a_state() documents the mapping and is
  intentionally conservative (see S5.1-T03).
- Nothing here is a private chain-of-thought store: the message sent over
  A2A is the same title/description already public within the Mission, plus
  AGORA-extension correlation metadata (mission_id/mission_task_id/attempt)
  in the A2A Message's own `metadata` field, a standards-provided extension
  point — never an invented top-level wire field.
"""

import secrets
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.a2a_service import create_task as a2a_create_task
from agora_api.a2a_service import deliver_task
from agora_api.errors import NotFound
from agora_api.missions_service import assign_task
from agora_api.models import A2ATask, Agent, MissionTask

# Conservative, documented mapping (S5.1-T03). An A2A Task reaching
# "completed" only means the cross-Bridge execution exchange finished; it is
# surfaced to the coordinator as a hint, never auto-applied to the
# MissionTask. The coordinator/assignee still drive MissionTask transitions
# through the existing, already-accepted Mission API (claim/submit/accept/
# request-revision) — this mapping exists so operators and the Mission Board
# can show *why* a task might be stuck without conflating the two state
# machines.
A2A_TO_MISSION_HINT: dict[str, str] = {
    "submitted": "delegation_sent",
    "working": "delegate_working",
    "completed": "delegate_finished_awaiting_explicit_submission",
    "failed": "delegate_failed_may_need_reassignment",
    "rejected": "delegate_rejected_may_need_reassignment",
}


async def delegate_task(
    session: AsyncSession,
    *,
    task: MissionTask,
    target_agent: Agent,
    coordinator_agent_id: str,
    trace_id: str | None,
) -> A2ATask:
    """Assign `task` to `target_agent` and hand it off over the real A2A
    relay in one transaction. Idempotent in effect: re-delegating the same
    ready/needs_revision/failed task (or re-delegating to the SAME already-
    assigned target) creates a fresh A2A Task for the new attempt without
    ever leaving the MissionTask in a contradictory state."""
    assigned = await assign_task(
        session, task_id=task.mission_task_id, target_agent_id=target_agent.agent_id,
        coordinator_agent_id=coordinator_agent_id, trace_id=trace_id,
    )
    message: dict[str, Any] = {
        "messageId": f"mission-delegate-{secrets.token_hex(8)}",
        "role": "ROLE_USER",
        "parts": [{"text": f"{assigned.title}\n\n{assigned.description}"}],
        "metadata": {
            "agora_mission_id": assigned.mission_id,
            "agora_mission_task_id": assigned.mission_task_id,
            "agora_attempt": assigned.attempt,
        },
    }
    a2a_task = await a2a_create_task(
        session, initiator_agent_id=coordinator_agent_id, target=target_agent,
        message=message, trace_id=trace_id, commit=False,
    )
    assigned.a2a_task_id = a2a_task.task_id
    await session.commit()
    await deliver_task(a2a_task)
    return a2a_task


def mission_hint_for_a2a_state(a2a_status: str) -> str:
    return A2A_TO_MISSION_HINT.get(a2a_status, "unknown")


async def get_delegation_status(session: AsyncSession, task: MissionTask) -> dict[str, Any] | None:
    """Read-only view combining MissionTask (source of truth for workflow
    state) with its correlated A2A Task's exchange state (source of truth
    for the execution handoff only), for the Mission Board and API clients."""
    if not task.a2a_task_id:
        return None
    a2a_task = await session.get(A2ATask, task.a2a_task_id)
    if a2a_task is None:
        raise NotFound("Correlated A2A task not found.")
    return {
        "a2a_task_id": a2a_task.task_id,
        "a2a_status": a2a_task.status,
        "hint": mission_hint_for_a2a_state(a2a_task.status),
    }
