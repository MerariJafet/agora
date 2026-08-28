"""Formal world opportunity market V2.

The static vocation catalog says what a district is for. This service records
auditable TEST market objects that agents may inspect and voluntarily act on.
It deliberately does not activate REAL opportunities or settle real TOKOIN.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import Conflict, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import (
    new_commitment_id,
    new_contribution_id,
    new_need_id,
    new_offer_id,
    new_opportunity_id,
    new_outcome_id,
)
from agora_api.models import (
    Agent,
    TokoinLedgerEntry,
    WorldCommitment,
    WorldContribution,
    WorldNeed,
    WorldOffer,
    WorldOpportunity,
    WorldOutcome,
)
from agora_api.provenance import add_provenance, world_instance_for_class
from agora_api.world import LANDMARKS

MARKET_VERSION = "world-opportunity-market.v2"
MARKET_CLASS = "test"
VALID_DISTRICTS = {str(landmark["id"]) for landmark in LANDMARKS}


def validate_create_opportunity(payload: Any) -> None:
    validate_boundary("world-market.schema.json", "/$defs/CreateOpportunityRequest", payload)


def validate_create_need(payload: Any) -> None:
    validate_boundary("world-market.schema.json", "/$defs/CreateNeedRequest", payload)


def validate_create_offer(payload: Any) -> None:
    validate_boundary("world-market.schema.json", "/$defs/CreateOfferRequest", payload)


def validate_propose_commitment(payload: Any) -> None:
    validate_boundary("world-market.schema.json", "/$defs/ProposeCommitmentRequest", payload)


def validate_deliver_contribution(payload: Any) -> None:
    validate_boundary("world-market.schema.json", "/$defs/DeliverContributionRequest", payload)


def validate_record_outcome(payload: Any) -> None:
    validate_boundary("world-market.schema.json", "/$defs/RecordOutcomeRequest", payload)


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _assert_test_market(payload: dict[str, Any]) -> None:
    if payload.get("market_class") != MARKET_CLASS:
        raise ValidationFailed("Only TEST world market objects can be created in this release.")


def _assert_district(district_id: str) -> None:
    if district_id not in VALID_DISTRICTS:
        raise ValidationFailed("Unknown world district.")


def _trust_record(record_id: str, created_by: str, event_id: str | None = None) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "record_authenticity": "authenticated_agent_record",
        "instruction_trust": "untrusted_content",
        "created_by_agent_id": created_by,
        "signature_status": "authenticated_transport",
        "event_id": event_id,
        "does_not_grant_local_permissions": True,
        "does_not_assert_truth": True,
    }


async def _provenance(session: AsyncSession, table: str, record_id: str, agent_id: str) -> None:
    await add_provenance(
        session,
        record_table=table,
        record_id=record_id,
        provenance_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        created_by="world-market-v2",
        created_by_actor_id=agent_id,
        created_by_actor_provenance=MARKET_CLASS,
        source_reference=MARKET_VERSION,
    )


async def _event(
    session: AsyncSession,
    event_type: str,
    agent_id: str,
    payload: dict[str, Any],
    trace_id: str | None,
) -> str:
    event = await append_event(
        session,
        event_type=event_type,
        actor={"agent_id": agent_id},
        payload=payload,
        trace_id=trace_id,
        provenance_class=MARKET_CLASS,
        provenance_world_instance_id=world_instance_for_class(MARKET_CLASS),
    )
    return event.event_id


def opportunity_view(row: WorldOpportunity, event_id: str | None = None) -> dict[str, Any]:
    return {
        "opportunity_id": row.opportunity_id,
        "market_class": row.market_class,
        "world_instance_id": row.world_instance_id,
        "district_id": row.district_id,
        "title": row.title,
        "description": row.description,
        "state": row.state,
        "reward_aceros": row.reward_aceros,
        "escrow_aceros": row.escrow_aceros,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "related_mission_id": row.related_mission_id,
        "related_challenge_mission_id": row.related_challenge_mission_id,
        "related_artifact_version_id": row.related_artifact_version_id,
        "trust": _trust_record(row.opportunity_id, row.created_by_agent_id, event_id),
        "next_allowed_actions": [
            "create_need",
            "withdraw",
            "expire",
        ]
        if row.state == "open"
        else ["inspect"],
    }


def need_view(row: WorldNeed, event_id: str | None = None) -> dict[str, Any]:
    return {
        "need_id": row.need_id,
        "opportunity_id": row.opportunity_id,
        "market_class": row.market_class,
        "world_instance_id": row.world_instance_id,
        "district_id": row.district_id,
        "title": row.title,
        "description": row.description,
        "requested_resources": row.requested_resources,
        "state": row.state,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "trust": _trust_record(row.need_id, row.created_by_agent_id, event_id),
        "next_allowed_actions": ["create_offer", "withdraw", "expire"]
        if row.state == "open"
        else ["inspect"],
    }


def offer_view(row: WorldOffer, event_id: str | None = None) -> dict[str, Any]:
    return {
        "offer_id": row.offer_id,
        "need_id": row.need_id,
        "market_class": row.market_class,
        "world_instance_id": row.world_instance_id,
        "district_id": row.district_id,
        "title": row.title,
        "description": row.description,
        "offered_resources": row.offered_resources,
        "state": row.state,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "trust": _trust_record(row.offer_id, row.created_by_agent_id, event_id),
        "next_allowed_actions": ["propose_commitment", "withdraw", "expire"]
        if row.state == "open"
        else ["inspect"],
    }


def commitment_view(row: WorldCommitment, event_id: str | None = None) -> dict[str, Any]:
    return {
        "commitment_id": row.commitment_id,
        "need_id": row.need_id,
        "offer_id": row.offer_id,
        "market_class": row.market_class,
        "world_instance_id": row.world_instance_id,
        "state": row.state,
        "proposed_by_agent_id": row.proposed_by_agent_id,
        "accepted_by_agent_id": row.accepted_by_agent_id,
        "terms": row.terms,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "trust": _trust_record(row.commitment_id, row.proposed_by_agent_id, event_id),
        "next_allowed_actions": ["accept", "reject", "withdraw"]
        if row.state == "proposed"
        else ["inspect", "deliver_contribution"]
        if row.state == "accepted"
        else ["inspect"],
    }


def contribution_view(row: WorldContribution, event_id: str | None = None) -> dict[str, Any]:
    return {
        "contribution_id": row.contribution_id,
        "commitment_id": row.commitment_id,
        "market_class": row.market_class,
        "world_instance_id": row.world_instance_id,
        "artifact_version_id": row.artifact_version_id,
        "summary": row.summary,
        "state": row.state,
        "created_at": row.created_at.isoformat(),
        "trust": _trust_record(row.contribution_id, row.created_by_agent_id, event_id),
        "next_allowed_actions": ["record_outcome"] if row.state == "delivered" else ["inspect"],
    }


def outcome_view(row: WorldOutcome, event_id: str | None = None) -> dict[str, Any]:
    return {
        "outcome_id": row.outcome_id,
        "contribution_id": row.contribution_id,
        "market_class": row.market_class,
        "world_instance_id": row.world_instance_id,
        "verdict": row.verdict,
        "summary": row.summary,
        "settled_aceros": row.settled_aceros,
        "created_at": row.created_at.isoformat(),
        "trust": _trust_record(row.outcome_id, row.reviewer_agent_id, event_id),
        "next_allowed_actions": ["inspect"],
    }


async def market_summary(session: AsyncSession) -> dict[str, Any]:
    async def counts(model: Any, id_column: Any) -> dict[str, int]:
        rows = (
            await session.execute(
                select(model.district_id, model.state, func.count(id_column))
                .where(model.market_class == MARKET_CLASS)
                .group_by(model.district_id, model.state)
            )
        ).all()
        result: dict[str, int] = {}
        for district_id, state, count in rows:
            result[f"{district_id}:{state}"] = int(count)
        return result

    need_counts = await counts(WorldNeed, WorldNeed.need_id)
    offer_counts = await counts(WorldOffer, WorldOffer.offer_id)
    commitment_rows = (
        await session.execute(
            select(WorldCommitment.state, func.count(WorldCommitment.commitment_id))
            .where(WorldCommitment.market_class == MARKET_CLASS)
            .group_by(WorldCommitment.state)
        )
    ).all()
    outcome_count = (
        await session.execute(
            select(func.count(WorldOutcome.outcome_id)).where(
                WorldOutcome.market_class == MARKET_CLASS
            )
        )
    ).scalar_one()
    return {
        "market_version": MARKET_VERSION,
        "market_class": MARKET_CLASS,
        "classification": "public_world_context",
        "runtime_trust": "untrusted_remote",
        "record_authenticity": "authenticated_record_required_for_mutations",
        "catalog_detail_endpoint": "/v1/world/opportunities",
        "formal_market_endpoint": "/v1/world-market",
        "does_not_grant_local_permissions": True,
        "real_opportunities_enabled": False,
        "economic_policy": {
            "test_settlement_only": True,
            "real_tokoin_settlement_enabled": False,
            "rewards_require_escrow": True,
            "presence_message_and_movement_rewards": False,
        },
        "counts": {
            "needs_by_district_state": need_counts,
            "offers_by_district_state": offer_counts,
            "commitments_by_state": {state: int(count) for state, count in commitment_rows},
            "outcomes_total": int(outcome_count),
        },
        "preference_learning": {
            "classification": "inference_not_identity",
            "primary_evidence": ["commitments", "contributions", "outcomes"],
            "secondary_evidence": ["movement", "presence"],
            "not_identity": True,
        },
    }


async def create_opportunity(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[WorldOpportunity, str | None]:
    _assert_test_market(payload)
    _assert_district(payload["district_id"])
    if (
        payload.get("reward_aceros", 0)
        and payload.get("escrow_aceros", 0) < payload["reward_aceros"]
    ):
        raise ValidationFailed("Economic opportunities require escrow covering the reward.")
    existing = (
        await session.execute(
            select(WorldOpportunity).where(
                WorldOpportunity.created_by_agent_id == agent.agent_id,
                WorldOpportunity.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, None
    ts = now_utc()
    row = WorldOpportunity(
        opportunity_id=new_opportunity_id(),
        idempotency_key=payload["idempotency_key"],
        market_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        district_id=payload["district_id"],
        title=payload["title"],
        description=payload["description"],
        state="open",
        created_by_agent_id=agent.agent_id,
        created_by_agent_version_id=agent.current_version_id,
        related_mission_id=payload.get("related_mission_id"),
        related_challenge_mission_id=payload.get("related_challenge_mission_id"),
        related_artifact_version_id=payload.get("related_artifact_version_id"),
        reward_aceros=payload.get("reward_aceros", 0),
        escrow_aceros=payload.get("escrow_aceros", 0),
        expires_at=_parse_dt(payload.get("expires_at")),
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await session.flush()
    await _provenance(session, "world_market_opportunities", row.opportunity_id, agent.agent_id)
    event_id = await _event(
        session,
        "world_market.opportunity_created",
        agent.agent_id,
        {
            "opportunity_id": row.opportunity_id,
            "district_id": row.district_id,
            "market_class": MARKET_CLASS,
        },
        trace_id,
    )
    return row, event_id


async def create_need(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[WorldNeed, str | None]:
    _assert_test_market(payload)
    _assert_district(payload["district_id"])
    existing = (
        await session.execute(
            select(WorldNeed).where(
                WorldNeed.created_by_agent_id == agent.agent_id,
                WorldNeed.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, None
    if (
        payload.get("opportunity_id")
        and await session.get(WorldOpportunity, payload["opportunity_id"]) is None
    ):
        raise NotFound("Opportunity not found.")
    ts = now_utc()
    row = WorldNeed(
        need_id=new_need_id(),
        opportunity_id=payload.get("opportunity_id"),
        idempotency_key=payload["idempotency_key"],
        market_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        district_id=payload["district_id"],
        title=payload["title"],
        description=payload["description"],
        requested_resources=payload["requested_resources"],
        state="open",
        created_by_agent_id=agent.agent_id,
        created_by_agent_version_id=agent.current_version_id,
        expires_at=_parse_dt(payload.get("expires_at")),
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await session.flush()
    await _provenance(session, "world_market_needs", row.need_id, agent.agent_id)
    event_id = await _event(
        session,
        "world_market.need_created",
        agent.agent_id,
        {"need_id": row.need_id, "district_id": row.district_id, "market_class": MARKET_CLASS},
        trace_id,
    )
    return row, event_id


async def create_offer(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[WorldOffer, str | None]:
    _assert_test_market(payload)
    _assert_district(payload["district_id"])
    existing = (
        await session.execute(
            select(WorldOffer).where(
                WorldOffer.created_by_agent_id == agent.agent_id,
                WorldOffer.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, None
    if payload.get("need_id") and await session.get(WorldNeed, payload["need_id"]) is None:
        raise NotFound("Need not found.")
    ts = now_utc()
    row = WorldOffer(
        offer_id=new_offer_id(),
        need_id=payload.get("need_id"),
        idempotency_key=payload["idempotency_key"],
        market_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        district_id=payload["district_id"],
        title=payload["title"],
        description=payload["description"],
        offered_resources=payload["offered_resources"],
        state="open",
        created_by_agent_id=agent.agent_id,
        created_by_agent_version_id=agent.current_version_id,
        expires_at=_parse_dt(payload.get("expires_at")),
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await session.flush()
    await _provenance(session, "world_market_offers", row.offer_id, agent.agent_id)
    event_id = await _event(
        session,
        "world_market.offer_created",
        agent.agent_id,
        {"offer_id": row.offer_id, "need_id": row.need_id, "district_id": row.district_id},
        trace_id,
    )
    return row, event_id


async def propose_commitment(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[WorldCommitment, str | None]:
    _assert_test_market(payload)
    existing = (
        await session.execute(
            select(WorldCommitment).where(
                WorldCommitment.proposed_by_agent_id == agent.agent_id,
                WorldCommitment.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, None
    need = await session.get(WorldNeed, payload["need_id"])
    offer = await session.get(WorldOffer, payload["offer_id"])
    if need is None or offer is None:
        raise NotFound("Need or offer not found.")
    if need.state != "open" or offer.state != "open":
        raise Conflict("Need and offer must both be open.")
    ts = now_utc()
    row = WorldCommitment(
        commitment_id=new_commitment_id(),
        need_id=need.need_id,
        offer_id=offer.offer_id,
        idempotency_key=payload["idempotency_key"],
        market_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        state="proposed",
        proposed_by_agent_id=agent.agent_id,
        terms=payload["terms"],
        created_at=ts,
        updated_at=ts,
    )
    session.add(row)
    await session.flush()
    await _provenance(session, "world_market_commitments", row.commitment_id, agent.agent_id)
    event_id = await _event(
        session,
        "world_market.commitment_proposed",
        agent.agent_id,
        {"commitment_id": row.commitment_id, "need_id": row.need_id, "offer_id": row.offer_id},
        trace_id,
    )
    return row, event_id


async def accept_commitment(
    session: AsyncSession,
    *,
    commitment_id: str,
    agent: Agent,
    trace_id: str | None,
) -> tuple[WorldCommitment, str | None]:
    row = await session.get(WorldCommitment, commitment_id)
    if row is None:
        raise NotFound("Commitment not found.")
    if row.state == "accepted":
        return row, None
    if row.state != "proposed":
        raise Conflict("Only proposed commitments can be accepted.")
    row.state = "accepted"
    row.accepted_by_agent_id = agent.agent_id
    row.updated_at = now_utc()
    need = await session.get(WorldNeed, row.need_id)
    offer = await session.get(WorldOffer, row.offer_id)
    if need is not None:
        need.state = "committed"
        need.updated_at = row.updated_at
    if offer is not None:
        offer.state = "committed"
        offer.updated_at = row.updated_at
    event_id = await _event(
        session,
        "world_market.commitment_accepted",
        agent.agent_id,
        {"commitment_id": row.commitment_id, "need_id": row.need_id, "offer_id": row.offer_id},
        trace_id,
    )
    return row, event_id


async def deliver_contribution(
    session: AsyncSession,
    *,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[WorldContribution, str | None]:
    _assert_test_market(payload)
    existing = (
        await session.execute(
            select(WorldContribution).where(
                WorldContribution.created_by_agent_id == agent.agent_id,
                WorldContribution.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, None
    commitment = await session.get(WorldCommitment, payload["commitment_id"])
    if commitment is None:
        raise NotFound("Commitment not found.")
    if commitment.state != "accepted":
        raise Conflict("Contribution requires an accepted commitment.")
    row = WorldContribution(
        contribution_id=new_contribution_id(),
        commitment_id=commitment.commitment_id,
        idempotency_key=payload["idempotency_key"],
        market_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        artifact_version_id=payload.get("artifact_version_id"),
        summary=payload["summary"],
        state="delivered",
        created_by_agent_id=agent.agent_id,
        created_by_agent_version_id=agent.current_version_id,
        created_at=now_utc(),
    )
    session.add(row)
    await session.flush()
    await _provenance(session, "world_market_contributions", row.contribution_id, agent.agent_id)
    event_id = await _event(
        session,
        "world_market.contribution_delivered",
        agent.agent_id,
        {"contribution_id": row.contribution_id, "commitment_id": row.commitment_id},
        trace_id,
    )
    return row, event_id


async def record_outcome(
    session: AsyncSession,
    *,
    contribution_id: str,
    agent: Agent,
    payload: dict[str, Any],
    trace_id: str | None,
) -> tuple[WorldOutcome, str | None]:
    _assert_test_market(payload)
    existing = (
        await session.execute(
            select(WorldOutcome).where(
                WorldOutcome.reviewer_agent_id == agent.agent_id,
                WorldOutcome.idempotency_key == payload["idempotency_key"],
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing, None
    contribution = await session.get(WorldContribution, contribution_id)
    if contribution is None:
        raise NotFound("Contribution not found.")
    row = WorldOutcome(
        outcome_id=new_outcome_id(),
        contribution_id=contribution_id,
        idempotency_key=payload["idempotency_key"],
        market_class=MARKET_CLASS,
        world_instance_id=world_instance_for_class(MARKET_CLASS),
        verdict=payload["verdict"],
        summary=payload["summary"],
        reviewer_agent_id=agent.agent_id,
        reviewer_agent_version_id=agent.current_version_id,
        settled_aceros=0,
        created_at=now_utc(),
    )
    contribution.state = "reviewed"
    session.add(row)
    await session.flush()
    await _provenance(session, "world_market_outcomes", row.outcome_id, agent.agent_id)
    event_id = await _event(
        session,
        "world_market.outcome_recorded",
        agent.agent_id,
        {
            "outcome_id": row.outcome_id,
            "contribution_id": row.contribution_id,
            "verdict": row.verdict,
            "settled_aceros": 0,
        },
        trace_id,
    )
    return row, event_id


async def expire_due_records(
    session: AsyncSession, *, trace_id: str | None = None
) -> dict[str, int]:
    ts = now_utc()
    expired = {"opportunities": 0, "needs": 0, "offers": 0, "commitments": 0}
    opportunities = (
        await session.execute(
            select(WorldOpportunity).where(
                WorldOpportunity.market_class == MARKET_CLASS,
                WorldOpportunity.state == "open",
                WorldOpportunity.expires_at.is_not(None),
                WorldOpportunity.expires_at <= ts,
            )
        )
    ).scalars().all()
    for opportunity in opportunities:
        opportunity.state = "expired"
        opportunity.updated_at = ts
        await _event(
            session,
            "world_market.opportunity_expired",
            "agt_00000000000000000000000000",
            {
                "opportunity_id": opportunity.opportunity_id,
                "market_class": MARKET_CLASS,
                "settled_aceros": 0,
            },
            trace_id,
        )
        expired["opportunities"] += 1

    needs = (
        await session.execute(
            select(WorldNeed).where(
                WorldNeed.market_class == MARKET_CLASS,
                WorldNeed.state == "open",
                WorldNeed.expires_at.is_not(None),
                WorldNeed.expires_at <= ts,
            )
        )
    ).scalars().all()
    for need in needs:
        need.state = "expired"
        need.updated_at = ts
        await _event(
            session,
            "world_market.need_expired",
            "agt_00000000000000000000000000",
            {"need_id": need.need_id, "market_class": MARKET_CLASS, "settled_aceros": 0},
            trace_id,
        )
        expired["needs"] += 1

    offers = (
        await session.execute(
            select(WorldOffer).where(
                WorldOffer.market_class == MARKET_CLASS,
                WorldOffer.state == "open",
                WorldOffer.expires_at.is_not(None),
                WorldOffer.expires_at <= ts,
            )
        )
    ).scalars().all()
    for offer in offers:
        offer.state = "expired"
        offer.updated_at = ts
        await _event(
            session,
            "world_market.offer_expired",
            "agt_00000000000000000000000000",
            {"offer_id": offer.offer_id, "market_class": MARKET_CLASS, "settled_aceros": 0},
            trace_id,
        )
        expired["offers"] += 1

    return expired


async def preference_evidence(session: AsyncSession, agent_id: str) -> dict[str, Any]:
    commitments = (
        await session.execute(
            select(func.count(WorldCommitment.commitment_id)).where(
                WorldCommitment.market_class == MARKET_CLASS,
                (WorldCommitment.proposed_by_agent_id == agent_id)
                | (WorldCommitment.accepted_by_agent_id == agent_id),
            )
        )
    ).scalar_one()
    contributions = (
        await session.execute(
            select(func.count(WorldContribution.contribution_id)).where(
                WorldContribution.market_class == MARKET_CLASS,
                WorldContribution.created_by_agent_id == agent_id,
            )
        )
    ).scalar_one()
    outcomes = (
        await session.execute(
            select(func.count(WorldOutcome.outcome_id)).where(
                WorldOutcome.market_class == MARKET_CLASS,
                WorldOutcome.reviewer_agent_id == agent_id,
            )
        )
    ).scalar_one()
    return {
        "agent_id": agent_id,
        "classification": "inference_not_identity",
        "can_be_disabled_later": True,
        "primary_evidence": {
            "commitments": int(commitments),
            "contributions": int(contributions),
            "outcomes": int(outcomes),
        },
        "secondary_evidence": {
            "movement_and_presence": "not_used_as_primary_preference_evidence",
        },
    }


async def tokoin_ledger_count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count(TokoinLedgerEntry.entry_id)))).scalar_one())
