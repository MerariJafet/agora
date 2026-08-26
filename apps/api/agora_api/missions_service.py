"""Mission domain: lifecycle, participation, task DAG, leases
(S5-T04..T10, ADR-0026).

A Mission is a social coordination object — NOT an A2A Task, NOT an MCP
Task. Those remain transport/execution primitives a MissionTask may use
underneath (see a2a_mission_adapter for the A2A bridge).
"""

from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import AgoraError, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_mission_id, new_mission_task_id
from agora_api.models import (
    Mission,
    MissionParticipant,
    MissionTask,
    MissionTaskDependency,
    RecordProvenance,
)
from agora_api.provenance import add_provenance, record_key, require_actor_record_compatible

LEASE_DURATION = timedelta(minutes=15)

# Explicit transition table (ADR: no silent/implicit transitions).
MISSION_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"open", "cancelled"},
    "open": {"forming", "active", "cancelled"},
    "forming": {"active", "cancelled"},
    "active": {"blocked", "review", "completed", "failed", "cancelled"},
    "blocked": {"active", "failed", "cancelled"},
    "review": {"active", "completed", "failed", "cancelled"},
    "completed": {"archived"},
    "failed": {"archived"},
    "cancelled": {"archived"},
    "archived": set(),
}

TASK_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"ready", "cancelled"},
    "ready": {"assigned", "cancelled"},
    "assigned": {"running", "ready", "cancelled"},  # ready = lease expired
    "running": {"submitted", "ready", "failed", "cancelled"},
    "submitted": {"accepted", "needs_revision", "cancelled"},
    "needs_revision": {"assigned", "ready", "cancelled"},
    "accepted": set(),
    "failed": {"ready", "cancelled"},
    "cancelled": set(),
    "blocked": {"ready", "cancelled"},
}


class InvalidTransition(AgoraError):
    status_code = 409
    code = "invalid_transition"


class MissionFull(AgoraError):
    status_code = 409
    code = "mission_full"


class TaskNotAvailable(AgoraError):
    status_code = 409
    code = "task_not_available"


class StaleAttempt(AgoraError):
    status_code = 409
    code = "stale_attempt"


class DependencyCycle(AgoraError):
    status_code = 422
    code = "dependency_cycle"


def validate_create_mission(payload: Any) -> None:
    validate_boundary("missions.schema.json", "/$defs/CreateMissionRequest", payload)


def validate_join_mission(payload: Any) -> None:
    validate_boundary("missions.schema.json", "/$defs/JoinMissionRequest", payload)


def validate_create_task(payload: Any) -> None:
    validate_boundary("missions.schema.json", "/$defs/CreateMissionTaskRequest", payload)


def validate_submit_task(payload: Any) -> None:
    validate_boundary("missions.schema.json", "/$defs/SubmitMissionTaskRequest", payload)


def _transition_mission(mission: Mission, target: str) -> None:
    allowed = MISSION_TRANSITIONS.get(mission.state, set())
    if target not in allowed:
        raise InvalidTransition(f"Cannot move Mission from {mission.state} to {target}.")
    mission.state = target


def _transition_task(task: MissionTask, target: str) -> None:
    allowed = TASK_TRANSITIONS.get(task.state, set())
    if target not in allowed:
        raise InvalidTransition(f"Cannot move MissionTask from {task.state} to {target}.")
    task.state = target


def mission_view(mission: Mission) -> dict[str, Any]:
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "objective": mission.objective,
        "description": mission.description,
        "state": mission.state,
        "visibility": mission.visibility,
        "hosting_space_id": mission.hosting_space_id,
        "related_debate_id": mission.related_debate_id,
        "related_claim_ids": mission.related_claim_ids,
        "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
        "reward_aceros": mission.reward_aceros,
        "challenge_kind": mission.challenge_kind,
        "challenge_problem": mission.challenge_problem,
        "challenge_space_color": mission.challenge_space_color,
        "resolution_policy": mission.resolution_policy,
        "winning_submission_id": mission.winning_submission_id,
        "resolved_by_agent_id": mission.resolved_by_agent_id,
        "max_participants": mission.max_participants,
        "completion_policy": mission.completion_policy,
        "created_by_agent_id": mission.created_by_agent_id,
        "final_artifact_version_ids": mission.final_artifact_version_ids,
        "created_at": mission.created_at.isoformat(),
        "activated_at": mission.activated_at.isoformat() if mission.activated_at else None,
        "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
        "resolved_at": mission.resolved_at.isoformat() if mission.resolved_at else None,
    }


def task_view(task: MissionTask) -> dict[str, Any]:
    return {
        "mission_task_id": task.mission_task_id,
        "mission_id": task.mission_id,
        "title": task.title,
        "description": task.description,
        "state": task.state,
        "required_skills": task.required_skills,
        "expected_artifact_types": task.expected_artifact_types,
        "assigned_agent_id": task.assigned_agent_id,
        "lease_expires_at": task.lease_expires_at.isoformat() if task.lease_expires_at else None,
        "attempt": task.attempt,
        "result_artifact_version_id": task.result_artifact_version_id,
        "created_at": task.created_at.isoformat(),
    }


async def create_mission(
    session: AsyncSession, *, agent_id: str, agent_version_id: str | None,
    payload: dict[str, Any], trace_id: str | None,
) -> Mission:
    mission = Mission(
        mission_id=new_mission_id(),
        title=payload["title"],
        objective=payload["objective"],
        description=payload.get("description"),
        state="open",
        visibility=payload.get("visibility", "public"),
        hosting_space_id=payload.get("hosting_space_id"),
        related_debate_id=payload.get("related_debate_id"),
        related_claim_ids=payload.get("related_claim_ids"),
        max_participants=payload.get("max_participants", 16),
        completion_policy=payload.get("completion_policy") or {},
        created_by_agent_id=agent_id,
        created_by_agent_version_id=agent_version_id,
        created_at=now_utc(),
    )
    session.add(mission)
    actor_provenance = await session.get(RecordProvenance, ("agents", agent_id))
    await add_provenance(
        session,
        record_table="missions",
        record_id=mission.mission_id,
        provenance_class=actor_provenance.provenance_class if actor_provenance else None,
        environment_id=actor_provenance.environment_id if actor_provenance else None,
        run_id=actor_provenance.run_id if actor_provenance else None,
        world_instance_id=actor_provenance.world_instance_id if actor_provenance else None,
        created_by="missions.create",
        source_reference=agent_id,
        created_by_actor_id=agent_id,
        created_by_actor_provenance=(
            actor_provenance.provenance_class if actor_provenance else None
        ),
    )
    await append_event(
        session,
        event_type="mission.created",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission.mission_id, "title": mission.title,
                 "related_debate_id": mission.related_debate_id},
        trace_id=trace_id,
    )
    return mission


async def join_mission(
    session: AsyncSession, *, mission_id: str, agent_id: str, agent_version_id: str | None,
    roles: list[str], trace_id: str | None,
) -> MissionParticipant:
    mission = (
        await session.execute(
            select(Mission).where(Mission.mission_id == mission_id).with_for_update()
        )
    ).scalar_one_or_none()
    if mission is None:
        raise NotFound("Mission not found.")
    if mission.state in ("completed", "failed", "cancelled", "archived"):
        raise InvalidTransition(f"Mission is {mission.state}; cannot join.")

    existing = await session.get(MissionParticipant, (mission_id, agent_id))
    if existing is not None and existing.left_at is None:
        existing.roles = roles or existing.roles
        return existing

    count = (
        await session.execute(
            select(MissionParticipant).where(
                MissionParticipant.mission_id == mission_id,
                MissionParticipant.left_at.is_(None),
            )
        )
    ).scalars().all()
    if len(count) >= mission.max_participants:
        raise MissionFull(f"Mission already has {mission.max_participants} participants.")

    participant = MissionParticipant(
        mission_id=mission_id, agent_id=agent_id, agent_version_id=agent_version_id,
        roles=roles or ["observer"], joined_at=now_utc(),
    )
    session.add(participant)
    provenance = await require_actor_record_compatible(
        session,
        actor_agent_id=agent_id,
        container_table="missions",
        container_id=mission_id,
        target_record_table="mission_participants",
        target_record_id=record_key(mission_id, agent_id),
        trace_id=trace_id,
    )
    await add_provenance(
        session,
        record_table="mission_participants",
        record_id=record_key(mission_id, agent_id),
        created_by="missions.join",
        source_reference=mission_id,
        **provenance,
    )
    if mission.state == "open":
        mission.state = "forming"
    await append_event(
        session,
        event_type="mission.participant_joined",
        actor={"agent_id": agent_id, "agent_version_id": agent_version_id},
        payload={"mission_id": mission_id, "roles": roles},
        trace_id=trace_id,
    )
    return participant


async def activate_mission(
    session: AsyncSession, *, mission: Mission, agent_id: str, trace_id: str | None
) -> Mission:
    if mission.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may activate it.")
    _transition_mission(mission, "active")
    mission.activated_at = now_utc()
    # Completion policy is frozen at activation (constitution rule).
    await append_event(
        session,
        event_type="mission.activated",
        actor={"agent_id": agent_id},
        payload={"mission_id": mission.mission_id, "completion_policy": mission.completion_policy},
        trace_id=trace_id,
    )
    return mission


async def cancel_mission(
    session: AsyncSession, *, mission: Mission, agent_id: str, trace_id: str | None
) -> Mission:
    if mission.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may cancel it.")
    _transition_mission(mission, "cancelled")
    await append_event(
        session,
        event_type="mission.cancelled",
        actor={"agent_id": agent_id},
        payload={"mission_id": mission.mission_id},
        trace_id=trace_id,
    )
    return mission


# -- Mission Task DAG --------------------------------------------------------

async def _would_create_cycle(
    session: AsyncSession, task_id: str, depends_on_task_id: str
) -> bool:
    """Bounded reachability check: would adding this edge let `task_id`
    reach itself? Postgres-first (no graph DB), same posture as ADR-0022 —
    Mission task graphs are small, so plain BFS over the edges table is
    sufficient and explainable."""
    frontier = {depends_on_task_id}
    seen: set[str] = set()
    for _ in range(200):  # hard bound, mirrors ADR-0022's node cap philosophy
        if task_id in frontier:
            return True
        if not frontier - seen:
            break
        seen |= frontier
        rows = (
            await session.execute(
                select(MissionTaskDependency.depends_on_task_id).where(
                    MissionTaskDependency.task_id.in_(frontier)
                )
            )
        ).scalars().all()
        frontier = set(rows) - seen
        if not frontier:
            break
    return False


async def create_task(
    session: AsyncSession, *, mission: Mission, payload: dict[str, Any], trace_id: str | None,
    agent_id: str,
) -> MissionTask:
    dependency_ids = payload.get("dependency_task_ids") or []
    task = MissionTask(
        mission_task_id=new_mission_task_id(),
        mission_id=mission.mission_id,
        title=payload["title"],
        description=payload["description"],
        state="pending",
        required_skills=payload.get("required_skills"),
        expected_artifact_types=payload.get("expected_artifact_types"),
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(task)
    await session.flush()

    for dep_id in dependency_ids:
        if dep_id == task.mission_task_id:
            raise ValidationFailed("A task cannot depend on itself.")
        dep = await session.get(MissionTask, dep_id)
        if dep is None or dep.mission_id != mission.mission_id:
            raise NotFound(f"Dependency task {dep_id} not found in this Mission.")
        if await _would_create_cycle(session, task.mission_task_id, dep_id):
            raise DependencyCycle("This dependency would create a cycle.")
        session.add(MissionTaskDependency(task_id=task.mission_task_id, depends_on_task_id=dep_id))

    task.state = "ready" if not dependency_ids else "pending"
    await _refresh_readiness(session, mission.mission_id)
    await append_event(
        session,
        event_type="mission.task_created",
        actor={"agent_id": agent_id},
        payload={"mission_id": mission.mission_id, "mission_task_id": task.mission_task_id,
                 "dependency_task_ids": dependency_ids},
        trace_id=trace_id,
    )
    return task


async def _refresh_readiness(session: AsyncSession, mission_id: str) -> None:
    """A pending task becomes ready once every dependency is accepted."""
    tasks = (
        await session.execute(
            select(MissionTask).where(
                MissionTask.mission_id == mission_id, MissionTask.state == "pending"
            )
        )
    ).scalars().all()
    for task in tasks:
        dep_ids = (
            await session.execute(
                select(MissionTaskDependency.depends_on_task_id).where(
                    MissionTaskDependency.task_id == task.mission_task_id
                )
            )
        ).scalars().all()
        if not dep_ids:
            task.state = "ready"
            continue
        deps = (
            await session.execute(
                select(MissionTask).where(MissionTask.mission_task_id.in_(dep_ids))
            )
        ).scalars().all()
        if all(d.state == "accepted" for d in deps):
            task.state = "ready"


async def claim_task(
    session: AsyncSession, *, task_id: str, agent_id: str, trace_id: str | None
) -> MissionTask:
    """Transactional lease claim: locks the task row before check-and-set,
    same pattern as Sprint 04's Debate participant-cap enforcement."""
    task = (
        await session.execute(
            select(MissionTask).where(MissionTask.mission_task_id == task_id).with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFound("Mission task not found.")

    now = now_utc()
    lease_active = task.lease_expires_at is not None and task.lease_expires_at > now
    if task.state == "assigned" and lease_active:
        raise TaskNotAvailable("Task is already leased to another agent.")
    if task.state not in ("ready", "needs_revision", "failed") and not (
        task.state == "assigned" and not lease_active
    ):
        raise TaskNotAvailable(f"Task is {task.state}; not claimable.")

    task.assigned_agent_id = agent_id
    task.lease_expires_at = now + LEASE_DURATION
    task.attempt += 1
    _transition_task(task, "assigned") if task.state != "assigned" else None
    task.state = "assigned"
    task.updated_at = now
    await append_event(
        session,
        event_type="mission.task_claimed",
        actor={"agent_id": agent_id},
        payload={"mission_task_id": task_id, "attempt": task.attempt},
        trace_id=trace_id,
    )
    return task


async def assign_task(
    session: AsyncSession, *, task_id: str, target_agent_id: str, coordinator_agent_id: str,
    trace_id: str | None,
) -> MissionTask:
    """Coordinator-driven assignment (S5.1-T02): the same lease/state effect
    as `claim_task`, but initiated by the Mission's creator pushing work to
    a specific agent rather than that agent pulling it. Used as the first
    half of A2A delegation — see `mission_a2a_adapter.delegate_task`, which
    calls this inside the same transaction as the A2A Task creation so both
    commit atomically."""
    task = (
        await session.execute(
            select(MissionTask).where(MissionTask.mission_task_id == task_id).with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFound("Mission task not found.")
    mission = await session.get(Mission, task.mission_id)
    if mission is None or mission.created_by_agent_id != coordinator_agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may assign a task.")

    now = now_utc()
    lease_active = task.lease_expires_at is not None and task.lease_expires_at > now
    if task.state == "assigned" and lease_active and task.assigned_agent_id != target_agent_id:
        raise TaskNotAvailable("Task is already leased to another agent.")
    if task.state not in ("ready", "needs_revision", "failed") and not (
        task.state == "assigned" and (not lease_active or task.assigned_agent_id == target_agent_id)
    ):
        raise TaskNotAvailable(f"Task is {task.state}; not assignable.")

    task.assigned_agent_id = target_agent_id
    task.lease_expires_at = now + LEASE_DURATION
    task.attempt += 1
    if task.state != "assigned":
        _transition_task(task, "assigned")
    task.state = "assigned"
    task.updated_at = now
    await append_event(
        session,
        event_type="mission.task_assigned",
        actor={"agent_id": coordinator_agent_id},
        payload={"mission_task_id": task_id, "target_agent_id": target_agent_id,
                 "attempt": task.attempt},
        trace_id=trace_id,
    )
    return task


async def renew_lease(
    session: AsyncSession, *, task_id: str, agent_id: str
) -> MissionTask:
    task = (
        await session.execute(
            select(MissionTask).where(MissionTask.mission_task_id == task_id).with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFound("Mission task not found.")
    if task.assigned_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the leasing agent may renew this lease.")
    task.lease_expires_at = now_utc() + LEASE_DURATION
    if task.state == "assigned":
        task.state = "running"
    return task


async def submit_task(
    session: AsyncSession, *, task_id: str, agent_id: str, artifact_version_id: str | None,
    trace_id: str | None, attempt: int | None = None,
) -> MissionTask:
    task = (
        await session.execute(
            select(MissionTask).where(MissionTask.mission_task_id == task_id).with_for_update()
        )
    ).scalar_one_or_none()
    if task is None:
        raise NotFound("Mission task not found.")
    if task.assigned_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the assigned agent may submit this task.")
    if attempt is not None and attempt != task.attempt:
        # A late/duplicate submission from a superseded attempt (lease
        # expired, task reassigned, a new attempt already running) must
        # never silently overwrite the current attempt's result — even if
        # the same agent ends up holding both attempts (S5.1-T05).
        raise StaleAttempt(
            f"Submission is for attempt {attempt}, but the task is now on attempt {task.attempt}."
        )
    if task.state == "submitted":
        return task  # idempotent: duplicate submission is a no-op
    if task.state not in ("assigned", "running"):
        raise InvalidTransition(f"Cannot submit from state {task.state}.")
    task.state = "submitted"
    task.result_artifact_version_id = artifact_version_id
    task.updated_at = now_utc()
    await append_event(
        session,
        event_type="mission.task_submitted",
        actor={"agent_id": agent_id},
        payload={"mission_task_id": task_id, "artifact_version_id": artifact_version_id},
        trace_id=trace_id,
    )
    return task


async def accept_task(
    session: AsyncSession, *, task: MissionTask, agent_id: str, trace_id: str | None
) -> MissionTask:
    _transition_task(task, "accepted")
    task.updated_at = now_utc()
    await _refresh_readiness(session, task.mission_id)
    await append_event(
        session,
        event_type="mission.task_accepted",
        actor={"agent_id": agent_id},
        payload={"mission_task_id": task.mission_task_id},
        trace_id=trace_id,
    )
    return task


async def request_revision(
    session: AsyncSession, *, task: MissionTask, agent_id: str, trace_id: str | None
) -> MissionTask:
    _transition_task(task, "needs_revision")
    task.updated_at = now_utc()
    await append_event(
        session,
        event_type="mission.task_needs_revision",
        actor={"agent_id": agent_id},
        payload={"mission_task_id": task.mission_task_id},
        trace_id=trace_id,
    )
    return task


async def expire_stale_leases(session: AsyncSession, mission_id: str) -> int:
    """Operator/scheduler entry point: expired leases return to `ready`
    WITHOUT implying failure (constitution rule) — the prior attempt's
    submission, if any, is untouched."""
    now = now_utc()
    tasks = (
        await session.execute(
            select(MissionTask).where(
                MissionTask.mission_id == mission_id,
                MissionTask.state.in_(["assigned", "running"]),
                MissionTask.lease_expires_at < now,
            )
        )
    ).scalars().all()
    for task in tasks:
        task.state = "ready"
        task.assigned_agent_id = None
        task.lease_expires_at = None
    return len(tasks)
