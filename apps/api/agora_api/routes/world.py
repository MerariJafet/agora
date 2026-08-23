"""World API (S3-T04): versioned cacheable topology + semantic population.

Topology and presence are deliberately separate endpoints: topology is
immutable-until-version-bump (ETag/304 forever), population is ephemeral
(Redis aggregate, never per-agent DB queries, never heartbeat-level data).
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.avatars import avatar_for
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.models import Agent
from agora_api.presence import list_present
from agora_api.world import build_manifest, manifest_etag, space_ids

router = APIRouter(prefix="/v1/world", tags=["world"])


@router.get("/manifest", response_model=None)
async def world_manifest(request: Request, response: Response) -> dict | Response:
    manifest = build_manifest()
    etag = manifest_etag(manifest)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"etag": etag,
                                                  "cache-control": "public, max-age=60"})
    response.headers["etag"] = etag
    # Short max-age + revalidation: a world-version bump invalidates instantly
    # while steady-state clients never re-download the topology body.
    response.headers["cache-control"] = "public, max-age=60, must-revalidate"
    return manifest


@router.get("/population")
async def world_population(session: AsyncSession = Depends(get_session)) -> dict:
    """Semantic population summary + the visible agents' public world state.
    Two queries total regardless of agent count (no N+1)."""
    per_space: dict[str, list[dict]] = {}
    present_ids: set[str] = set()
    for space_id in space_ids().values():
        entries = await list_present(space_id)
        per_space[space_id] = entries
        present_ids.update(e["agent_id"] for e in entries)

    agents: dict[str, Agent] = {}
    if present_ids:
        rows = (
            await session.execute(select(Agent).where(Agent.agent_id.in_(present_ids)))
        ).scalars().all()
        agents = {a.agent_id: a for a in rows}

    def public_state(agent_id: str) -> dict:
        agent = agents.get(agent_id)
        return {
            "agent_id": agent_id,
            "name": agent.name if agent else agent_id,
            "activity": agent.activity if agent else "idle",
            "avatar": avatar_for(agent_id, agent.avatar if agent else None),
        }

    return {
        "spaces": {
            space_id: {
                "count": len(entries),
                "agents": [public_state(e["agent_id"]) for e in entries],
            }
            for space_id, entries in per_space.items()
        },
        "total_present": len(present_ids),
    }


@router.get("/agents/{agent_id}/state")
async def agent_world_state(
    agent_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    from agora_api.presence import current_space

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "activity": agent.activity,
        "avatar": avatar_for(agent.agent_id, agent.avatar),
        "current_space_id": await current_space(agent.agent_id),
    }
