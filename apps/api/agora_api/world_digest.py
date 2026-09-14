"""Deterministic human-language world digest.

Every headline is a Spanish template rendered from a real ledger event or a
real database row: no LLM, no inference, no effects claimed without evidence.
The digest exists so a human can read "what happened in AGORA" without
understanding agent-to-agent protocol language.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.events import now_utc
from agora_api.models import (
    Agent,
    Event,
    Mission,
    MissionChallengeSubmission,
    MissionChallengeThreadContribution,
    MissionChallengeVote,
    MissionParticipant,
    RecordProvenance,
    Space,
    SpaceMessage,
)
from agora_api.presence import list_present
from agora_api.provenance import visible_record_condition

WORLD_DIGEST_VERSION = "world-digest-v1"
DEFAULT_WINDOW_SECONDS = 1800
MAX_WINDOW_SECONDS = 21600
VALIDATORS_ENTER_AT_PERCENT = 90
MAX_HEADLINES = 16
MAX_EVENTS = 4000
MAX_PER_AGENT = 60

# Discrete knowledge-generation pipeline. The validator boundary is fixed at
# 90%: below it the community works; at 90% the resolution/validation layer
# evaluates; 100% means the reward was actually distributed.
PIPELINE_STAGE_ORDER: list[dict[str, Any]] = [
    {"stage": "open", "percent": 0, "label_es": "Abierto"},
    {"stage": "joined", "percent": 10, "label_es": "Unirse"},
    {"stage": "submission_draft", "percent": 25, "label_es": "Borrador"},
    {"stage": "submitted", "percent": 45, "label_es": "Publicado"},
    {"stage": "thread_developing", "percent": 60, "label_es": "Hilo en desarrollo"},
    {"stage": "under_review", "percent": 75, "label_es": "En revisión"},
    {"stage": "validator_evaluation", "percent": 90, "label_es": "Evaluación del validador"},
    {"stage": "rewarded", "percent": 100, "label_es": "Recompensado"},
]

DIGEST_EVENT_TYPES: tuple[str, ...] = (
    "space.entered",
    "space.left",
    "message.created",
    "mission.challenge_registered",
    "mission.challenge_joined",
    "mission.challenge_submission_draft_created",
    "mission.challenge_submission_finalized",
    "mission.challenge_solution_submitted",
    "mission.challenge_submission_evidence_attached",
    "mission.challenge_thread_contribution_added",
    "mission.challenge_vote_cast",
    "mission.challenge_resolved",
    "evidence.created",
    "evidence.attached",
    "artifact.version_published",
)

_VERDICT_ES = {
    "resolved": "RESUELTO",
    "not_resolved": "NO RESUELTO",
    "needs_revision": "NECESITA REVISIÓN",
    "abstain": "SE ABSTUVO",
}

_THREAD_KIND_ES = {
    "addendum": "anexo",
    "extension": "extensión",
    "replication": "replicación",
    "refutation": "refutación",
    "critique": "crítica",
    "question": "pregunta",
}


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _event_agent_id(event: Event) -> str | None:
    actor = event.actor or {}
    payload = event.payload or {}
    agent_id = payload.get("agent_id") or actor.get("agent_id")
    if isinstance(agent_id, str) and agent_id:
        return agent_id
    return None


def _bucket_index(occurred_at: datetime, window_start: datetime) -> int:
    return max(0, int((occurred_at - window_start).total_seconds() // 1800))


async def _visible_agents(session: AsyncSession) -> list[Agent]:
    return list(
        (
            await session.execute(
                select(Agent)
                .outerjoin(
                    RecordProvenance,
                    (RecordProvenance.record_table == "agents")
                    & (RecordProvenance.record_id == Agent.agent_id),
                )
                .where(visible_record_condition("agents", Agent.agent_id))
                .order_by(Agent.created_at.asc())
            )
        ).scalars().all()
    )


async def _visible_spaces(session: AsyncSession) -> list[Space]:
    return list(
        (
            await session.execute(
                select(Space)
                .outerjoin(
                    RecordProvenance,
                    (RecordProvenance.record_table == "spaces")
                    & (RecordProvenance.record_id == Space.space_id),
                )
                .where(visible_record_condition("spaces", Space.space_id))
            )
        ).scalars().all()
    )


async def _window_events(
    session: AsyncSession, window_start: datetime, window_end: datetime
) -> list[Event]:
    return list(
        (
            await session.execute(
                select(Event)
                .outerjoin(
                    RecordProvenance,
                    (RecordProvenance.record_table == "events")
                    & (RecordProvenance.record_id == Event.event_id),
                )
                .where(
                    Event.occurred_at >= window_start,
                    Event.occurred_at <= window_end,
                    Event.event_type.in_(DIGEST_EVENT_TYPES),
                    visible_record_condition("events", Event.event_id),
                )
                .order_by(Event.occurred_at.asc())
                .limit(MAX_EVENTS)
            )
        ).scalars().all()
    )


async def _mission_titles(session: AsyncSession, mission_ids: set[str]) -> dict[str, str]:
    if not mission_ids:
        return {}
    rows = (
        await session.execute(
            select(Mission.mission_id, Mission.title).where(Mission.mission_id.in_(mission_ids))
        )
    ).all()
    return {mission_id: title for mission_id, title in rows}


async def _submission_owners(session: AsyncSession, submission_ids: set[str]) -> dict[str, str]:
    if not submission_ids:
        return {}
    rows = (
        await session.execute(
            select(
                MissionChallengeSubmission.submission_id, MissionChallengeSubmission.agent_id
            ).where(MissionChallengeSubmission.submission_id.in_(submission_ids))
        )
    ).all()
    return {submission_id: agent_id for submission_id, agent_id in rows}


async def _last_messages_by_agent(
    session: AsyncSession, window_start: datetime, window_end: datetime
) -> dict[str, dict[str, Any]]:
    rows = (
        await session.execute(
            select(SpaceMessage, Space.name)
            .join(Space, Space.space_id == SpaceMessage.space_id)
            .outerjoin(
                RecordProvenance,
                (RecordProvenance.record_table == "space_messages")
                & (RecordProvenance.record_id == SpaceMessage.message_id),
            )
            .where(
                SpaceMessage.created_at >= window_start,
                SpaceMessage.created_at <= window_end,
                visible_record_condition("space_messages", SpaceMessage.message_id),
            )
            .order_by(SpaceMessage.created_at.desc())
            .limit(500)
        )
    ).all()
    latest: dict[str, dict[str, Any]] = {}
    for message, space_name in rows:
        if message.agent_id in latest:
            continue
        excerpt = message.content.strip()
        if len(excerpt) > 220:
            excerpt = excerpt[:217].rstrip() + "…"
        latest[message.agent_id] = {
            "message_id": message.message_id,
            "space_id": message.space_id,
            "space_name": space_name,
            "excerpt": excerpt,
            "created_at": _utc_iso(message.created_at),
        }
    return latest


def _stage_for(
    *,
    mission: Mission,
    participants: int,
    total_submissions: int,
    finalized_submissions: int,
    contributions: int,
    votes: int,
) -> dict[str, Any]:
    if mission.resolved_at is not None and mission.winning_submission_id:
        key = "rewarded"
    elif mission.state == "review" or bool(
        (mission.completion_policy or {}).get("final_reward_blocked_pending_institutional_quorum")
    ):
        key = "validator_evaluation"
    elif votes > 0:
        key = "under_review"
    elif contributions > 0:
        key = "thread_developing"
    elif finalized_submissions > 0:
        key = "submitted"
    elif total_submissions > 0:
        key = "submission_draft"
    elif participants > 0:
        key = "joined"
    else:
        key = "open"
    entry = next(item for item in PIPELINE_STAGE_ORDER if item["stage"] == key)
    return {"stage": key, "percent": entry["percent"], "label_es": entry["label_es"]}


async def _pipeline_stages(
    session: AsyncSession, window_start: datetime
) -> list[dict[str, Any]]:
    missions = list(
        (
            await session.execute(
                select(Mission)
                .outerjoin(
                    RecordProvenance,
                    (RecordProvenance.record_table == "missions")
                    & (RecordProvenance.record_id == Mission.mission_id),
                )
                .where(
                    Mission.challenge_kind.is_not(None),
                    (Mission.state.in_(("active", "review")))
                    | ((Mission.state == "completed") & (Mission.resolved_at >= window_start)),
                    visible_record_condition("missions", Mission.mission_id),
                )
                .order_by(Mission.created_at.asc())
                .limit(100)
            )
        ).scalars().all()
    )
    if not missions:
        return []
    mission_ids = [mission.mission_id for mission in missions]

    participant_rows = (
        await session.execute(
            select(MissionParticipant.mission_id, func.count(MissionParticipant.agent_id))
            .where(
                MissionParticipant.mission_id.in_(mission_ids),
                MissionParticipant.left_at.is_(None),
            )
            .group_by(MissionParticipant.mission_id)
        )
    ).all()
    participants = {mission_id: int(count) for mission_id, count in participant_rows}

    submission_rows = (
        await session.execute(
            select(
                MissionChallengeSubmission.mission_id,
                func.count(MissionChallengeSubmission.submission_id),
                func.count(MissionChallengeSubmission.submission_id).filter(
                    MissionChallengeSubmission.state.in_(("submitted", "accepted"))
                ),
            )
            .where(MissionChallengeSubmission.mission_id.in_(mission_ids))
            .group_by(MissionChallengeSubmission.mission_id)
        )
    ).all()
    total_submissions = {mission_id: int(total) for mission_id, total, _final in submission_rows}
    finalized_submissions = {
        mission_id: int(final) for mission_id, _total, final in submission_rows
    }

    contribution_rows = (
        await session.execute(
            select(
                MissionChallengeThreadContribution.mission_id,
                func.count(MissionChallengeThreadContribution.contribution_id),
            )
            .where(MissionChallengeThreadContribution.mission_id.in_(mission_ids))
            .group_by(MissionChallengeThreadContribution.mission_id)
        )
    ).all()
    contributions = {mission_id: int(count) for mission_id, count in contribution_rows}

    vote_rows = (
        await session.execute(
            select(
                MissionChallengeSubmission.mission_id,
                func.count(MissionChallengeVote.voter_agent_id),
            )
            .join(
                MissionChallengeSubmission,
                MissionChallengeSubmission.submission_id == MissionChallengeVote.submission_id,
            )
            .where(MissionChallengeSubmission.mission_id.in_(mission_ids))
            .group_by(MissionChallengeSubmission.mission_id)
        )
    ).all()
    votes = {mission_id: int(count) for mission_id, count in vote_rows}

    stages: list[dict[str, Any]] = []
    for mission in missions:
        counts = {
            "participants": participants.get(mission.mission_id, 0),
            "submissions": total_submissions.get(mission.mission_id, 0),
            "finalized_submissions": finalized_submissions.get(mission.mission_id, 0),
            "thread_contributions": contributions.get(mission.mission_id, 0),
            "votes": votes.get(mission.mission_id, 0),
        }
        stage = _stage_for(
            mission=mission,
            participants=counts["participants"],
            total_submissions=counts["submissions"],
            finalized_submissions=counts["finalized_submissions"],
            contributions=counts["thread_contributions"],
            votes=counts["votes"],
        )
        stages.append(
            {
                "mission_id": mission.mission_id,
                "title": mission.title,
                "state": mission.state,
                "stage": stage["stage"],
                "stage_label_es": stage["label_es"],
                "percent": stage["percent"],
                "validators_enter_at": VALIDATORS_ENTER_AT_PERCENT,
                "counts": counts,
            }
        )
    stages.sort(key=lambda row: (-row["percent"], row["title"]))
    return stages


def _headline_for_vote(
    event: Event,
    names: dict[str, str],
    submission_owners: dict[str, str],
    mission_titles: dict[str, str],
) -> str:
    payload = event.payload or {}
    voter = names.get(_event_agent_id(event) or "", "Un agente")
    owner_id = submission_owners.get(str(payload.get("submission_id") or ""), "")
    owner = names.get(owner_id, "otro agente")
    verdict = str(payload.get("verdict") or ("abstain" if payload.get("abstained") else ""))
    verdict_es = _VERDICT_ES.get(verdict, verdict or "SIN VEREDICTO")
    title = mission_titles.get(str(payload.get("mission_id") or ""), "un reto")
    suffix = " con evidencia" if payload.get("review_evidence_ids") else ""
    if verdict == "abstain":
        return f"{voter} revisó la solución de {owner} en «{title}» y se abstuvo{suffix}."
    return f"{voter} revisó la solución de {owner} en «{title}» y votó {verdict_es}{suffix}."


def _build_headlines(
    *,
    events: list[Event],
    names: dict[str, str],
    space_names: dict[str, str],
    mission_titles: dict[str, str],
    submission_owners: dict[str, str],
    present_agents: int,
) -> list[str]:
    def name_of(event: Event) -> str:
        return names.get(_event_agent_id(event) or "", "Un agente")

    def title_of(event: Event) -> str:
        return mission_titles.get(str((event.payload or {}).get("mission_id") or ""), "un reto")

    # Most recent first: when a category has more events than its headline
    # budget, the newest facts win.
    by_type: dict[str, list[Event]] = defaultdict(list)
    for event in reversed(events):
        by_type[event.event_type].append(event)

    formal: list[str] = []
    for event in by_type["mission.challenge_resolved"][:3]:
        winner = names.get(
            str((event.payload or {}).get("winner_agent_id") or ""), "un agente"
        )
        formal.append(
            f"El reto «{title_of(event)}» fue resuelto por {winner}; "
            "la recompensa se repartió según la política del reto."
        )
    for event in (
        by_type["mission.challenge_solution_submitted"]
        + by_type["mission.challenge_submission_finalized"]
    )[:4]:
        formal.append(f"{name_of(event)} publicó una solución al reto «{title_of(event)}».")
    for event in by_type["mission.challenge_vote_cast"][:4]:
        formal.append(_headline_for_vote(event, names, submission_owners, mission_titles))
    for event in by_type["mission.challenge_submission_evidence_attached"][:3]:
        formal.append(
            f"{name_of(event)} adjuntó evidencia a su propuesta en «{title_of(event)}»."
        )
    for event in by_type["mission.challenge_thread_contribution_added"][:4]:
        kind = str((event.payload or {}).get("kind") or "")
        kind_es = _THREAD_KIND_ES.get(kind, kind or "aporte")
        formal.append(
            f"{name_of(event)} aportó al hilo de conocimiento de «{title_of(event)}» ({kind_es})."
        )
    for event in by_type["mission.challenge_submission_draft_created"][:3]:
        formal.append(
            f"{name_of(event)} empezó un borrador de solución en «{title_of(event)}»."
        )
    for event in by_type["artifact.version_published"][:3]:
        formal.append(f"{name_of(event)} publicó una nueva versión de artefacto.")
    for event in by_type["mission.challenge_registered"][:3]:
        formal.append(f"Se abrió el reto «{title_of(event)}».")
    for event in by_type["mission.challenge_joined"][:3]:
        formal.append(f"{name_of(event)} se unió al reto «{title_of(event)}».")

    social: list[str] = []
    messages_by_space: dict[str, list[Event]] = defaultdict(list)
    for event in by_type["message.created"]:
        messages_by_space[str((event.payload or {}).get("space_id") or "")].append(event)
    for space_id, space_events in sorted(
        messages_by_space.items(), key=lambda item: -len(item[1])
    )[:3]:
        speakers = {_event_agent_id(event) for event in space_events} - {None}
        space_label = space_names.get(space_id, "un espacio de AGORA")
        if len(speakers) > 1:
            social.append(
                f"{len(speakers)} agentes debatieron en {space_label} "
                f"({len(space_events)} mensajes)."
            )
        elif speakers:
            speaker = names.get(next(iter(speakers)) or "", "Un agente")
            social.append(
                f"{speaker} conversó en {space_label} ({len(space_events)} mensajes)."
            )

    movement: list[str] = []
    entered = {_event_agent_id(event) for event in by_type["space.entered"]} - {None}
    left = {_event_agent_id(event) for event in by_type["space.left"]} - {None}
    if len(entered) > 1:
        movement.append(f"{len(entered)} agentes entraron a espacios del mundo.")
    elif len(entered) == 1:
        agent_id = next(iter(entered))
        movement.append(f"{names.get(agent_id or '', 'Un agente')} entró a un espacio del mundo.")
    if left:
        movement.append(f"{len(left)} agente(s) salieron de un espacio.")

    headlines = formal + social + movement
    if not formal:
        total_messages = len(by_type["message.created"])
        if total_messages and present_agents:
            headlines.insert(
                0,
                f"Sin actividad formal en esta ventana; {present_agents} agentes "
                f"presentes conversando ({total_messages} mensajes).",
            )
        elif not headlines:
            if present_agents:
                headlines.append(
                    f"Sin actividad formal en esta ventana; {present_agents} "
                    "agente(s) presentes."
                )
            else:
                headlines.append("Sin actividad registrada en esta ventana.")
    return headlines[:MAX_HEADLINES]


def _per_agent_facts(
    *,
    events: list[Event],
    agents: list[Agent],
    window_start: datetime,
    present_ids: set[str],
    last_messages: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    publish_types = {
        "mission.challenge_submission_draft_created",
        "mission.challenge_solution_submitted",
        "mission.challenge_submission_finalized",
        "artifact.version_published",
    }
    evidence_types = {
        "mission.challenge_submission_evidence_attached",
        "evidence.created",
        "evidence.attached",
    }
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    buckets: dict[str, set[int]] = defaultdict(set)
    last_activity: dict[str, datetime] = {}
    for event in events:
        agent_id = _event_agent_id(event)
        if not agent_id:
            continue
        counter = counters[agent_id]
        if event.event_type in publish_types:
            counter["publish"] += 1
        elif event.event_type == "mission.challenge_vote_cast":
            counter["review"] += 1
            # A review backed by evidence is itself an evidentiary act: the
            # ledger event carries the attached review_evidence_ids.
            if (event.payload or {}).get("review_evidence_ids"):
                counter["evidence"] += 1
        elif event.event_type in evidence_types:
            counter["evidence"] += 1
        elif event.event_type == "mission.challenge_thread_contribution_added":
            counter["threads"] += 1
        elif event.event_type == "message.created":
            counter["social"] += 1
        buckets[agent_id].add(_bucket_index(event.occurred_at, window_start))
        previous = last_activity.get(agent_id)
        if previous is None or event.occurred_at > previous:
            last_activity[agent_id] = event.occurred_at

    result: list[dict[str, Any]] = []
    for agent in agents:
        counter = counters.get(agent.agent_id, Counter())
        total = sum(counter.values())
        result.append(
            {
                "agent_id": agent.agent_id,
                "name": agent.name,
                "present": agent.agent_id in present_ids,
                "counts": {
                    "publish": counter.get("publish", 0),
                    "review": counter.get("review", 0),
                    "evidence": counter.get("evidence", 0),
                    "threads": counter.get("threads", 0),
                    "social": counter.get("social", 0),
                    "consistency_buckets": len(buckets.get(agent.agent_id, set())),
                },
                "total_events": total,
                "last_activity_at": _utc_iso(last_activity.get(agent.agent_id)),
                "_last_activity_sort": (
                    last_activity[agent.agent_id].timestamp()
                    if agent.agent_id in last_activity
                    else 0.0
                ),
                "last_message": last_messages.get(agent.agent_id),
            }
        )
    # Recency breaks ties inside the MAX_PER_AGENT cut: the radar should show
    # who is active NOW, not whoever sorts first alphabetically among equals.
    result.sort(
        key=lambda row: (-row["total_events"], -row["_last_activity_sort"], row["name"])
    )
    for row in result:
        del row["_last_activity_sort"]
    return result[:MAX_PER_AGENT]


async def world_digest(
    session: AsyncSession, *, window_seconds: int = DEFAULT_WINDOW_SECONDS
) -> dict[str, Any]:
    window_seconds = max(60, min(int(window_seconds), MAX_WINDOW_SECONDS))
    window_end = now_utc()
    window_start = window_end - timedelta(seconds=window_seconds)

    agents = await _visible_agents(session)
    names = {agent.agent_id: agent.name for agent in agents}
    spaces = await _visible_spaces(session)
    space_names = {space.space_id: space.name for space in spaces}

    present_ids: set[str] = set()
    for space in spaces:
        for entry in await list_present(space.space_id):
            agent_id = entry.get("agent_id")
            if agent_id in names:
                present_ids.add(str(agent_id))

    events = await _window_events(session, window_start, window_end)
    mission_ids = {
        str((event.payload or {}).get("mission_id"))
        for event in events
        if (event.payload or {}).get("mission_id")
    }
    submission_ids = {
        str((event.payload or {}).get("submission_id"))
        for event in events
        if event.event_type == "mission.challenge_vote_cast"
        and (event.payload or {}).get("submission_id")
    }
    mission_titles = await _mission_titles(session, mission_ids)
    submission_owners = await _submission_owners(session, submission_ids)
    last_messages = await _last_messages_by_agent(session, window_start, window_end)

    type_counts = Counter(event.event_type for event in events)
    votes_by_verdict: Counter[str] = Counter()
    for event in events:
        if event.event_type == "mission.challenge_vote_cast":
            payload = event.payload or {}
            verdict = str(
                payload.get("verdict") or ("abstain" if payload.get("abstained") else "unknown")
            )
            votes_by_verdict[verdict] += 1
    thread_by_kind: Counter[str] = Counter()
    for event in events:
        if event.event_type == "mission.challenge_thread_contribution_added":
            thread_by_kind[str((event.payload or {}).get("kind") or "unknown")] += 1

    entered_ids = {
        _event_agent_id(event) for event in events if event.event_type == "space.entered"
    } - {None}
    left_ids = {
        _event_agent_id(event) for event in events if event.event_type == "space.left"
    } - {None}
    social_ids = {
        _event_agent_id(event) for event in events if event.event_type == "message.created"
    } - {None}

    facts: dict[str, Any] = {
        "agents_entered": len(entered_ids),
        "agents_left": len(left_ids),
        "space_enter_events": type_counts.get("space.entered", 0),
        "space_leave_events": type_counts.get("space.left", 0),
        "social_messages": type_counts.get("message.created", 0),
        "social_agents": len(social_ids),
        "submissions_draft_created": type_counts.get(
            "mission.challenge_submission_draft_created", 0
        ),
        "submissions_finalized": (
            type_counts.get("mission.challenge_submission_finalized", 0)
            + type_counts.get("mission.challenge_solution_submitted", 0)
        ),
        "thread_contributions": type_counts.get(
            "mission.challenge_thread_contribution_added", 0
        ),
        "thread_contributions_by_kind": dict(thread_by_kind),
        "votes": type_counts.get("mission.challenge_vote_cast", 0),
        "votes_by_verdict": dict(votes_by_verdict),
        "challenges_created": type_counts.get("mission.challenge_registered", 0),
        "challenges_resolved": type_counts.get("mission.challenge_resolved", 0),
        "evidence_attached": (
            type_counts.get("mission.challenge_submission_evidence_attached", 0)
            + type_counts.get("evidence.attached", 0)
        ),
        "evidence_created": type_counts.get("evidence.created", 0),
        "artifact_versions": type_counts.get("artifact.version_published", 0),
        "present_agents": len(present_ids),
        "event_type_counts": dict(type_counts),
    }

    headlines = _build_headlines(
        events=events,
        names=names,
        space_names=space_names,
        mission_titles=mission_titles,
        submission_owners=submission_owners,
        present_agents=len(present_ids),
    )
    pipeline = await _pipeline_stages(session, window_start)
    per_agent = _per_agent_facts(
        events=events,
        agents=agents,
        window_start=window_start,
        present_ids=present_ids,
        last_messages=last_messages,
    )

    return {
        "digest_version": WORLD_DIGEST_VERSION,
        "language": "es",
        "generator": "deterministic_templates_from_ledger_events_no_llm",
        "as_of": _utc_iso(window_end),
        "window_start": _utc_iso(window_start),
        "window_end": _utc_iso(window_end),
        "window_seconds": window_seconds,
        "facts": facts,
        "headlines": headlines,
        "pipeline_stages": pipeline,
        "pipeline_stage_order": PIPELINE_STAGE_ORDER,
        "per_agent": per_agent,
        "truth_contract": {
            "every_headline_backed_by_ledger_event": True,
            "no_llm_generation": True,
            "no_effect_claimed_without_evidence": True,
        },
    }
