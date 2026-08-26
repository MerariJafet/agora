"""World API (S3-T04): versioned cacheable topology + semantic population.

Topology and presence are deliberately separate endpoints: topology is
immutable-until-version-bump (ETag/304 forever), population is ephemeral
(Redis aggregate, never per-agent DB queries, never heartbeat-level data).
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.authz import CurrentDevice
from agora_api.avatars import avatar_for
from agora_api.db import get_session
from agora_api.errors import NotFound
from agora_api.models import Agent, Mission, RecordProvenance
from agora_api.presence import list_present
from agora_api.provenance import visible_record_condition
from agora_api.rule_delivery import (
    attest_rule_delivery,
    mark_rule_seen,
    pending_rules_for_agent,
    rule_view,
)
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


@router.get("/rules/feed")
async def world_rule_feed(
    device: CurrentDevice,
    after_sequence: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rules = await pending_rules_for_agent(
        session,
        agent_id=device.agent_id,
        device_id=device.device_id,
        after_sequence=after_sequence,
    )
    await session.commit()
    return {
        "agent_id": device.agent_id,
        "device_id": device.device_id,
        "protocol_version": "world-rules-feed.v1",
        "rules": [rule_view(rule) for rule in rules],
    }


@router.post("/rules/cursor")
async def world_rule_cursor(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    from agora_api.errors import ValidationFailed

    if not isinstance(body, dict):
        raise ValidationFailed("Expected JSON object.")
    unknown = set(body) - {"rule_id", "sequence_number"}
    if unknown:
        raise ValidationFailed("Unknown fields rejected.")
    if not isinstance(body.get("rule_id"), str) or not isinstance(
        body.get("sequence_number"), int
    ):
        raise ValidationFailed("rule_id and sequence_number are required.")
    state = await mark_rule_seen(
        session,
        agent_id=device.agent_id,
        rule_id=body["rule_id"],
        sequence_number=body["sequence_number"],
    )
    await session.commit()
    return {
        "agent_id": state.agent_id,
        "rule_id": state.rule_id,
        "technical_state": state.technical_state,
    }


@router.post("/rules/attest-versioned")
async def world_rule_attest_versioned(
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    from agora_api.errors import ValidationFailed

    body = await request.json()
    if not isinstance(body, dict):
        raise ValidationFailed("Expected JSON object.")
    unknown = set(body) - {
        "rule_id",
        "canonical_hash",
        "decision",
        "technical_cause",
        "runtime_version",
        "runtime_protocol_version",
        "verification_result",
        "attested_at",
        "world_instance_id",
        "sequence_number",
    }
    if unknown:
        raise ValidationFailed("Unknown fields rejected.")
    if not all(isinstance(body.get(key), str) for key in ("rule_id", "canonical_hash", "decision")):
        raise ValidationFailed("rule_id, canonical_hash and decision are required.")
    if body.get("technical_cause") is not None and not isinstance(body["technical_cause"], str):
        raise ValidationFailed("technical_cause must be a string.")
    runtime_fields = (
        "runtime_version",
        "runtime_protocol_version",
        "verification_result",
        "attested_at",
    )
    for key in runtime_fields:
        if body.get(key) is not None and not isinstance(body[key], str):
            raise ValidationFailed(f"{key} must be a string.")
    if body.get("world_instance_id") is not None and not isinstance(body["world_instance_id"], str):
        raise ValidationFailed("world_instance_id must be a string.")
    if body.get("sequence_number") is not None and not isinstance(body["sequence_number"], int):
        raise ValidationFailed("sequence_number must be an integer.")
    state = await attest_rule_delivery(
        session,
        agent_id=device.agent_id,
        rule_id=body["rule_id"],
        canonical_hash=body["canonical_hash"],
        decision=body["decision"],
        technical_cause=body.get("technical_cause"),
        runtime_version=body.get("runtime_version"),
        runtime_protocol_version=body.get("runtime_protocol_version"),
        verification_result=body.get("verification_result"),
        attestation_metadata={
            key: body[key]
            for key in ("attested_at", "world_instance_id", "sequence_number")
            if key in body
        },
    )
    await session.commit()
    return {
        "agent_id": state.agent_id,
        "rule_id": state.rule_id,
        "technical_state": state.technical_state,
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
                visible_record_condition("missions", Mission.mission_id),
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
                    visible_record_condition("agents", Agent.agent_id),
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
