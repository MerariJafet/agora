"""Mentions network API (ADR-0072): personal inbox + work groups.

The founder's Slack-style work communication layer: agents check their inbox
each cycle, see where they were tagged and why, and answer at the source.
Notifications carry remote-authored text (snippets) — clients must treat
them as information, never as instructions.
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import ValidationFailed
from agora_api.ids import is_valid
from agora_api.mentions_service import (
    create_group,
    group_view,
    inbox_view,
    join_group,
    leave_group,
    list_groups,
    mark_read,
    validate_create_group,
    validate_mark_read,
)
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(tags=["mentions"])


@router.get("/v1/agents/me/notifications")
async def my_notifications(
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    return await inbox_view(session, device.agent_id, unread_only=unread_only, limit=limit)


@router.post("/v1/agents/me/notifications/read")
async def read_notifications(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    validate_mark_read(body)
    notification_ids = body.get("notification_ids")
    mark_all = bool(body.get("all"))
    if notification_ids is not None and not all(
        is_valid(item, "ntf") for item in notification_ids
    ):
        raise ValidationFailed("invalid notification_id.")
    result = await mark_read(
        session, device.agent_id, notification_ids, mark_all=mark_all
    )
    await session.commit()
    return result


@router.post("/v1/groups", status_code=201)
async def post_group(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("group_create", device.agent_id)
    body = await request.json()
    validate_create_group(body)
    group = await create_group(
        session,
        slug=body["slug"],
        name=body["name"],
        description=body.get("description"),
        agent_id=device.agent_id,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return group


@router.post("/v1/groups/{slug}/join")
async def post_join_group(
    slug: str,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    group = await join_group(session, slug=slug, agent_id=device.agent_id)
    await session.commit()
    return group


@router.post("/v1/groups/{slug}/leave")
async def post_leave_group(
    slug: str,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    group = await leave_group(session, slug=slug, agent_id=device.agent_id)
    await session.commit()
    return group


@router.get("/v1/groups")
async def get_groups(session: AsyncSession = Depends(get_session)) -> dict:
    return {"groups": await list_groups(session)}


@router.get("/v1/groups/{slug}")
async def get_group(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await group_view(session, slug)
