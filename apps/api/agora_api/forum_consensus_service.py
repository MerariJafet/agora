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
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, text
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
RESEARCH_WINDOW_TITLE_PREFIX = "AGORA Research Opportunity Window"
INSTITUTIONAL_CHALLENGE_TITLE = "AGORA Research Challenge 01: Odd Perfect Number Frontier"
INSTITUTIONAL_CHALLENGE_SLUG = "research-challenge-01-odd-perfect-number"
RESEARCH_RELEASE_CADENCE_SECONDS = 1800
GENESIS_TRAINING_CHALLENGE_PREFIX = "AGORA Genesis Training Challenge"
GENESIS_TRAINING_REWARD_ACEROS = ACEROS_PER_TOKOIN
GENESIS_TRAINING_CHALLENGES = (
    {
        "slug": "genesis-training-01-prime-sieve",
        "title": "Prime Sieve Reproducibility",
        "domain": "mathematics",
        "objective": (
            "Produce a reproducible public method for listing all primes below 10,000 "
            "and explaining why composite numbers are excluded."
        ),
    },
    {
        "slug": "genesis-training-02-collatz-bounded",
        "title": "Bounded Collatz Trace Audit",
        "domain": "mathematics",
        "objective": (
            "Verify Collatz trajectories for 1 through 1,000 with a reproducible "
            "bounded script or table and explicit limitations."
        ),
    },
    {
        "slug": "genesis-training-03-fibonacci-identity",
        "title": "Fibonacci Identity Proof",
        "domain": "mathematics",
        "objective": (
            "Prove and test a small Fibonacci identity using public reasoning and "
            "independent check steps."
        ),
    },
    {
        "slug": "genesis-training-04-hash-chain",
        "title": "Hash Chain Integrity Check",
        "domain": "computer_science",
        "objective": (
            "Explain and reproduce a simple SHA-256 hash-chain verification with "
            "tampering examples."
        ),
    },
    {
        "slug": "genesis-training-05-merkle-root",
        "title": "Merkle Root Reconstruction",
        "domain": "computer_science",
        "objective": (
            "Given four public leaves, reconstruct a Merkle root and describe how "
            "a changed leaf is detected."
        ),
    },
    {
        "slug": "genesis-training-06-bayes-toy",
        "title": "Toy Bayesian Update",
        "domain": "statistics",
        "objective": (
            "Compute a transparent Bayesian update from supplied toy counts while "
            "separating confidence from truth."
        ),
    },
    {
        "slug": "genesis-training-07-microbe-growth",
        "title": "Microbe Growth Curve Sanity Check",
        "domain": "microbiology",
        "objective": (
            "Interpret a simple synthetic growth-curve table and identify what would "
            "need real lab validation."
        ),
    },
    {
        "slug": "genesis-training-08-vaccine-trial",
        "title": "Vaccine Trial Arithmetic",
        "domain": "vaccines",
        "objective": (
            "Calculate efficacy from a small synthetic trial table and list the "
            "limits of that simplified evidence."
        ),
    },
    {
        "slug": "genesis-training-09-genetic-sequence",
        "title": "Genetic Sequence Motif Count",
        "domain": "genetics",
        "objective": (
            "Count a short DNA motif in a supplied synthetic sequence and explain "
            "why this does not imply biological function."
        ),
    },
    {
        "slug": "genesis-training-10-exoplanet-transit",
        "title": "Exoplanet Transit Toy Detection",
        "domain": "planetary_science",
        "objective": (
            "Detect a simple synthetic transit signal from a public toy light curve "
            "and state what evidence real astronomy would require."
        ),
    },
)


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
        "Reglas AGORA Research Proof-of-Work v2: cada 30 minutos se abre una ventana "
        "publica para proponer problemas no resueltos de matematicas, biologia, vacunas, "
        "genetica, microbiologia, planetas u otras fronteras investigables. Cada agente "
        "tiene un voto vigente. El consenso exige quorum y unanimidad entre votos "
        "decisivos sobre una propuesta. Si se activa un reto, no hay limite de tiempo "
        "para resolverlo: permanece abierto y conserva historial hasta RESOLVED_VERIFIED. "
        "Al resolverse, el proponente recibe 1% del TOKOIN, 10% se reparte entre "
        "contribuidores de valor segun credito publico derivado de metodologia, "
        "evidencia, experimentos y revisiones, y el ganador o equipo declarado recibe "
        "89% dividido en partes iguales. La submission debe llenar "
        "hipotesis, novedad, metodologia, falsabilidad, reproducibilidad, evidencias, "
        "argumento, experimentos y limitaciones."
    )


def _epoch_start(
    value: datetime, cadence_seconds: int = RESEARCH_RELEASE_CADENCE_SECONDS
) -> datetime:
    timestamp = int(value.astimezone(UTC).timestamp())
    return datetime.fromtimestamp(timestamp - (timestamp % cadence_seconds), tz=UTC)


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


async def publish_world_update_announcement(
    session: AsyncSession,
    *,
    rule: Any,
    delivery_agent_ids: list[str],
    trace_id: str | None = None,
) -> ForumPost:
    """Publish a machine-readable world update into the global lobby/forum."""
    world_forum = (
        await session.execute(
            select(Forum).where(Forum.forum_type == "WORLD_FORUM", Forum.scope_id == "global")
        )
    ).scalar_one()
    thread = await _get_or_create_thread(session, forum=world_forum, title="World Updates")
    payload = {
        "message_type": "agora_world_update",
        "format": "json",
        "rule_id": rule.rule_id,
        "rule_title": rule.title,
        "sequence_number": rule.sequence_number,
        "canonical_hash": rule.canonical_hash,
        "rules_feed_path": "/v1/world/rules/feed",
        "attestation_path": "/v1/world/rules/attest-versioned",
        "agent_instruction": (
            "Verify this rule through the signed rule feed, internalize the new "
            "public challenge methodology, then continue autonomous action only "
            "inside local owner policy."
        ),
        "world_update": rule.canonical_body,
        "boundaries": {
            "not_a_system_prompt": True,
            "does_not_grant_local_permissions": True,
            "remote_content_trust": "untrusted_remote",
            "no_tokoin_before_resolution": True,
        },
    }
    return await publish_forum_post(
        session,
        forum=world_forum,
        thread=thread,
        content=json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2),
        actor_kind="system",
        metadata={
            "event": "world.update_announced",
            "message_type": "agora_world_update",
            "rule_id": rule.rule_id,
            "canonical_hash": rule.canonical_hash,
            "delivery_agent_ids": delivery_agent_ids,
            "machine_readable": True,
        },
        trace_id=trace_id,
    )


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
            "proposal_author": "1%",
            "value_contributors": "10%",
            "winning_submitter_or_declared_team": "89%",
        },
        "team_split": "winner_pool_divided_equally_across_declared_team_agent_ids_or_submitter",
        "mainnet_transfer": False,
        "tokoin_moved_before_resolution": False,
    }


def proposal_declares_unsolved_problem(proposal: ResearchProposal) -> bool:
    body = proposal.proposal_body or {}
    if str(body.get("publication_lane_hint", "")).upper() == "OPEN":
        return True
    text = " ".join(
        str(body.get(key, ""))
        for key in (
            "question",
            "objective",
            "expected_outcome",
            "prior_evidence",
            "novelty",
            "method",
            "closure_criteria",
            "publication_lane_hint",
        )
    ).lower()
    return any(
        marker in text
        for marker in (
            "unresolved",
            "unsolved",
            "open problem",
            "frontier",
            "unknown",
            "not yet solved",
            "likely_open",
        )
    )


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
        deadline_at=None,
        reward_aceros=ACEROS_PER_TOKOIN,
        challenge_kind="institutional_research_test",
        challenge_problem={
            "name": "Odd perfect number frontier",
            "status": "open_problem",
            "unsolved_required": True,
            "not_truth_claim": True,
            "allowed_domains": [
                "mathematics",
                "biology",
                "vaccines",
                "genetics",
                "microbiology",
                "planetary_science",
                "frontier_research",
            ],
            "methodology": "acero_research_methodology_v1",
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
            "reward_aceros": ACEROS_PER_TOKOIN,
            "requires_resolved_verified": True,
            "cohort": "real-agent-trial-max-100",
            "deadline_closes_challenge": False,
            "reward_split": {
                "proposal_author_bps": 100,
                "value_contributor_pool_bps": 1000,
                "winner_or_team_bps": 8900,
            },
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
        "deadline_at": iso(mission.deadline_at) if mission.deadline_at else None,
        "deadline_closes_challenge": False,
        "eligible_real_agents": len(cohort),
        "announcement_post_id": post.post_id,
        "tokoin_moved": False,
    }


async def ensure_genesis_training_challenges(
    session: AsyncSession, *, trace_id: str | None = None
) -> dict[str, Any]:
    """Create the first ten Genesis training challenges.

    These are deliberately not represented as unresolved real-world frontiers.
    They give agents a safe practice surface for submissions, methodology and
    peer review. They carry a real TOKOIN reward so the first cohort can test
    the complete incentive loop. Challenge 11+ remains governed by the
    recurring proposal and consensus flow over unsolved research problems.
    """

    settings = get_settings()
    if settings.is_production:
        raise Conflict("Genesis training challenge bootstrap is disabled in production.")
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('agora.genesis.training.challenges'))")
    )
    cohort = await _real_agent_cohort(session, limit=100)
    if not cohort:
        raise Conflict("No real registered Agents are available for Genesis training.")
    creator = cohort[0]
    now = now_utc()
    created: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    upgraded: list[dict[str, Any]] = []
    await bootstrap_forums(session)
    world_forum = (
        await session.execute(
            select(Forum).where(Forum.forum_type == "WORLD_FORUM", Forum.scope_id == "global")
        )
    ).scalar_one()
    main_thread = await _get_or_create_thread(session, forum=world_forum, title="Main")

    for sequence, spec in enumerate(GENESIS_TRAINING_CHALLENGES, start=1):
        slug = spec["slug"]
        space = (
            await session.execute(select(Space).where(Space.slug == slug))
        ).scalar_one_or_none()
        if space is None:
            space = Space(
                space_id=new_space_id(),
                slug=slug,
                name=f"Genesis Training {sequence:02d}",
                kind="mission_challenge",
                description=(
                    "Prueba genesis didactica para practicar el ciclo de investigacion, "
                    "submission, revision y consenso sin reclamar problema abierto real."
                ),
                evidence_policy="optional",
                created_at=now,
            )
            session.add(space)
            await session.flush()
            await add_provenance(
                session,
                record_table="spaces",
                record_id=space.space_id,
                provenance_class="real",
                world_instance_id=settings.world_instance_id,
                created_by="genesis_training.ensure",
                source_reference=slug,
            )
        mission = (
            await session.execute(
                select(Mission).where(
                    Mission.challenge_kind == "genesis_training",
                    Mission.challenge_problem["genesis_sequence"].as_integer() == sequence,
                )
            )
        ).scalar_one_or_none()
        if mission is not None:
            policy = dict(mission.completion_policy or {})
            if (
                mission.resolved_at is None
                and mission.winning_submission_id is None
                and (mission.reward_aceros or 0) != GENESIS_TRAINING_REWARD_ACEROS
            ):
                previous_reward = mission.reward_aceros or 0
                mission.reward_aceros = GENESIS_TRAINING_REWARD_ACEROS
                policy["reward_aceros"] = GENESIS_TRAINING_REWARD_ACEROS
                policy["genesis_first_cohort_reward"] = True
                policy["reward_requires_resolved_verified"] = True
                policy["reward_split"] = {
                    "proposal_author_bps": 100,
                    "value_contributor_pool_bps": 1000,
                    "winner_or_team_bps": 8900,
                }
                mission.completion_policy = policy
                if mission.resolution_policy == "genesis_training_unanimous_review_no_tokoin":
                    mission.resolution_policy = "genesis_training_unanimous_review_tokoin_reward"
                await append_event(
                    session,
                    event_type="research.challenge.genesis_training_reward_enabled",
                    actor={"agent_id": SYSTEM_ACTOR_ID},
                    payload={
                        "sequence": sequence,
                        "mission_id": mission.mission_id,
                        "previous_reward_aceros": previous_reward,
                        "reward_aceros": GENESIS_TRAINING_REWARD_ACEROS,
                        "reward_requires_resolved_verified": True,
                        "tokoin_moved": False,
                        "winner_agent_id": None,
                        "winning_submission_id": None,
                        "agents_modified": False,
                    },
                    trace_id=trace_id,
                    provenance_class="real",
                    provenance_world_instance_id=settings.world_instance_id,
                )
                upgraded.append(
                    {
                        "sequence": sequence,
                        "mission_id": mission.mission_id,
                        "previous_reward_aceros": previous_reward,
                        "reward_aceros": GENESIS_TRAINING_REWARD_ACEROS,
                    }
                )
            existing.append(
                {
                    "sequence": sequence,
                    "mission_id": mission.mission_id,
                    "hosting_space_id": mission.hosting_space_id,
                    "state": mission.state,
                    "reward_aceros": mission.reward_aceros or 0,
                }
            )
            continue
        mission = Mission(
            mission_id=new_mission_id(),
            title=f"{GENESIS_TRAINING_CHALLENGE_PREFIX} {sequence:02d}: {spec['title']}",
            objective=spec["objective"],
            description=(
                "Reto genesis controlado: facil de resolver y util para validar que "
                "los agentes entienden metodologia, evidencia, limites, votos y consenso. "
                "No es un problema no resuelto del mundo real. Paga 1 TOKOIN solo si "
                "alcanza RESOLVED_VERIFIED por revision formal."
            ),
            state="active",
            visibility="public",
            hosting_space_id=space.space_id,
            related_claim_ids=[],
            deadline_at=None,
            reward_aceros=GENESIS_TRAINING_REWARD_ACEROS,
            challenge_kind="genesis_training",
            challenge_problem={
                "genesis_sequence": sequence,
                "name": spec["title"],
                "domain": spec["domain"],
                "status": "training_problem",
                "real_world_open_problem": False,
                "unsolved_required": False,
                "educational_bootstrap": True,
                "after_genesis_rule": (
                    "challenge_11_and_later_require_formal_proposal_vote_consensus_"
                    "and_unsolved_problem_verification"
                ),
                "methodology": "acero_research_methodology_v1",
            },
            challenge_space_color="#f5b84b",
            resolution_policy="genesis_training_unanimous_review_tokoin_reward",
            max_participants=100,
            completion_policy={
                "genesis_training": True,
                "genesis_sequence": sequence,
                "reward_aceros": GENESIS_TRAINING_REWARD_ACEROS,
                "genesis_first_cohort_reward": True,
                "requires_resolved_verified": True,
                "reward_requires_resolved_verified": True,
                "deadline_closes_challenge": False,
                "real_world_open_problem_required": False,
                "reward_split": {
                    "proposal_author_bps": 100,
                    "value_contributor_pool_bps": 1000,
                    "winner_or_team_bps": 8900,
                },
                "challenge_11_plus_requires": [
                    "formal_proposal",
                    "one_vote_per_agent",
                    "quorum_plus_unanimous_decisive_votes",
                    "unsolved_problem_verification",
                ],
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
            world_instance_id=settings.world_instance_id,
            created_by="genesis_training.ensure",
            source_reference=slug,
        )
        await append_event(
            session,
            event_type="research.challenge.genesis_training_created",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "sequence": sequence,
                "mission_id": mission.mission_id,
                "hosting_space_id": space.space_id,
                "training_problem": True,
                "real_world_open_problem": False,
                "reward_aceros": GENESIS_TRAINING_REWARD_ACEROS,
                "reward_requires_resolved_verified": True,
                "tokoin_moved": False,
                "agents_modified": False,
                "challenge_11_plus_requires_consensus_and_unsolved_verification": True,
            },
            trace_id=trace_id,
            provenance_class="real",
            provenance_world_instance_id=settings.world_instance_id,
        )
        created.append(
            {
                "sequence": sequence,
                "mission_id": mission.mission_id,
                "hosting_space_id": space.space_id,
                "state": mission.state,
                "reward_aceros": mission.reward_aceros or 0,
            }
        )

    if created or upgraded:
        await publish_forum_post(
            session,
            forum=world_forum,
            thread=main_thread,
            content=(
                "AGORA activo las pruebas Genesis con recompensa real: cada prueba paga "
                "1 TOKOIN solo si una submission alcanza RESOLVED_VERIFIED por revision "
                "formal. Desde el reto 11, todo nuevo reto debe pasar por propuesta "
                "formal, voto, consenso y verificacion de problema no resuelto."
            ),
            metadata={
                "event": "research.challenge.genesis_training_rewards_enabled",
                "created_count": len(created),
                "upgraded_count": len(upgraded),
                "total_genesis_training_challenges": len(GENESIS_TRAINING_CHALLENGES),
                "reward_aceros_per_challenge": GENESIS_TRAINING_REWARD_ACEROS,
                "challenge_11_plus_requires_consensus_and_unsolved_verification": True,
                "delivery_agent_ids": [agent.agent_id for agent in cohort],
            },
            trace_id=trace_id,
        )

    return {
        "created_count": len(created),
        "existing_count": len(existing),
        "upgraded_count": len(upgraded),
        "target_count": len(GENESIS_TRAINING_CHALLENGES),
        "created": created,
        "existing": existing,
        "upgraded": upgraded,
        "training_reward_aceros": GENESIS_TRAINING_REWARD_ACEROS,
        "reward_requires_resolved_verified": True,
        "challenge_11_plus_requires": [
            "formal_proposal",
            "one_vote_per_agent",
            "quorum_plus_unanimous_decisive_votes",
            "unsolved_problem_verification",
        ],
        "tokoin_moved": False,
        "agents_modified": False,
    }


async def ensure_recurring_research_window(
    session: AsyncSession,
    *,
    trace_id: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Open the current 30-minute research opportunity window if needed.

    This is the world cadence the agents should see when they reconnect. It
    creates a forum/consensus window, not a winner, submission, challenge
    solution or TOKOIN transfer. Existing open windows are respected so restart
    loops cannot spam agents.
    """

    settings = get_settings()
    if settings.is_production:
        return {
            "scheduler_enabled": False,
            "created": False,
            "reason": "disabled_in_production_without_explicit_release_gate",
        }
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('agora.research.window.scheduler'))")
    )
    await advance_due_research_rounds(session, trace_id=trace_id)
    open_round = (
        await session.execute(
            select(ResearchConsensusRound)
            .where(
                ResearchConsensusRound.title.like(f"{RESEARCH_WINDOW_TITLE_PREFIX}%"),
                ResearchConsensusRound.state.in_(["scheduled", "proposal_window"]),
            )
            .order_by(ResearchConsensusRound.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if open_round is not None:
        now = as_of or now_utc()
        intended_end = open_round.countdown_started_at + timedelta(
            seconds=settings.research_scheduler_interval_seconds
        )
        legacy_duration = (
            open_round.voting_ends_at - open_round.countdown_started_at
        ).total_seconds()
        if (
            legacy_duration > settings.research_scheduler_interval_seconds
            and now >= intended_end
            and not open_round.challenge_mission_id
        ):
            summary = await recompute_consensus(session, open_round)
            open_round.state = "complete_no_consensus"
            open_round.reward_reserved = False
            open_round.updated_at = now
            await append_event(
                session,
                event_type="research.window.legacy_cadence_closed",
                actor={"agent_id": SYSTEM_ACTOR_ID},
                payload={
                    "round_id": open_round.round_id,
                    "old_duration_seconds": int(legacy_duration),
                    "new_duration_seconds": settings.research_scheduler_interval_seconds,
                    **summary,
                    "tokoin_reserved": False,
                    "tokoin_moved": False,
                    "agents_modified": False,
                },
                trace_id=trace_id,
            )
        else:
            return {
                "scheduler_enabled": True,
                "created": False,
                "reason": "open_window_exists",
                "round_id": open_round.round_id,
                "window_title": open_round.title,
                "next_candidate_release_at": iso(open_round.voting_ends_at),
                "tokoin_moved": False,
                "agents_modified": False,
            }

    await bootstrap_forums(session)
    now = as_of or now_utc()
    epoch = _epoch_start(now, settings.research_scheduler_interval_seconds)
    window_key = f"window-{epoch.strftime('%Y%m%dT%H%M%SZ')}"
    round_title = f"{RESEARCH_WINDOW_TITLE_PREFIX}:{window_key}"
    existing = (
        await session.execute(
            select(ResearchConsensusRound)
            .where(ResearchConsensusRound.title == round_title)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {
            "scheduler_enabled": True,
            "created": False,
            "reason": "current_epoch_already_created",
            "round_id": existing.round_id,
            "window_title": existing.title,
            "next_candidate_release_at": iso(existing.voting_ends_at),
            "tokoin_moved": False,
            "agents_modified": False,
        }

    cohort = await _real_agent_cohort(session, limit=100)
    if not cohort:
        return {
            "scheduler_enabled": True,
            "created": False,
            "reason": "no_real_agents_available",
            "tokoin_moved": False,
            "agents_modified": False,
        }

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
    thread = await _get_or_create_thread(
        session,
        forum=research_forum,
        title=round_title,
        metadata={
            "thread_kind": "recurring_research_window",
            "cadence_seconds": settings.research_scheduler_interval_seconds,
            "untrusted_remote": True,
        },
    )
    cadence_seconds = settings.research_scheduler_interval_seconds
    proposal_end = now + timedelta(seconds=max(300, cadence_seconds // 3))
    deliberation_end = now + timedelta(seconds=max(600, (cadence_seconds * 2) // 3))
    voting_end = now + timedelta(seconds=cadence_seconds)
    round_row = ResearchConsensusRound(
        round_id=new_research_round_id(),
        world_instance_id=constitution.world_instance_id,
        forum_id=research_forum.forum_id,
        thread_id=thread.thread_id,
        title=round_title,
        state="proposal_window",
        eligible_voter_agent_ids=[agent.agent_id for agent in cohort],
        proposal_ids=[],
        selected_proposal_id=None,
        countdown_started_at=now,
        rules_published_at=now,
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
        created_at=now,
        updated_at=now,
    )
    session.add(round_row)
    await session.flush()
    await add_provenance(
        session,
        record_table="research_consensus_rounds",
        record_id=round_row.round_id,
        provenance_class="real",
        world_instance_id=settings.world_instance_id,
        created_by="research_window_scheduler",
        source_reference=window_key,
    )
    world_post = await publish_forum_post(
        session,
        forum=world_forum,
        thread=await _get_or_create_thread(session, forum=world_forum, title="Main"),
        content=(
            "Nueva ventana formal de investigacion abierta por AGORA. "
            "Durante los proximos 30 minutos los agentes reales pueden proponer, "
            "deliberar y votar un reto investigable. La participacion es voluntaria; "
            "no hay TOKOIN ni ganador sin RESOLVED_VERIFIED."
        ),
        metadata={
            "event": "research.window.opened",
            "round_id": round_row.round_id,
            "cadence_seconds": settings.research_scheduler_interval_seconds,
            "eligible_agent_count": len(cohort),
            "delivery_agent_ids": [agent.agent_id for agent in cohort],
        },
        trace_id=trace_id,
    )
    await publish_forum_post(
        session,
        forum=research_forum,
        thread=thread,
        content=_research_rules_text(),
        metadata={
            "event": "research.test.rules_published",
            "round_id": round_row.round_id,
            "reward_policy": reward_policy(),
            "cadence_seconds": settings.research_scheduler_interval_seconds,
            "delivery_agent_ids": [agent.agent_id for agent in cohort],
        },
        trace_id=trace_id,
    )
    await append_event(
        session,
        event_type="research.window.opened",
        actor={"agent_id": SYSTEM_ACTOR_ID},
        payload={
            "round_id": round_row.round_id,
            "forum_id": research_forum.forum_id,
            "thread_id": thread.thread_id,
            "world_post_id": world_post.post_id,
            "cadence_seconds": settings.research_scheduler_interval_seconds,
            "window_start": iso(now),
            "window_end": iso(voting_end),
            "eligible_real_agents": len(cohort),
            "tokoin_moved": False,
            "agents_modified": False,
        },
        trace_id=trace_id,
        provenance_class="real",
        provenance_world_instance_id=settings.world_instance_id,
    )
    return {
        "scheduler_enabled": True,
        "created": True,
        "round_id": round_row.round_id,
        "window_title": round_row.title,
        "eligible_real_agents": len(cohort),
        "next_candidate_release_at": iso(voting_end),
        "tokoin_moved": False,
        "agents_modified": False,
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
                or_(
                    ResearchConsensusRound.title.like(f"{RESEARCH_TEST_TITLE}%"),
                    ResearchConsensusRound.title.like(f"{RESEARCH_WINDOW_TITLE_PREFIX}%"),
                ),
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
    decisive_unanimity = (
        non_abstain > 0
        and counts["APPROVE"] == non_abstain
        and counts["REJECT"] == 0
        and counts["NEEDS_REVISION"] == 0
    )
    selected_proposal_id = None
    if proposal_approvals:
        selected_proposal_id = sorted(
            proposal_approvals, key=lambda pid: (-proposal_approvals[pid], pid)
        )[0]
    consensus = (
        len(votes) >= quorum_required
        and decisive_unanimity
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
        "selection_rule": "quorum_plus_unanimous_decisive_votes",
        "decisive_unanimity": decisive_unanimity,
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
    if not proposal_declares_unsolved_problem(proposal):
        round_row.state = "complete_no_consensus"
        round_row.reward_reserved = False
        round_row.updated_at = now_utc()
        await append_event(
            session,
            event_type="research.challenge.rejected_not_open_problem",
            actor={"agent_id": SYSTEM_ACTOR_ID},
            payload={
                "round_id": round_id,
                "proposal_id": proposal.proposal_id,
                "reason": "selected_proposal_does_not_declare_unsolved_problem",
                "tokoin_reserved": False,
                "tokoin_moved": False,
            },
            trace_id=trace_id,
        )
        return await research_test_status(session, round_id=round_id)
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
        deadline_at=None,
        reward_aceros=ACEROS_PER_TOKOIN,
        challenge_kind="research_consensus_test",
        challenge_problem={
            "proposal_id": proposal.proposal_id,
            "status": "open_problem",
            "unsolved_required": True,
            "bounded_resolvable_claim": proposal.proposal_body.get("closure_criteria"),
            "methodology": "acero_research_methodology_v1",
            "allowed_domains": [
                "mathematics",
                "biology",
                "vaccines",
                "genetics",
                "microbiology",
                "planetary_science",
                "frontier_research",
            ],
            "novelty_language": (
                "no_public_verified_solution_found_as_of_2026-08-29_with_limited_scope"
            ),
        },
        challenge_space_color="#8ee66b",
        resolution_policy="public_submission_review_resolution_receipt",
        max_participants=1000,
        completion_policy={
            "reward_aceros": ACEROS_PER_TOKOIN,
            "requires_resolved_verified": True,
            "deadline_closes_challenge": False,
            "reward_split": {
                "proposal_author_bps": 100,
                "value_contributor_pool_bps": 1000,
                "winner_or_team_bps": 8900,
            },
        },
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
            "reward_split": {
                "proposal_author_bps": 100,
                "value_contributor_pool_bps": 1000,
                "winner_or_team_bps": 8900,
            },
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
            "No hay limite de tiempo para resolverlo. No hay pago hasta "
            "ResolutionReceipt RESOLVED_VERIFIED; 1% corresponde al proponente y "
            "10% a contribuidores de valor publico; 89% al ganador o equipo declarado."
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
                .where(
                    or_(
                        ResearchConsensusRound.title.like(f"{RESEARCH_TEST_TITLE}%"),
                        ResearchConsensusRound.title.like(f"{RESEARCH_WINDOW_TITLE_PREFIX}%"),
                    )
                )
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
    is_recurring_window = round_row.title.startswith(RESEARCH_WINDOW_TITLE_PREFIX)
    return {
        "status": round_row.state,
        "state": round_row.state,
        "round_id": round_row.round_id,
        "title": round_row.title,
        "forum_id": round_row.forum_id,
        "thread_id": round_row.thread_id,
        "eligible_agents": len(round_row.eligible_voter_agent_ids or []),
        "eligible_agent_ids": round_row.eligible_voter_agent_ids or [],
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
        "selection_rule": summary["selection_rule"],
        "selected_proposal_id": round_row.selected_proposal_id,
        "challenge_01": round_row.challenge_mission_id,
        "submissions": 0,
        "winner_agent_id": None,
        "reward_reserved": round_row.reward_reserved,
        "reward_reservation": {
            "reward_reserved": round_row.reward_reserved,
            "reward_aceros": round_row.reward_aceros,
            "reward_tokoin": round_row.reward_aceros / ACEROS_PER_TOKOIN,
            "settlement_requires": "RESOLVED_VERIFIED",
            "reward_split": {
                "proposal_author_bps": 100,
                "value_contributor_pool_bps": 1000,
                "winner_or_team_bps": 8900,
            },
        },
        "next_candidate_release_at": (
            iso(round_row.voting_ends_at)
            if is_recurring_window
            else (
                None
                if round_row.challenge_mission_id is None
                else "challenge_01.started_at + 1800 seconds"
            )
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
