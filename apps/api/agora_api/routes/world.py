"""World API (S3-T04): versioned cacheable topology + semantic population.

Topology and presence are deliberately separate endpoints: topology is
immutable-until-version-bump (ETag/304 forever), population is ephemeral
(Redis aggregate, never per-agent DB queries, never heartbeat-level data).
"""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.avatars import avatar_for
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.models import Agent, Mission, RecordProvenance
from agora_api.presence import list_present
from agora_api.provenance import public_provenance_classes
from agora_api.world import build_manifest, manifest_etag, space_ids
from agora_api.world_rules import (
    WORLD_RULES_VERSION,
    mark_world_rules_attested,
    validate_world_rules_attestation,
    world_rules_payload,
)
from agora_api.world_signing import sign_manifest, trust_bootstrap

router = APIRouter(prefix="/v1/world", tags=["world"])

@router.get("/rules")
async def world_rules() -> dict:
    """Rules handed to a local Bridge before it enters the public world.

    This is a contract, not a remote permission grant. The owner-side Bridge
    must keep its own LocalPolicyEngine as the final authority.
    """
    return world_rules_payload()


@router.post("/rules/attest")
async def attest_world_rules(request: Request, device: CurrentDevice) -> dict:
    body = await request.json()
    validate_world_rules_attestation(body)
    await mark_world_rules_attested(device.device_id)
    return {
        "accepted": True,
        "rules_version": WORLD_RULES_VERSION,
        "agent_id": device.agent_id,
        "device_id": device.device_id,
        "message": "World rules attested. Local policy remains authoritative.",
    }


async def _challenge_landmarks(session: AsyncSession) -> list[dict]:
    rows = (
        await session.execute(
            select(Mission)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "missions")
                & (RecordProvenance.record_id == Mission.mission_id),
            )
            .where(
                Mission.challenge_kind.is_not(None),
                Mission.state.in_(["forming", "active", "review"]),
                Mission.hosting_space_id.is_not(None),
                RecordProvenance.provenance_class.in_(public_provenance_classes()),
            )
        )
    ).scalars().all()
    landmarks = []
    for index, mission in enumerate(rows):
        angle = -0.25 + index * 0.38
        landmarks.append(
            {
                "id": f"challenge-{mission.mission_id[-8:].lower()}",
                "name": mission.title,
                "state": "ACTIVE",
                "space_id": mission.hosting_space_id,
                "purpose": mission.objective,
                "shape": "challenge",
                "x": int(980 + index * 120),
                "y": int(620 + index * 170 + angle * 30),
                "radius": 160,
                "color": mission.challenge_space_color or "#35d0ff",
                "mission_id": mission.mission_id,
                "deadline_at": mission.deadline_at.isoformat() if mission.deadline_at else None,
                "reward_aceros": mission.reward_aceros,
                "challenge_kind": mission.challenge_kind,
            }
        )
    return landmarks


@router.get("/manifest", response_model=None)
async def world_manifest(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict | Response:
    manifest = sign_manifest(build_manifest(await _challenge_landmarks(session)))
    etag = manifest_etag(manifest)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"etag": etag,
                                                  "cache-control": "public, max-age=60"})
    response.headers["etag"] = etag
    # Short max-age + revalidation: a world-version bump invalidates instantly
    # while steady-state clients never re-download the topology body.
    response.headers["cache-control"] = "public, max-age=60, must-revalidate"
    return manifest


@router.get("/trust-bootstrap")
async def world_trust_bootstrap() -> dict:
    return trust_bootstrap()


@router.get("/population")
async def world_population(session: AsyncSession = Depends(get_session)) -> dict:
    """Semantic population summary + the visible agents' public world state.
    Two queries total regardless of agent count (no N+1)."""
    per_space: dict[str, list[dict]] = {}
    present_ids: set[str] = set()
    for space_id in space_ids(await _challenge_landmarks(session)).values():
        entries = await list_present(space_id)
        per_space[space_id] = entries
        present_ids.update(e["agent_id"] for e in entries)

    agents: dict[str, Agent] = {}
    if present_ids:
        rows = (
            await session.execute(
                select(Agent)
                .outerjoin(
                    RecordProvenance,
                    (RecordProvenance.record_table == "agents")
                    & (RecordProvenance.record_id == Agent.agent_id),
                )
                .where(
                    Agent.agent_id.in_(present_ids),
                    RecordProvenance.provenance_class.in_(public_provenance_classes()),
                )
            )
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

    spaces = {}
    for space_id, entries in per_space.items():
        visible_agent_ids = [
            e["agent_id"] for e in entries if e["agent_id"] in agents
        ]
        spaces[space_id] = {
            "count": len(visible_agent_ids),
            "agents": [public_state(agent_id) for agent_id in visible_agent_ids],
        }

    return {
        "spaces": spaces,
        "total_present": sum(space["count"] for space in spaces.values()),
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
