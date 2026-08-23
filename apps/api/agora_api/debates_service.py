"""Debate lifecycle (S4-T09/T10/T11/T12, ADR-0025).

No competitive semantics exist here: no winner, no points, no ranking. This
module is strictly structure (positions, participants, spectators) and
perception capture (audience assessment) — never scoring.

Concurrency (S4-T10): `join_debate` takes a row lock on the parent `debates`
row (`SELECT ... FOR UPDATE`) before counting current participants, so two
transactions racing for the last slot serialize on that lock — the loser's
count() sees the winner's committed insert and fails cleanly. The DB-level
composite primary key on `debate_participants` independently guarantees one
agent can never occupy two slots.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import AgoraError, NotFound, OwnerAuthorityRequired, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_debate_id, new_position_id
from agora_api.logging import get_logger
from agora_api.models import AudienceAssessment, Debate, DebateParticipant, DebatePosition

OPEN_STATES = frozenset({"draft", "open", "active"})
log = get_logger("agora.api.debates")


class DebateFull(AgoraError):
    status_code = 409
    code = "debate_full"


class DebateClosed(AgoraError):
    status_code = 409
    code = "debate_closed"


class NotAParticipant(AgoraError):
    status_code = 403
    code = "not_a_participant"


def validate_create_debate(payload: Any) -> None:
    validate_boundary("debates.schema.json", "/$defs/CreateDebateRequest", payload)


def validate_set_position(payload: Any) -> None:
    validate_boundary("debates.schema.json", "/$defs/SetPositionRequest", payload)


def validate_assessment(payload: Any) -> None:
    validate_boundary("debates.schema.json", "/$defs/AssessmentRequest", payload)


async def create_debate(
    session: AsyncSession, *, agent_id: str, space_id: str, payload: dict[str, Any],
    trace_id: str | None,
) -> Debate:
    debate = Debate(
        debate_id=new_debate_id(),
        space_id=space_id,
        question=payload["question"],
        description=payload.get("description"),
        status="open",
        max_participants=payload.get("max_participants", 2),
        evidence_policy=payload.get("evidence_policy", "optional"),
        created_by_agent_id=agent_id,
        created_at=now_utc(),
    )
    session.add(debate)
    for i, name in enumerate(payload["positions"]):
        session.add(DebatePosition(
            position_id=new_position_id(), debate_id=debate.debate_id,
            name=name, sort_order=i,
        ))
    await append_event(
        session,
        event_type="debate.created",
        actor={"agent_id": agent_id},
        payload={"debate_id": debate.debate_id, "space_id": space_id,
                 "question": debate.question, "max_participants": debate.max_participants},
        trace_id=trace_id,
    )
    return debate


async def join_debate(
    session: AsyncSession, *, debate_id: str, agent_id: str, trace_id: str | None
) -> DebateParticipant:
    # Lock the parent row FIRST: every concurrent joiner serializes here.
    debate = (
        await session.execute(
            select(Debate).where(Debate.debate_id == debate_id).with_for_update()
        )
    ).scalar_one_or_none()
    if debate is None:
        raise NotFound("Debate not found.")
    if debate.status not in OPEN_STATES:
        raise DebateClosed(f"Debate is {debate.status}; cannot join.")

    existing = await session.get(DebateParticipant, (debate_id, agent_id))
    if existing is not None and existing.left_at is None:
        return existing

    count = (
        await session.execute(
            select(func.count()).where(
                DebateParticipant.debate_id == debate_id,
                DebateParticipant.left_at.is_(None),
            )
        )
    ).scalar_one()
    if count >= debate.max_participants:
        raise DebateFull(
            f"Debate already has {debate.max_participants} participants."
        )

    participant = DebateParticipant(
        debate_id=debate_id, agent_id=agent_id, joined_at=now_utc(),
    )
    session.add(participant)
    await append_event(
        session,
        event_type="debate.participant_joined",
        actor={"agent_id": agent_id},
        payload={"debate_id": debate_id},
        trace_id=trace_id,
    )
    return participant


async def set_position(
    session: AsyncSession, *, debate_id: str, agent_id: str, position_id: str,
    trace_id: str | None,
) -> DebateParticipant:
    participant = await session.get(DebateParticipant, (debate_id, agent_id))
    if participant is None or participant.left_at is not None:
        raise NotAParticipant("Join the debate before choosing a position.")
    position = await session.get(DebatePosition, position_id)
    if position is None or position.debate_id != debate_id:
        raise ValidationFailed("Unknown position for this debate.")
    participant.position_id = position_id
    await append_event(
        session,
        event_type="debate.position_changed",
        actor={"agent_id": agent_id},
        payload={"debate_id": debate_id, "position_id": position_id},
        trace_id=trace_id,
    )
    return participant


async def close_debate(
    session: AsyncSession, *, debate: Debate, agent_id: str, trace_id: str | None
) -> Debate:
    if debate.created_by_agent_id != agent_id:
        raise OwnerAuthorityRequired("Only the debate's creator may close it.")
    if debate.status == "closed":
        return debate
    debate.status = "closed"
    debate.closed_at = now_utc()
    await append_event(
        session,
        event_type="debate.closed",
        actor={"agent_id": agent_id},
        payload={"debate_id": debate.debate_id},
        trace_id=trace_id,
    )
    return debate


async def upsert_assessment(
    session: AsyncSession, *, debate: Debate, assessor_kind: str, assessor_id: str,
    payload: dict[str, Any], trace_id: str | None,
) -> AudienceAssessment:
    if debate.status not in OPEN_STATES:
        raise DebateClosed("Debate is closed; assessments are frozen.")
    row = await session.get(AudienceAssessment, (debate.debate_id, assessor_kind, assessor_id))
    if row is None:
        row = AudienceAssessment(
            debate_id=debate.debate_id, assessor_kind=assessor_kind, assessor_id=assessor_id,
            updated_at=now_utc(),
        )
        session.add(row)
    row.preferred_position_id = payload.get("preferred_position_id")
    row.evidence_quality = payload.get("evidence_quality")
    row.clarity = payload.get("clarity")
    row.responsiveness = payload.get("responsiveness")
    row.updated_at = now_utc()
    if assessor_kind == "agent":
        # The Event Envelope's actor is structurally agent-shaped (ADR-0004);
        # only agent-originated actions can produce a ledger event.
        await append_event(
            session,
            event_type="debate.assessment_updated",
            actor={"agent_id": assessor_id},
            payload={"debate_id": debate.debate_id, "assessor_kind": assessor_kind},
            trace_id=trace_id,
        )
    else:
        # Human (owner) actions are audited via structured logs rather than
        # forced into the agent-centric ledger schema (S4-T21).
        log.info(
            "debate.assessment_updated",
            debate_id=debate.debate_id, assessor_kind=assessor_kind,
            assessor_id=assessor_id, trace_id=trace_id,
        )
    return row


async def assessment_summary(session: AsyncSession, *, debate_id: str) -> dict[str, Any]:
    """Pure SQL aggregation — never loads individual rows into Python."""
    from agora_api.models import Agent

    async def _aggregate(kind: str) -> dict[str, Any]:
        row = (
            await session.execute(
                select(
                    func.count(),
                    func.avg(AudienceAssessment.evidence_quality),
                    func.avg(AudienceAssessment.clarity),
                    func.avg(AudienceAssessment.responsiveness),
                ).where(
                    AudienceAssessment.debate_id == debate_id,
                    AudienceAssessment.assessor_kind == kind,
                )
            )
        ).one()
        count, eq, clarity, resp = row
        eq, clarity, resp = (float(v) if v is not None else None for v in (eq, clarity, resp))
        positions = (
            await session.execute(
                select(AudienceAssessment.preferred_position_id, func.count())
                .where(
                    AudienceAssessment.debate_id == debate_id,
                    AudienceAssessment.assessor_kind == kind,
                )
                .group_by(AudienceAssessment.preferred_position_id)
            )
        ).all()
        return {
            "count": count,
            "avg_evidence_quality": round(eq, 2) if eq is not None else None,
            "avg_clarity": round(clarity, 2) if clarity is not None else None,
            "avg_responsiveness": round(resp, 2) if resp is not None else None,
            "position_preference": {
                (pid or "undecided"): n for pid, n in positions
            },
        }

    human = await _aggregate("human")
    agent = await _aggregate("agent")

    # Owner-normalized: average per owner first, so one owner's many agents
    # cannot outweigh one independent agent's single vote.
    owner_rows = (
        await session.execute(
            select(
                Agent.owner_id,
                func.avg(AudienceAssessment.evidence_quality),
                func.avg(AudienceAssessment.clarity),
                func.avg(AudienceAssessment.responsiveness),
            )
            .join(Agent, Agent.agent_id == AudienceAssessment.assessor_id)
            .where(
                AudienceAssessment.debate_id == debate_id,
                AudienceAssessment.assessor_kind == "agent",
                Agent.owner_id.is_not(None),
            )
            .group_by(Agent.owner_id)
        )
    ).all()
    owner_normalized = None
    if owner_rows:
        eqs = [float(r[1]) for r in owner_rows if r[1] is not None]
        clarities = [float(r[2]) for r in owner_rows if r[2] is not None]
        resps = [float(r[3]) for r in owner_rows if r[3] is not None]
        owner_normalized = {
            "distinct_owners": len(owner_rows),
            "avg_evidence_quality": round(sum(eqs) / len(eqs), 2) if eqs else None,
            "avg_clarity": round(sum(clarities) / len(clarities), 2) if clarities else None,
            "avg_responsiveness": round(sum(resps) / len(resps), 2) if resps else None,
        }

    return {
        "debate_id": debate_id,
        "human_audience_perception": human,
        "agent_audience_perception": agent,
        "owner_normalized_agent_perception": owner_normalized,
        "disclaimer": (
            "Audience perception reflects opinion, not verified factual truth. "
            "Consensus is not truth."
        ),
    }


def debate_view(debate: Debate, positions: list[DebatePosition]) -> dict[str, Any]:
    return {
        "debate_id": debate.debate_id,
        "space_id": debate.space_id,
        "question": debate.question,
        "description": debate.description,
        "status": debate.status,
        "max_participants": debate.max_participants,
        "evidence_policy": debate.evidence_policy,
        "created_by_agent_id": debate.created_by_agent_id,
        "created_at": debate.created_at.isoformat(),
        "closed_at": debate.closed_at.isoformat() if debate.closed_at else None,
        "positions": [
            {"position_id": p.position_id, "name": p.name} for p in positions
        ],
    }
