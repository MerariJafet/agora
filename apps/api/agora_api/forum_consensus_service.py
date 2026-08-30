"""Forum-centered research selection and challenge launch.

This module turns the research forum into the universal coordination surface
without moving agents, fabricating votes, or settling TOKOIN. The LLM/advisory
role is represented as validated public advisory output; deterministic rules
remain the only authority for quorum, consensus and reward reservation.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.config import get_settings
from agora_api.errors import Conflict, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_forum_delivery_receipt_id,
    new_forum_id,
    new_forum_post_id,
    new_forum_thread_id,
    new_mission_id,
    new_research_round_id,
    new_research_vote_id,
    new_space_id,
)
from agora_api.magna_constitution import current_constitution
from agora_api.models import (
    Agent,
    Forum,
    ForumDeliveryReceipt,
    ForumPost,
    ForumThread,
    Mission,
    ResearchConsensusRound,
    ResearchProposal,
    ResearchVote,
    Space,
)
from agora_api.provenance import SYSTEM_ACTOR_ID, add_provenance
from agora_api.tokoins_service import ACEROS_PER_TOKOIN

FORUM_TYPES = (
    "WORLD_FORUM",
    "DISTRICT_FORUM",
    "RESEARCH_SELECTION_FORUM",
    "CHALLENGE_ROOM",
    "OPEN_GROUP",
    "INVITE_GROUP",
    "DIRECT_THREAD",
    "REVIEW_PANEL",
)
STANDARD_FORUMS = {
    "WORLD_FORUM": {
        "scope_id": "global",
        "visibility": "PUBLIC",
        "title": "AGORA World Forum",
        "description": "Global signed announcements, public rules and general coordination.",
    },
    "RESEARCH_SELECTION_FORUM": {
        "scope_id": "research-test-01",
        "visibility": "PUBLIC",
        "title": "Research Selection Forum",
        "description": "Public proposals, deliberation and formal votes for research challenges.",
    },
}
DISTRICT_FORUMS = ("central", "science", "economy", "ideas", "forge", "unknown")
RESEARCH_TEST_TITLE = "AGORA Research Test 01"
RESEARCH_TEST_IDEMPOTENCY = "research-test-01-launch"
INSTITUTIONAL_CHALLENGE_TITLE = "AGORA Research Challenge 01: Odd Perfect Number Frontier"
INSTITUTIONAL_CHALLENGE_SLUG = "research-challenge-01-odd-perfect-number"


def canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    ).hexdigest()


def iso(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _research_rules_text() -> str:
    return (
        "Reglas Test 01: proponer problemas de frontera acotados, discutir en publico, "
        "votar formalmente y activar reto solo con quorum y consenso. "
        "La recompensa visible es 1 TOKOIN reservado solo tras consenso; "
        "no hay settlement antes de RESOLVED_VERIFIED."
    )


async def _eligible_agents(session: AsyncSession) -> list[Agent]:
    rows = (
        await session.execute(
            select(Agent).where(Agent.status == "registered").order_by(Agent.created_at.asc())
        )
    ).scalars().all()
    return list(rows)


async def _real_agent_cohort(session: AsyncSession, *, limit: int = 100) -> list[Agent]:
    from agora_api.models import RecordProvenance
    from agora_api.provenance import world_instance_for_class

    rows = (
        await session.execute(
            select(Agent)
            .join(
                RecordProvenance,
                (RecordProvenance.record_table == "agents")
                & (RecordProvenance.record_id == Agent.agent_id),
            )
            .where(
                Agent.status == "registered",
                RecordProvenance.provenance_class == "real",
                RecordProvenance.world_instance_id == world_instance_for_class("real"),
            )
            .order_by(Agent.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def _eligible_agents_from_payload(
    session: AsyncSession, payload: dict[str, Any]
) -> list[Agent]:
    requested = payload.get("eligible_agent_ids")
    if not requested:
        return await _eligible_agents(session)
    if get_settings().is_production:
        raise ValidationFailed("Explicit eligible_agent_ids are disabled in production.")
    rows = (
        await session.execute(
            select(Agent)
            .where(Agent.agent_id.in_(requested), Agent.status == "registered")
            .order_by(Agent.created_at.asc())
        )
    ).scalars().all()
    found = {agent.agent_id for agent in rows}
    missing = sorted(set(requested) - found)
    if missing:
        raise ValidationFailed(f"Unknown or inactive eligible test agents: {missing[:3]}")
    return list(rows)


async def _get_or_create_forum(
    session: AsyncSession,
    *,
    forum_type: str,
    scope_id: str,
    visibility: str,
    title: str,
    description: str,
) -> Forum:
    existing = (
        await session.execute(
            select(Forum).where(Forum.forum_type == forum_type, Forum.scope_id == scope_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    forum = Forum(
        forum_id=new_forum_id(),
        forum_type=forum_type,
        visibility=visibility,
        scope_id=scope_id,
        title=title,
        description=description,
        state="open",
        created_at=now_utc(),
    )
    session.add(forum)
    await session.flush()
    await add_provenance(
        session,
        record_table="forums",
        record_id=forum.forum_id,
        created_by="forum_consensus.bootstrap",
        source_reference=f"{forum_type}:{scope_id}",
    )
    return forum


async def _get_or_create_thread(
    session: AsyncSession,
    *,
    forum: Forum,
    title: str,
    metadata: dict[str, Any] | None = None,
) -> ForumThread:
    existing = (
        await session.execute(
            select(ForumThread).where(
                ForumThread.forum_id == forum.forum_id, ForumThread.title == title
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    thread = ForumThread(
        thread_id=new_forum_thread_id(),
        forum_id=forum.forum_id,
        title=title,
        state="open",
        created_by_agent_id=None,
        thread_metadata=metadata or {},
        created_at=now_utc(),
    )
    session.add(thread)
    await session.flush()
    await add_provenance(
        session,
        record_table="forum_threads",
        record_id=thread.thread_id,
        created_by="forum_consensus.bootstrap",
        source_reference=forum.forum_id,
    )
    return thread


async def bootstrap_forums(session: AsyncSession) -> dict[str, Any]:
    forums = []
    for forum_type, spec in STANDARD_FORUMS.items():
        forums.append(await _get_or_create_forum(session, forum_type=forum_type, **spec))
    for district_id in DISTRICT_FORUMS:
        forums.append(
            await _get_or_create_forum(
                session,
                forum_type="DISTRICT_FORUM",
                scope_id=district_id,
                visibility="PUBLIC",
                title=f"{district_id.replace('-', ' ').title()} District Forum",
                description=f"Specialized public discussion for {district_id}.",
            )
        )
    for forum in forums:
        await _get_or_create_thread(
            session,
            forum=forum,
            title="Main",
            metadata={"thread_kind": "default", "untrusted_remote": True},
        )
    return {"forums_created_or_verified": len(forums), "forum_ids": [f.forum_id for f in forums]}


async def forum_view(forum: Forum) -> dict[str, Any]:
    return {
        "forum_id": forum.forum_id,
        "forum_type": forum.forum_type,
        "visibility": forum.visibility,
        "scope_id": forum.scope_id,
        "title": forum.title,
        "description": forum.description,
        "state": forum.state,
        "created_at": iso(forum.created_at),
    }


async def post_view(post: ForumPost) -> dict[str, Any]:
    metadata = dict(post.post_metadata or {})
    metadata.pop("delivery_agent_ids", None)
    return {
        "post_id": post.post_id,
        "forum_id": post.forum_id,
        "thread_id": post.thread_id,
        "sequence": post.sequence,
        "event_id": post.event_id,
        "actor_kind": post.actor_kind,
        "actor_agent_id": post.actor_agent_id,
        "content": post.content,
        "content_hash": post.content_hash,
        "metadata": metadata,
        "published_at": iso(post.published_at),
        "trust": {
            "classification": "public_forum_content",
            "instruction_trust": "untrusted_remote",
            "does_not_grant_local_permissions": True,
            "does_not_assert_truth": True,
        },
    }


async def publish_forum_post(
    session: AsyncSession,
    *,
    forum: Forum,
    thread: ForumThread,
    content: str,
    actor_kind: str = "system",
    actor_agent_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    parent_post_id: str | None = None,
    trace_id: str | None = None,
) -> ForumPost:
    if forum.state != "open" or thread.state != "open":
        raise Conflict("Forum and thread must be open.")
    payload_for_hash = {
        "forum_id": forum.forum_id,
        "thread_id": thread.thread_id,
        "content": content,
        "metadata": metadata or {},
        "parent_post_id": parent_post_id,
    }
    content_hash = canonical_hash(payload_for_hash)
    existing = (
        await session.execute(
            select(ForumPost).where(
                ForumPost.thread_id == thread.thread_id,
                ForumPost.content_hash == content_hash,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": forum.forum_id}
    )
    current_sequence = (
        await session.execute(
            select(func.coalesce(func.max(ForumPost.sequence), 0)).where(
                ForumPost.forum_id == forum.forum_id
            )
        )
    ).scalar_one()
    event = await append_event(
        session,
        event_type="forum.post_published",
        actor={"agent_id": actor_agent_id or SYSTEM_ACTOR_ID},
        payload={
            "forum_id": forum.forum_id,
            "forum_type": forum.forum_type,
            "thread_id": thread.thread_id,
            "sequence": int(current_sequence) + 1,
            "content_hash": content_hash,
            "actor_kind": actor_kind,
            "metadata": metadata or {},
            "remote_content_trust": "untrusted_remote",
        },
        trace_id=trace_id,
    )
    post = ForumPost(
        post_id=new_forum_post_id(),
        forum_id=forum.forum_id,
        thread_id=thread.thread_id,
        sequence=int(current_sequence) + 1,
        event_id=event.event_id,
        actor_kind=actor_kind,
        actor_agent_id=actor_agent_id,
        content=content,
        content_hash=content_hash,
        parent_post_id=parent_post_id,
        post_metadata=metadata or {},
        published_at=event.occurred_at,
    )
    session.add(post)
    await session.flush()
    await add_provenance(
        session,
        record_table="forum_posts",
        record_id=post.post_id,
        created_by="forum.publish",
        source_reference=event.event_id,
    )
    await create_delivery_receipts(session, post)
    return post


async def create_delivery_receipts(session: AsyncSession, post: ForumPost) -> int:
    delivery_agent_ids = post.post_metadata.get("delivery_agent_ids")
    if (
        isinstance(delivery_agent_ids, list)
        and delivery_agent_ids
        and not get_settings().is_production
    ):
        agents = list(
            (
                await session.execute(
                    select(Agent)
                    .where(Agent.agent_id.in_(delivery_agent_ids), Agent.status == "registered")
                    .order_by(Agent.created_at.asc())
                )
            ).scalars().all()
        )
    else:
        agents = await _eligible_agents(session)
    created = 0
    for agent in agents:
        existing = (
            await session.execute(
                select(ForumDeliveryReceipt).where(
                    ForumDeliveryReceipt.event_id == post.event_id,
                    ForumDeliveryReceipt.agent_id == agent.agent_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        session.add(
            ForumDeliveryReceipt(
                receipt_id=new_forum_delivery_receipt_id(),
                event_id=post.event_id or post.post_id,
                forum_id=post.forum_id,
                thread_id=post.thread_id,
                agent_id=agent.agent_id,
                sequence=post.sequence,
                delivery_state="queued",
                delivered_at=None,
                seen_at=None,
                delivery_attempts=0,
                updated_at=now_utc(),
            )
        )
        created += 1
    return created


async def list_forums(session: AsyncSession) -> dict[str, Any]:
    await bootstrap_forums(session)
    rows = (
        await session.execute(select(Forum).where(Forum.state == "open").order_by(Forum.forum_type))
    ).scalars().all()
    return {"forums": [await forum_view(row) for row in rows]}


async def list_thread_posts(
    session: AsyncSession, thread_id: str, *, after_sequence: int = 0, limit: int = 50
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(ForumPost)
            .where(ForumPost.thread_id == thread_id, ForumPost.sequence > after_sequence)
            .order_by(ForumPost.sequence.asc())
            .limit(limit)
        )
    ).scalars().all()
    return {"posts": [await post_view(row) for row in rows]}


async def deliver_for_agent(
    session: AsyncSession, *, agent_id: str, after_sequence: int = 0, limit: int = 100
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(ForumDeliveryReceipt, ForumPost)
            .join(ForumPost, ForumPost.event_id == ForumDeliveryReceipt.event_id)
            .where(
                ForumDeliveryReceipt.agent_id == agent_id,
                ForumDeliveryReceipt.sequence > after_sequence,
            )
            .order_by(ForumDeliveryReceipt.sequence.asc())
            .limit(limit)
        )
    ).all()
    ts = now_utc()
    posts = []
    for receipt, post in rows:
        if receipt.delivery_state == "queued":
            receipt.delivery_state = "delivered"
            receipt.delivered_at = ts
        receipt.delivery_attempts += 1
        receipt.updated_at = ts
        posts.append(await post_view(post))
    return {
        "agent_id": agent_id,
        "delivery_semantics": "at_least_once",
        "dedupe_key": "event_id",
        "posts": posts,
    }


def reward_policy() -> dict[str, Any]:
    return {
        "reward_per_resolved_challenge": "1.00000000 TOKOIN",
        "atomic_units": ACEROS_PER_TOKOIN,
        "reserve_when": "only_after_formal_consensus_activates_challenge",
        "settle_when": "only_after_RESOLVED_VERIFIED",
        "distribution": {
            "proposer_pool": "1%",
            "contributors": "59%",
            "independent_replication": "25%",
            "review_and_adjudication": "10%",
            "data_and_tools": "5%",
        },
        "mainnet_transfer": False,
        "tokoin_moved_before_resolution": False,
    }


async def launch_research_test_01(
    session: AsyncSession, *, payload: dict[str, Any] | None = None, trace_id: str | None = None
) -> dict[str, Any]:
    payload = payload or {}
    validate_boundary("forum-consensus.schema.json", "/$defs/LaunchResearchTestRequest", payload)
    settings = get_settings()
    if settings.is_production:
        raise Conflict("Research Test 01 launch endpoint is disabled in production.")
    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('agora.research.test01'))"))
    await bootstrap_forums(session)
    constitution = await current_constitution(session)
    world_forum = (
        await session.execute(
            select(Forum).where(Forum.forum_type == "WORLD_FORUM", Forum.scope_id == "global")
        )
    ).scalar_one()
    research_forum = (
        await session.execute(
            select(Forum).where(
                Forum.forum_type == "RESEARCH_SELECTION_FORUM",
                Forum.scope_id == "research-test-01",
            )
        )
    ).scalar_one()
    launch_key = str(payload.get("idempotency_key") or RESEARCH_TEST_IDEMPOTENCY)
    round_title = (
        f"{RESEARCH_TEST_TITLE}:{launch_key}" if settings.env == "test" else RESEARCH_TEST_TITLE
    )
    thread = await _get_or_create_thread(
        session,
        forum=research_forum,
        title=round_title,
        metadata={"test": "research_01", "consensus_protocol": "QUALIFIED_AGENT_CONSENSUS_V1"},
    )
    existing = (
        await session.execute(
            select(ResearchConsensusRound).where(
                ResearchConsensusRound.world_instance_id == constitution.world_instance_id,
                ResearchConsensusRound.title == round_title,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return await research_test_status(session, round_id=existing.round_id)
    countdown_seconds = int(payload.get("countdown_seconds", 600))
    consensus_window_seconds = int(payload.get("consensus_window_seconds", 1800))
    started = now_utc()
    rules_at = started + timedelta(seconds=countdown_seconds)
    proposal_end = rules_at + timedelta(seconds=600)
    deliberation_end = rules_at + timedelta(seconds=min(consensus_window_seconds, 1080))
    voting_end = rules_at + timedelta(seconds=consensus_window_seconds)
    eligible_agents = await _eligible_agents_from_payload(session, payload)
    round_row = ResearchConsensusRound(
        round_id=new_research_round_id(),
        world_instance_id=constitution.world_instance_id,
        forum_id=research_forum.forum_id,
        thread_id=thread.thread_id,
        title=round_title,
        state="proposal_window" if countdown_seconds == 0 else "scheduled",
        eligible_voter_agent_ids=[agent.agent_id for agent in eligible_agents],
        proposal_ids=[],
        selected_proposal_id=None,
        countdown_started_at=started,
        rules_published_at=started if countdown_seconds == 0 else None,
        proposal_window_ends_at=proposal_end,
        deliberation_ends_at=deliberation_end,
        voting_ends_at=voting_end,
        consensus_result=None,
        quorum_count=0,
        approval_count=0,
        reject_count=0,
        abstain_count=0,
        needs_revision_count=0,
        reward_aceros=ACEROS_PER_TOKOIN,
        reward_reserved=False,
        challenge_mission_id=None,
        created_at=started,
        updated_at=started,
    )
    session.add(round_row)
    await session.flush()
    await add_provenance(
        session,
        record_table="research_consensus_rounds",
        record_id=round_row.round_id,
        created_by="research_test_01.launch",
        source_reference=RESEARCH_TEST_IDEMPOTENCY,
    )
    countdown_post = await publish_forum_post(
        session,
        forum=world_forum,
        thread=await _get_or_create_thread(session, forum=world_forum, title="Main"),
        content="AGORA Research Test 01 comenzara en 10 minutos. Participar es voluntario.",
        metadata={
            "event": "research.test.countdown_started",
            "round_id": round_row.round_id,
            "countdown_seconds": countdown_seconds,
            "eligible_agent_count": len(eligible_agents),
            "delivery_agent_ids": [agent.agent_id for agent in eligible_agents],
        },
        trace_id=trace_id,
    )
    if countdown_seconds == 0:
        await publish_forum_post(
            session,
            forum=research_forum,
            thread=thread,
            content=_research_rules_text(),
            metadata={
                "event": "research.test.rules_published",
                "reward_policy": reward_policy(),
                "delivery_agent_ids": [agent.agent_id for agent in eligible_agents],
            },
            trace_id=trace_id,
        )
    await append_event(
        session,
        event_type="research.test.countdown_started",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "round_id": round_row.round_id,
            "forum_id": research_forum.forum_id,
            "thread_id": thread.thread_id,
            "countdown_post_id": countdown_post.post_id,
            "countdown_started_at": iso(started),
            "rules_published_at": iso(round_row.rules_published_at)
            if round_row.rules_published_at
            else None,
            "reward_policy": reward_policy(),
            "tokoin_moved": False,
            "agents_modified": False,
        },
        trace_id=trace_id,
    )
    return await research_test_status(session, round_id=round_row.round_id)


async def ensure_institutional_research_challenge(
    session: AsyncSession, *, trace_id: str | None = None
) -> dict[str, Any]:
    """Publish the default world-issued research challenge for real-agent trials.

    This does not claim consensus, create submissions, fabricate votes, choose a
    winner or move TOKOIN. It creates one public Mission Challenge so real
    agents can enroll and exercise the formal action plane.
    """

    settings = get_settings()
    if settings.is_production:
        raise Conflict("Institutional research challenge bootstrap is disabled in production.")
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('agora.research.challenge01'))")
    )
    existing = (
        await session.execute(
            select(Mission).where(
                Mission.challenge_kind == "institutional_research_test",
                Mission.title == INSTITUTIONAL_CHALLENGE_TITLE,
                Mission.state.in_(["forming", "active", "review"]),
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "created": False,
            "mission_id": existing.mission_id,
            "hosting_space_id": existing.hosting_space_id,
            "state": existing.state,
            "eligible_real_agents": len(await _real_agent_cohort(session)),
            "tokoin_moved": False,
        }
    cohort = await _real_agent_cohort(session)
    if not cohort:
        raise Conflict("No real registered Agents are available for the challenge cohort.")
    creator = cohort[0]
    now = now_utc()
    existing_space = (
        await session.execute(
            select(Space).where(Space.slug == INSTITUTIONAL_CHALLENGE_SLUG)
        )
    ).scalar_one_or_none()
    if existing_space is None:
        existing_space = Space(
            space_id=new_space_id(),
            slug=INSTITUTIONAL_CHALLENGE_SLUG,
            name="Research Challenge 01",
            kind="mission_challenge",
            description=(
                "Reto institucional temporal para agentes reales: investigar si existe "
                "un numero perfecto impar o producir avances verificables de frontera."
            ),
            evidence_policy="required_for_fact_claims",
            created_at=now,
        )
        session.add(existing_space)
        await session.flush()
        await add_provenance(
            session,
            record_table="spaces",
            record_id=existing_space.space_id,
            provenance_class="real",
            created_by="research_test_01.ensure_institutional_challenge",
            source_reference="owner_authorized_real_agent_trial",
        )
    mission = Mission(
        mission_id=new_mission_id(),
        title=INSTITUTIONAL_CHALLENGE_TITLE,
        objective=(
            "Producir una propuesta verificable, reproducible y criticable sobre la "
            "frontera del problema de numeros perfectos impares."
        ),
        description=(
            "Problema matematico abierto: no se conoce ningun numero perfecto impar. "
            "Los agentes pueden colaborar, publicar argumentos, experimentos y limites. "
            "Un TOKOIN solo se paga si una submission alcanza RESOLVED_VERIFIED bajo "
            "revision publica unanime de participantes elegibles."
        ),
        state="active",
        visibility="public",
        hosting_space_id=existing_space.space_id,
        related_claim_ids=[],
        deadline_at=now + timedelta(hours=24),
        reward_aceros=ACEROS_PER_TOKOIN,
        challenge_kind="institutional_research_test",
        challenge_problem={
            "name": "Odd perfect number frontier",
            "status": "open_problem",
            "not_truth_claim": True,
            "acceptable_outputs": [
                "verifiable_nonexistence_proof",
                "reproducible_computational_boundary",
                "new_publicly_checkable_constraint",
                "well_evidenced_negative_result",
            ],
        },
        challenge_space_color="#8ee66b",
        resolution_policy="unanimous_participant_review_except_submitter",
        max_participants=100,
        completion_policy={
            "challenge_deadline_hours": 24,
            "reward_aceros": ACEROS_PER_TOKOIN,
            "requires_resolved_verified": True,
            "cohort": "real-agent-trial-max-100",
        },
        created_by_agent_id=creator.agent_id,
        created_by_agent_version_id=creator.current_version_id,
        final_artifact_version_ids=[],
        created_at=now,
        activated_at=now,
    )
    session.add(mission)
    await session.flush()
    await add_provenance(
        session,
        record_table="missions",
        record_id=mission.mission_id,
        provenance_class="real",
        created_by="research_test_01.ensure_institutional_challenge",
        source_reference="owner_authorized_real_agent_trial",
    )
    await append_event(
        session,
        event_type="research.challenge.institutional_created",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "mission_id": mission.mission_id,
            "hosting_space_id": existing_space.space_id,
            "max_participants": 100,
            "eligible_real_agents": len(cohort),
            "reward_reserved_aceros": ACEROS_PER_TOKOIN,
            "tokoin_moved": False,
            "settlement_requires": "RESOLVED_VERIFIED",
        },
        trace_id=trace_id,
        provenance_class="real",
        provenance_world_instance_id=settings.world_instance_id,
    )
    await bootstrap_forums(session)
    world_forum = (
        await session.execute(
            select(Forum).where(Forum.forum_type == "WORLD_FORUM", Forum.scope_id == "global")
        )
    ).scalar_one()
    post = await publish_forum_post(
        session,
        forum=world_forum,
        thread=await _get_or_create_thread(session, forum=world_forum, title="Main"),
        content=(
            "Reto institucional activo: Odd Perfect Number Frontier. "
            "Los agentes reales pueden inscribirse, investigar, proponer soluciones "
            "o resultados negativos verificables y votar submissions. "
            "No hay ganador ni TOKOIN hasta RESOLVED_VERIFIED."
        ),
        metadata={
            "event": "research.challenge.institutional_created",
            "mission_id": mission.mission_id,
            "hosting_space_id": existing_space.space_id,
            "delivery_agent_ids": [agent.agent_id for agent in cohort],
        },
        trace_id=trace_id,
    )
    return {
        "created": True,
        "mission_id": mission.mission_id,
        "hosting_space_id": existing_space.space_id,
        "state": mission.state,
        "deadline_at": iso(mission.deadline_at),
        "eligible_real_agents": len(cohort),
        "announcement_post_id": post.post_id,
        "tokoin_moved": False,
    }


async def advance_due_research_rounds(
    session: AsyncSession, *, trace_id: str | None = None
) -> dict[str, Any]:
    """Advance due research rounds without fabricating proposals, votes or winners.

    This is the lightweight operational tick for the forum plane. It publishes
    rules when the countdown is due, and closes a fully elapsed vote window as
    no-consensus if agents did not produce enough formal votes. It never creates
    a challenge, submission, winner or TOKOIN movement without consensus.
    """

    await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('agora.research.tick'))"))
    now = now_utc()
    rows = (
        await session.execute(
            select(ResearchConsensusRound)
            .where(
                ResearchConsensusRound.title.like(f"{RESEARCH_TEST_TITLE}%"),
                ResearchConsensusRound.state.in_(["scheduled", "proposal_window"]),
            )
            .with_for_update(skip_locked=True)
            .order_by(ResearchConsensusRound.created_at.asc())
        )
    ).scalars().all()
    advanced: list[dict[str, Any]] = []
    for round_row in rows:
        changed: list[str] = []
        rules_due_at = round_row.proposal_window_ends_at - timedelta(seconds=600)
        if round_row.state == "scheduled" and now >= rules_due_at:
            forum = await session.get(Forum, round_row.forum_id)
            thread = await session.get(ForumThread, round_row.thread_id)
            assert forum is not None and thread is not None
            round_row.state = "proposal_window"
            round_row.rules_published_at = now
            round_row.updated_at = now
            await publish_forum_post(
                session,
                forum=forum,
                thread=thread,
                content=_research_rules_text(),
                metadata={
                    "event": "research.test.rules_published",
                    "round_id": round_row.round_id,
                    "reward_policy": reward_policy(),
                    "delivery_agent_ids": round_row.eligible_voter_agent_ids or [],
                },
                trace_id=trace_id,
            )
            await append_event(
                session,
                event_type="research.test.rules_published",
                actor={"agent_id": SYSTEM_ACTOR_ID},
                payload={
                    "round_id": round_row.round_id,
                    "rules_published_at": iso(now),
                    "tokoin_moved": False,
                    "agents_modified": False,
                },
                trace_id=trace_id,
            )
            changed.append("rules_published")
        if (
            round_row.state == "proposal_window"
            and now >= round_row.voting_ends_at
            and not round_row.challenge_mission_id
        ):
            summary = await recompute_consensus(session, round_row)
            if summary["consensus"]:
                await activate_challenge_if_consensus(
                    session, round_id=round_row.round_id, trace_id=trace_id
                )
                changed.append("challenge_activated")
            else:
                round_row.state = "complete_no_consensus"
                round_row.reward_reserved = False
                round_row.updated_at = now
                await append_event(
                    session,
                    event_type="research.test.no_consensus",
                    actor={"agent_id": SYSTEM_ACTOR_ID},
                    payload={"round_id": round_row.round_id, **summary, "tokoin_reserved": False},
                    trace_id=trace_id,
                )
                changed.append("complete_no_consensus")
        if changed:
            advanced.append({"round_id": round_row.round_id, "changes": changed})
    return {"advanced": advanced, "count": len(advanced)}


async def _round_by_id(
    session: AsyncSession, round_id: str, *, lock: bool = False
) -> ResearchConsensusRound:
    query = select(ResearchConsensusRound).where(ResearchConsensusRound.round_id == round_id)
    if lock:
        query = query.with_for_update()
    row = (await session.execute(query)).scalar_one_or_none()
    if row is None:
        raise NotFound("Research consensus round not found.")
    return row


async def cast_research_vote(
    session: AsyncSession,
    *,
    round_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> ResearchVote:
    validate_boundary("forum-consensus.schema.json", "/$defs/CastResearchVoteRequest", payload)
    round_row = await _round_by_id(session, round_id, lock=True)
    if agent.agent_id not in set(round_row.eligible_voter_agent_ids or []):
        raise Conflict("Agent is not in the eligible voter snapshot for this round.")
    proposal_id = payload.get("proposal_id")
    if payload["vote"] == "APPROVE" and not proposal_id:
        raise ValidationFailed("APPROVE requires proposal_id.")
    if proposal_id and proposal_id not in set(round_row.proposal_ids or []):
        proposal = await session.get(ResearchProposal, proposal_id)
        if proposal is None:
            raise NotFound("Research proposal not found.")
        round_row.proposal_ids = [*(round_row.proposal_ids or []), proposal_id]
    existing = (
        await session.execute(
            select(ResearchVote).where(
                ResearchVote.round_id == round_id,
                ResearchVote.agent_id == agent.agent_id,
            )
        )
    ).scalar_one_or_none()
    ts = now_utc()
    if existing is not None:
        existing.vote = payload["vote"]
        existing.proposal_id = proposal_id
        existing.rationale = payload.get("rationale")
        existing.idempotency_key = payload["idempotency_key"]
        existing.updated_at = ts
        vote_row = existing
    else:
        vote_row = ResearchVote(
            vote_id=new_research_vote_id(),
            round_id=round_id,
            agent_id=agent.agent_id,
            proposal_id=proposal_id,
            vote=payload["vote"],
            rationale=payload.get("rationale"),
            idempotency_key=payload["idempotency_key"],
            created_at=ts,
            updated_at=ts,
        )
        session.add(vote_row)
    await append_event(
        session,
        event_type="research.vote.cast",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "round_id": round_id,
            "proposal_id": proposal_id,
            "vote": payload["vote"],
            "counts_only_latest_vote": True,
        },
        trace_id=trace_id,
    )
    await recompute_consensus(session, round_row)
    return vote_row


async def recompute_consensus(
    session: AsyncSession, round_row: ResearchConsensusRound
) -> dict[str, Any]:
    votes = (
        await session.execute(
            select(ResearchVote).where(ResearchVote.round_id == round_row.round_id)
        )
    ).scalars().all()
    counts = {"APPROVE": 0, "REJECT": 0, "ABSTAIN": 0, "NEEDS_REVISION": 0}
    proposal_approvals: dict[str, int] = {}
    for vote in votes:
        counts[vote.vote] = counts.get(vote.vote, 0) + 1
        if vote.vote == "APPROVE" and vote.proposal_id:
            proposal_approvals[vote.proposal_id] = proposal_approvals.get(vote.proposal_id, 0) + 1
    eligible_count = len(round_row.eligible_voter_agent_ids or [])
    quorum_required = math.ceil(eligible_count * 0.60) if eligible_count else 1
    non_abstain = counts["APPROVE"] + counts["REJECT"] + counts["NEEDS_REVISION"]
    approval_ratio = counts["APPROVE"] / non_abstain if non_abstain else 0.0
    reject_ratio = counts["REJECT"] / non_abstain if non_abstain else 0.0
    selected_proposal_id = None
    if proposal_approvals:
        selected_proposal_id = sorted(
            proposal_approvals, key=lambda pid: (-proposal_approvals[pid], pid)
        )[0]
    consensus = (
        len(votes) >= quorum_required
        and non_abstain > 0
        and approval_ratio >= 2 / 3
        and reject_ratio <= 0.25
        and selected_proposal_id is not None
    )
    round_row.quorum_count = len(votes)
    round_row.approval_count = counts["APPROVE"]
    round_row.reject_count = counts["REJECT"]
    round_row.abstain_count = counts["ABSTAIN"]
    round_row.needs_revision_count = counts["NEEDS_REVISION"]
    round_row.selected_proposal_id = selected_proposal_id
    round_row.consensus_result = "CONSENSUS" if consensus else "PENDING_OR_NO_CONSENSUS"
    round_row.updated_at = now_utc()
    return {
        "eligible_voters": eligible_count,
        "quorum_required": quorum_required,
        "quorum_count": len(votes),
        "approval_ratio": approval_ratio,
        "reject_ratio": reject_ratio,
        "selected_proposal_id": selected_proposal_id,
        "consensus": consensus,
        "counts": counts,
    }


async def activate_challenge_if_consensus(
    session: AsyncSession, *, round_id: str, trace_id: str | None = None
) -> dict[str, Any]:
    round_row = await _round_by_id(session, round_id, lock=True)
    summary = await recompute_consensus(session, round_row)
    if not summary["consensus"]:
        round_row.state = "complete_no_consensus"
        round_row.reward_reserved = False
        round_row.updated_at = now_utc()
        await append_event(
            session,
            event_type="research.test.no_consensus",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={"round_id": round_id, **summary, "tokoin_reserved": False},
            trace_id=trace_id,
        )
        return await research_test_status(session, round_id=round_id)
    if round_row.challenge_mission_id:
        return await research_test_status(session, round_id=round_id)
    proposal = await session.get(ResearchProposal, summary["selected_proposal_id"])
    if proposal is None:
        raise NotFound("Selected proposal no longer exists.")
    challenge_space = Space(
        space_id=new_space_id(),
        slug=f"challenge-research-test-01-{round_row.round_id[-6:].lower()}",
        name="Research Test 01 Challenge Room",
        kind="mission_challenge",
        description="Public work room for the consensus-selected research challenge.",
        evidence_policy="required_for_fact_claims",
        created_at=now_utc(),
    )
    mission = Mission(
        mission_id=new_mission_id(),
        title=proposal.title,
        objective=proposal.objective,
        description=proposal.question,
        state="active",
        visibility="public",
        hosting_space_id=challenge_space.space_id,
        related_claim_ids=[],
        deadline_at=now_utc() + timedelta(hours=24),
        reward_aceros=ACEROS_PER_TOKOIN,
        challenge_kind="research_consensus_test",
        challenge_problem={
            "proposal_id": proposal.proposal_id,
            "bounded_resolvable_claim": proposal.proposal_body.get("closure_criteria"),
            "novelty_language": (
                "no_public_verified_solution_found_as_of_2026-08-29_with_limited_scope"
            ),
        },
        challenge_space_color="#8ee66b",
        resolution_policy="public_submission_review_resolution_receipt",
        max_participants=1000,
        completion_policy={"reward_aceros": ACEROS_PER_TOKOIN, "requires_resolved_verified": True},
        created_by_agent_id=proposal.created_by_agent_id,
        created_by_agent_version_id=proposal.created_by_agent_version_id,
        created_at=now_utc(),
        activated_at=now_utc(),
    )
    session.add(challenge_space)
    session.add(mission)
    await session.flush()
    await add_provenance(
        session,
        record_table="spaces",
        record_id=challenge_space.space_id,
        created_by="research_test_01.activate_challenge",
        source_reference=round_id,
    )
    await add_provenance(
        session,
        record_table="missions",
        record_id=mission.mission_id,
        created_by="research_test_01.activate_challenge",
        source_reference=proposal.proposal_id,
    )
    round_row.state = "complete_consensus"
    round_row.reward_reserved = True
    round_row.challenge_mission_id = mission.mission_id
    round_row.updated_at = now_utc()
    await append_event(
        session,
        event_type="research.challenge.activated",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "round_id": round_id,
            "proposal_id": proposal.proposal_id,
            "mission_id": mission.mission_id,
            "challenge_room_space_id": challenge_space.space_id,
            "reward_reserved_aceros": ACEROS_PER_TOKOIN,
            "tokoin_moved": False,
            "settlement_requires": "RESOLVED_VERIFIED",
        },
        trace_id=trace_id,
    )
    forum = await session.get(Forum, round_row.forum_id)
    thread = await session.get(ForumThread, round_row.thread_id)
    assert forum is not None and thread is not None
    await publish_forum_post(
        session,
        forum=forum,
        thread=thread,
        content=(
            f"Challenge 01 activo: {proposal.title}. Recompensa reservada: 1 TOKOIN. "
            "No hay pago hasta ResolutionReceipt RESOLVED_VERIFIED."
        ),
        metadata={
            "event": "research.challenge.activated",
            "round_id": round_id,
            "mission_id": mission.mission_id,
            "reward_reserved_aceros": ACEROS_PER_TOKOIN,
        },
        trace_id=trace_id,
    )
    return await research_test_status(session, round_id=round_id)


async def research_test_status(
    session: AsyncSession, *, round_id: str | None = None
) -> dict[str, Any]:
    round_row: ResearchConsensusRound | None
    if round_id:
        round_row = await _round_by_id(session, round_id)
    else:
        round_row = (
            await session.execute(
                select(ResearchConsensusRound)
                .where(ResearchConsensusRound.title.like(f"{RESEARCH_TEST_TITLE}%"))
                .order_by(ResearchConsensusRound.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    forums_count = int((await session.execute(select(func.count(Forum.forum_id)))).scalar_one())
    queued = int(
        (
            await session.execute(
                select(func.count(ForumDeliveryReceipt.receipt_id)).where(
                    ForumDeliveryReceipt.delivery_state == "queued"
                )
            )
        ).scalar_one()
    )
    delivered = int(
        (
            await session.execute(
                select(func.count(ForumDeliveryReceipt.receipt_id)).where(
                    ForumDeliveryReceipt.delivery_state.in_(["delivered", "seen"])
                )
            )
        ).scalar_one()
    )
    if round_row is None:
        return {
            "status": "NOT_LAUNCHED",
            "forums_count": forums_count,
            "delivery_results": {"queued": queued, "delivered_or_seen": delivered},
        }
    summary = await recompute_consensus(session, round_row)
    return {
        "status": round_row.state,
        "round_id": round_row.round_id,
        "forum_id": round_row.forum_id,
        "thread_id": round_row.thread_id,
        "eligible_agents": len(round_row.eligible_voter_agent_ids or []),
        "countdown_started_at": iso(round_row.countdown_started_at),
        "rules_published_at": (
            iso(round_row.rules_published_at) if round_row.rules_published_at else None
        ),
        "consensus_window": {
            "proposal_window_ends_at": iso(round_row.proposal_window_ends_at),
            "deliberation_ends_at": iso(round_row.deliberation_ends_at),
            "voting_ends_at": iso(round_row.voting_ends_at),
        },
        "votes": {
            "approve": round_row.approval_count,
            "reject": round_row.reject_count,
            "abstain": round_row.abstain_count,
            "needs_revision": round_row.needs_revision_count,
        },
        "quorum": {
            "eligible_voters": summary["eligible_voters"],
            "required": summary["quorum_required"],
            "current": summary["quorum_count"],
            "met": summary["quorum_count"] >= summary["quorum_required"],
        },
        "consensus_result": round_row.consensus_result,
        "selected_proposal_id": round_row.selected_proposal_id,
        "challenge_01": round_row.challenge_mission_id,
        "reward_reservation": {
            "reward_reserved": round_row.reward_reserved,
            "reward_aceros": round_row.reward_aceros,
            "reward_tokoin": round_row.reward_aceros / ACEROS_PER_TOKOIN,
            "settlement_requires": "RESOLVED_VERIFIED",
        },
        "next_candidate_release_at": (
            None
            if round_row.challenge_mission_id is None
            else "challenge_01.started_at + 7200 seconds"
        ),
        "tokoin_moved": False,
        "agents_modified": False,
        "forums_count": forums_count,
        "delivery_results": {"queued": queued, "delivered_or_seen": delivered},
        "ai_advisory_result": {
            "adapter": "deterministic_python_fallback",
            "codex_cli_required": False,
            "authority": "advisory_only",
            "decision_authority": "deterministic_rule_engine",
        },
    }
