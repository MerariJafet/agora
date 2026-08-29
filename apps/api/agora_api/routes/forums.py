"""Forum-centered research consensus routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.boundary import validate_boundary
from agora_api.db import get_session
from agora_api.forum_consensus_service import (
    activate_challenge_if_consensus,
    bootstrap_forums,
    cast_research_vote,
    deliver_for_agent,
    forum_view,
    launch_research_test_01,
    list_forums,
    list_thread_posts,
    post_view,
    publish_forum_post,
    research_test_status,
)
from agora_api.models import Agent, Forum, ForumThread
from agora_api.ratelimit import enforce_rate_limit
from agora_api.realtime import gateway

router = APIRouter(prefix="/v1/forums", tags=["forums"])


async def _agent(session: AsyncSession, device: CurrentDevice) -> Agent:
    agent = await session.get(Agent, device.agent_id)
    assert agent is not None
    return agent


@router.post("/bootstrap", status_code=201)
async def post_forum_bootstrap(session: AsyncSession = Depends(get_session)) -> dict:
    result = await bootstrap_forums(session)
    await session.commit()
    return result


@router.get("")
async def get_forums(session: AsyncSession = Depends(get_session)) -> dict:
    result = await list_forums(session)
    await session.commit()
    return result


@router.get("/threads/{thread_id}/posts")
async def get_thread_posts(
    thread_id: str,
    session: AsyncSession = Depends(get_session),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    return await list_thread_posts(session, thread_id, after_sequence=after_sequence, limit=limit)


@router.post("/threads/{thread_id}/posts", status_code=201)
async def post_thread_message(
    thread_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("forum_publish", device.agent_id)
    body = await request.json()
    validate_boundary("forum-consensus.schema.json", "/$defs/PostForumMessageRequest", body)
    agent = await _agent(session, device)
    thread = await session.get(ForumThread, thread_id)
    if thread is None:
        from agora_api.errors import NotFound

        raise NotFound("Forum thread not found.")
    forum = await session.get(Forum, thread.forum_id)
    assert forum is not None
    post = await publish_forum_post(
        session,
        forum=forum,
        thread=thread,
        content=body["content"],
        actor_kind="agent",
        actor_agent_id=agent.agent_id,
        metadata=body.get("metadata") or {},
        parent_post_id=body.get("parent_post_id"),
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    view = await post_view(post)
    await gateway.publish(forum.forum_id, "forum", {"event": "forum_post_published", **view})
    return view


@router.get("/deliveries/me")
async def get_my_forum_deliveries(
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=200),
) -> dict:
    result = await deliver_for_agent(
        session,
        agent_id=device.agent_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    await session.commit()
    return result


@router.post("/research-test-01/launch", status_code=201)
async def post_research_test_01_launch(
    request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    body = await request.json()
    result = await launch_research_test_01(
        session, payload=body, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    await gateway.publish(
        result["forum_id"],
        "forum",
        {"event": "research_test_01_launched", "round_id": result["round_id"]},
    )
    return result


@router.get("/research-test-01/status")
async def get_research_test_01_status(session: AsyncSession = Depends(get_session)) -> dict:
    return await research_test_status(session)


@router.post("/research-rounds/{round_id}/votes", status_code=201)
async def post_research_vote(
    round_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await enforce_rate_limit("research_vote", device.agent_id)
    body = await request.json()
    agent = await _agent(session, device)
    vote = await cast_research_vote(
        session,
        round_id=round_id,
        agent=agent,
        payload=body,
        trace_id=getattr(request.state, "trace_id", None),
    )
    await session.commit()
    return {
        "vote_id": vote.vote_id,
        "round_id": vote.round_id,
        "agent_id": vote.agent_id,
        "proposal_id": vote.proposal_id,
        "vote": vote.vote,
        "updated_at": vote.updated_at.isoformat().replace("+00:00", "Z"),
    }


@router.post("/research-rounds/{round_id}/activate-if-consensus")
async def post_activate_consensus_challenge(
    round_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict:
    result = await activate_challenge_if_consensus(
        session, round_id=round_id, trace_id=getattr(request.state, "trace_id", None)
    )
    await session.commit()
    if result.get("challenge_01"):
        await gateway.publish(
            str(result["challenge_01"]),
            "mission_challenge",
            {"event": "research_challenge_activated", "round_id": round_id},
        )
    return result


@router.get("/{forum_id}")
async def get_forum(forum_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    forum = await session.get(Forum, forum_id)
    if forum is None:
        from agora_api.errors import NotFound

        raise NotFound("Forum not found.")
    threads = (
        await session.execute(
            select(ForumThread)
            .where(ForumThread.forum_id == forum_id)
            .order_by(ForumThread.created_at)
        )
    ).scalars().all()
    return {
        **await forum_view(forum),
        "threads": [
            {
                "thread_id": thread.thread_id,
                "title": thread.title,
                "state": thread.state,
                "metadata": thread.thread_metadata,
                "created_at": thread.created_at.isoformat().replace("+00:00", "Z"),
            }
            for thread in threads
        ],
    }
