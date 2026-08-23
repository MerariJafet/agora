"""Mission lifecycle, participation, task graph and lease API (S5-T04..T10)."""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.mission_a2a_adapter import delegate_task, get_delegation_status
from agora_api.mission_completion import evaluate_completion
from agora_api.missions_service import (
    accept_task,
    activate_mission,
    cancel_mission,
    claim_task,
    create_mission,
    create_task,
    join_mission,
    mission_view,
    renew_lease,
    request_revision,
    submit_task,
    task_view,
    validate_create_mission,
    validate_create_task,
    validate_join_mission,
    validate_submit_task,
)
from agora_api.models import Agent, Mission, MissionParticipant, MissionTask
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(tags=["missions"])

MAX_PAGE_SIZE = 100


async def _get_mission(session: AsyncSession, mission_id: str) -> Mission:
    mission = await session.get(Mission, mission_id)
    if mission is None:
        raise NotFound("Mission not found.")
    return mission


async def _get_task(session: AsyncSession, task_id: str) -> MissionTask:
    task = await session.get(MissionTask, task_id)
    if task is None:
        raise NotFound("Mission task not found.")
    return task


async def _fan_out(session: AsyncSession, mission_id: str, event: dict) -> None:
    """Mission realtime events are scoped by Mission id (a browser explicitly
    subscribes to the Missions it cares about, same WS subscribe mechanism
    already used for Spaces) and, when the Mission is hosted in a Space,
    ALSO fanned to that Space's scope so a Space view can show Mission
    activity without knowing every mission_id in advance. Never broadcast
    to an unscoped "global" channel — nothing subscribes to that, and it
    would defeat interest-based scoping."""
    await gateway.publish(mission_id, "mission", event)
    mission = await session.get(Mission, mission_id)
    if mission is not None and mission.hosting_space_id:
        await gateway.publish(mission.hosting_space_id, "mission", event)


@router.get("/v1/missions")
async def list_missions(
    session: AsyncSession = Depends(get_session),
    state: str | None = Query(default=None),
    limit: int = Query(default=50, le=MAX_PAGE_SIZE, ge=1),
) -> dict:
    query = select(Mission)
    if state:
        query = query.where(Mission.state == state)
    rows = (await session.execute(query.order_by(Mission.created_at.desc()).limit(limit))).scalars().all()
    return {"missions": [mission_view(m) for m in rows]}


@router.post("/v1/missions", status_code=201)
async def post_mission(
    request: Request, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    await enforce_rate_limit("mission_create", device.agent_id)
    body = await request.json()
    validate_create_mission(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    mission = await create_mission(
        session, agent_id=device.agent_id, agent_version_id=agent.current_version_id, payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(session, mission.mission_id, {"event": "created", **mission_view(mission)})
    return mission_view(mission)


@router.get("/v1/missions/{mission_id}")
async def get_mission(mission_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    mission = await _get_mission(session, mission_id)
    participants = (
        await session.execute(
            select(MissionParticipant).where(
                MissionParticipant.mission_id == mission_id,
                MissionParticipant.left_at.is_(None),
            )
        )
    ).scalars().all()
    return {
        **mission_view(mission),
        "participants": [
            {"agent_id": p.agent_id, "roles": p.roles} for p in participants
        ],
    }


@router.post("/v1/missions/{mission_id}/join", status_code=201)
async def post_join(
    mission_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_join", device.agent_id)
    body = await request.json() if await request.body() else {}
    validate_join_mission(body)
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    participant = await join_mission(
        session, mission_id=mission_id, agent_id=device.agent_id,
        agent_version_id=agent.current_version_id,
        roles=body.get("roles", []), trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        session, mission_id,
        {"event": "participant_joined", "mission_id": mission_id, "agent_id": device.agent_id,
         "roles": participant.roles},
    )
    return {"mission_id": mission_id, "agent_id": participant.agent_id, "roles": participant.roles}


@router.post("/v1/missions/{mission_id}/activate")
async def post_activate(
    mission_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    mission = await _get_mission(session, mission_id)
    mission = await activate_mission(
        session, mission=mission, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(session, mission_id, {"event": "activated", "mission_id": mission_id})
    return mission_view(mission)


@router.post("/v1/missions/{mission_id}/cancel")
async def post_cancel(
    mission_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    mission = await _get_mission(session, mission_id)
    mission = await cancel_mission(
        session, mission=mission, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(session, mission_id, {"event": "cancelled", "mission_id": mission_id})
    return mission_view(mission)


@router.get("/v1/missions/{mission_id}/tasks")
async def list_tasks(mission_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    await _get_mission(session, mission_id)
    rows = (
        await session.execute(select(MissionTask).where(MissionTask.mission_id == mission_id))
    ).scalars().all()
    return {"mission_tasks": [task_view(t) for t in rows]}


@router.post("/v1/missions/{mission_id}/tasks", status_code=201)
async def post_task(
    mission_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    mission = await _get_mission(session, mission_id)
    if mission.created_by_agent_id != device.agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may add tasks.")
    body = await request.json()
    validate_create_task(body)
    task = await create_task(
        session, mission=mission, payload=body, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        session, mission_id,
        {"event": "task_created", "mission_id": mission_id, "mission_task_id": task.mission_task_id,
         "state": task.state},
    )
    return task_view(task)


@router.get("/v1/mission-tasks/{task_id}")
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return task_view(await _get_task(session, task_id))


@router.post("/v1/mission-tasks/{task_id}/claim")
async def post_claim_task(
    task_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("mission_task_claim", device.agent_id)
    task = await claim_task(
        session, task_id=task_id, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        session, task.mission_id,
        {"event": "task_claimed", "mission_id": task.mission_id, "mission_task_id": task_id,
         "agent_id": device.agent_id},
    )
    return task_view(task)


@router.post("/v1/mission-tasks/{task_id}/renew-lease")
async def post_renew_lease(
    task_id: str, device: CurrentDevice, session: AsyncSession = Depends(get_session)
) -> dict:
    # Deliberately NOT fanned out: renewing a lease is not a semantic,
    # user-visible change (the assignee and state were already known), so
    # this must never become realtime heartbeat noise.
    task = await renew_lease(session, task_id=task_id, agent_id=device.agent_id)
    await session.commit()
    return task_view(task)


@router.post("/v1/mission-tasks/{task_id}/submit")
async def post_submit_task(
    task_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_submit_task(body)
    task = await submit_task(
        session, task_id=task_id, agent_id=device.agent_id,
        artifact_version_id=body.get("artifact_version_id"),
        trace_id=getattr(request.state, "trace_id", None), attempt=body.get("attempt"),
    )
    await session.commit()
    await _fan_out(
        session, task.mission_id,
        {"event": "task_submitted", "mission_id": task.mission_id, "mission_task_id": task_id,
         "artifact_version_id": task.result_artifact_version_id},
    )
    return task_view(task)


@router.post("/v1/mission-tasks/{task_id}/accept")
async def post_accept_task(
    task_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    task = await _get_task(session, task_id)
    mission = await _get_mission(session, task.mission_id)
    if mission.created_by_agent_id != device.agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may accept a task.")
    task = await accept_task(
        session, task=task, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await evaluate_completion(session, mission=mission, trace_id=getattr(request.state, "trace_id", None))
    await session.commit()
    await _fan_out(
        session, task.mission_id,
        {"event": "task_accepted", "mission_id": task.mission_id, "mission_task_id": task_id},
    )
    if mission.state == "completed":
        await _fan_out(
            session, mission.mission_id,
            {"event": "completed", "mission_id": mission.mission_id,
             "final_artifact_version_ids": mission.final_artifact_version_ids},
        )
    return task_view(task)


@router.post("/v1/mission-tasks/{task_id}/request-revision")
async def post_request_revision(
    task_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    task = await _get_task(session, task_id)
    mission = await _get_mission(session, task.mission_id)
    if mission.created_by_agent_id != device.agent_id:
        raise OwnerAuthorityRequired("Only the Mission creator may request revision.")
    task = await request_revision(
        session, task=task, agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    await _fan_out(
        session, task.mission_id,
        {"event": "task_needs_revision", "mission_id": task.mission_id, "mission_task_id": task_id},
    )
    return task_view(task)


@router.post("/v1/mission-tasks/{task_id}/delegate")
async def post_delegate_task(
    task_id: str, request: Request, device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Coordinator-driven delegation (S5.1-T02/T04): assign the task AND
    hand it off over the real cross-Bridge A2A relay to `target_agent_id`,
    instead of the assignee being the sole one who can poll/claim it."""
    task = await _get_task(session, task_id)
    body = await request.json()
    target_agent_id = body.get("target_agent_id")
    if not isinstance(target_agent_id, str) or not target_agent_id:
        raise ValidationFailed("target_agent_id is required.")
    target_agent = await session.get(Agent, target_agent_id)
    if target_agent is None:
        raise NotFound("Target agent not found.")
    a2a_task = await delegate_task(
        session, task=task, target_agent=target_agent, coordinator_agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    refreshed = await _get_task(session, task_id)
    await _fan_out(
        session, refreshed.mission_id,
        {"event": "task_delegated", "mission_id": refreshed.mission_id, "mission_task_id": task_id,
         "target_agent_id": target_agent_id, "a2a_task_id": a2a_task.task_id},
    )
    return {**task_view(refreshed), "a2a_task_id": a2a_task.task_id}


@router.get("/v1/mission-tasks/{task_id}/delegation")
async def get_delegation(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    task = await _get_task(session, task_id)
    status = await get_delegation_status(session, task)
    return status or {"a2a_task_id": None, "a2a_status": None, "hint": "not_delegated"}
