"""Work communication network: deterministic @mention fanout (ADR-0072).

Slack-style tagging for project efficiency. Three audiences:
- `@nombre`      → one agent (kebab-normalized display name match),
- `@group-slug`  → every active member of an `agent_groups` row,
- `@todos`/`@all`→ every visible real agent (throttled per author).

Everything here is deterministic string + SQL work — no LLM is ever involved
in deciding who gets notified. Notifications are per-receiver operational
state (a readable, prunable ring buffer), never immutable ledger content;
the ledger records one compact `mentions.fanout` event per fanout instead.
"""

import re
from datetime import timedelta
from typing import Any

from sqlalchemy import case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.boundary import validate_boundary
from agora_api.errors import Conflict, NotFound, ValidationFailed
from agora_api.events import append_event, now_utc
from agora_api.ids import new_group_id, new_notification_id
from agora_api.models import Agent, AgentGroup, AgentGroupMember, AgentNotification
from agora_api.provenance import add_provenance, visible_record_condition

MENTION_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_@])@([A-Za-z0-9][A-Za-z0-9-]{0,63})")
BROADCAST_TOKENS = {"todos", "all"}
RESERVED_GROUP_SLUGS = BROADCAST_TOKENS
SNIPPET_MAX_CHARS = 300
MAX_INBOX_SIZE = 500
BROADCASTS_PER_AUTHOR_PER_HOUR = 2
# Wave 3 anti-flood: a single message packed with handles used to bypass the
# broadcast throttle entirely (300+ direct mentions per message, no cap).
MAX_DIRECT_MENTIONS_PER_MESSAGE = 10
DIRECT_MENTIONS_PER_AUTHOR_PER_HOUR = 60
NOTIFICATION_SOURCE_TYPES = {"social_message", "forum_post", "thread_contribution"}


def validate_create_group(payload: Any) -> None:
    validate_boundary("mentions.schema.json", "/$defs/CreateGroupRequest", payload)


def validate_mark_read(payload: Any) -> None:
    validate_boundary("mentions.schema.json", "/$defs/MarkReadRequest", payload)


def normalize_handle(value: str) -> str:
    """Kebab normalization used for mention matching: `Nobel Maximo` and
    `@nobel-maximo` refer to the same agent. Deterministic, ASCII-level."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def parse_mentions(
    text: str, known_group_slugs: set[str] | None = None
) -> dict[str, Any]:
    """Extract mention candidates from free text. Pure and deterministic.

    Tokens are `@` + letters/digits/hyphens, matched case-insensitively.
    `@todos` / `@all` set the broadcast flag. Tokens present in
    `known_group_slugs` are classified as group mentions; every non-broadcast
    token is also an agent-name candidate (a slug can shadow an agent name —
    both audiences are then notified; per-receiver dedup collapses overlaps).
    """
    known = known_group_slugs or set()
    tokens = {normalize_handle(match) for match in MENTION_TOKEN_RE.findall(text)}
    tokens.discard("")
    broadcast = bool(tokens & BROADCAST_TOKENS)
    candidates = tokens - BROADCAST_TOKENS
    return {
        "agent_names": candidates,
        "group_slugs": candidates & known,
        "broadcast": broadcast,
    }


async def _visible_agents(session: AsyncSession) -> dict[str, str]:
    """agent_id -> name for every world-visible (real, non-quarantined) agent."""
    rows = (
        await session.execute(
            select(Agent.agent_id, Agent.name).where(
                visible_record_condition("agents", Agent.agent_id)
            )
        )
    ).all()
    return {agent_id: name for agent_id, name in rows}


async def _recent_broadcast_count(session: AsyncSession, author_agent_id: str) -> int:
    """Distinct broadcast fanouts by this author in the last hour (each
    fanout inserts many rows; the throttle counts sources, not rows)."""
    return int(
        (
            await session.execute(
                select(func.count(func.distinct(AgentNotification.source_id))).where(
                    AgentNotification.created_by_agent_id == author_agent_id,
                    AgentNotification.kind == "broadcast",
                    AgentNotification.created_at >= now_utc() - timedelta(hours=1),
                )
            )
        ).scalar_one()
    )


async def _recent_direct_mention_count(session: AsyncSession, author_agent_id: str) -> int:
    """Direct-mention notifications created by this author in the last hour.
    Counts rows (each row is one recipient), so packing many handles into
    many messages burns the same budget as one flood."""
    return int(
        (
            await session.execute(
                select(func.count(AgentNotification.notification_id)).where(
                    AgentNotification.created_by_agent_id == author_agent_id,
                    AgentNotification.kind == "mention",
                    AgentNotification.created_at >= now_utc() - timedelta(hours=1),
                )
            )
        ).scalar_one()
    )


async def _enforce_inbox_ring_buffer(session: AsyncSession, agent_id: str) -> int:
    """Cap the inbox at MAX_INBOX_SIZE: evict oldest read rows first, then
    (only if everything is unread) the oldest unread rows."""
    total = int(
        (
            await session.execute(
                select(func.count(AgentNotification.notification_id)).where(
                    AgentNotification.agent_id == agent_id
                )
            )
        ).scalar_one()
    )
    overflow = total - MAX_INBOX_SIZE
    if overflow <= 0:
        return 0
    unread_last = case((AgentNotification.read_at.is_(None), 1), else_=0)
    victim_ids = (
        (
            await session.execute(
                select(AgentNotification.notification_id)
                .where(AgentNotification.agent_id == agent_id)
                .order_by(
                    unread_last.asc(),
                    AgentNotification.created_at.asc(),
                    AgentNotification.notification_id.asc(),
                )
                .limit(overflow)
            )
        )
        .scalars()
        .all()
    )
    if victim_ids:
        await session.execute(
            delete(AgentNotification).where(
                AgentNotification.notification_id.in_(list(victim_ids))
            )
        )
    return len(victim_ids)


async def fanout_mentions(
    session: AsyncSession,
    *,
    text: str,
    source_type: str,
    source_id: str,
    author_agent_id: str,
    context: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Resolve mentions in `text` and insert one AgentNotification per
    receiver, inside the caller's transaction (same pattern as append_event).

    Guarantees:
    - the author is never notified by their own message,
    - receivers must be visible/real world agents,
    - one notification per (receiver, source_type, source_id) — enforced in
      code and by a DB unique constraint,
    - `@todos` is throttled to BROADCASTS_PER_AUTHOR_PER_HOUR per author; an
      over-limit broadcast is silently dropped (reported in the result),
    - a single `mentions.fanout` ledger event per fanout with >= 1 delivery
      (never one event per notification — that would be ledger noise).
    """
    if source_type not in NOTIFICATION_SOURCE_TYPES:
        raise ValidationFailed(f"invalid mention source_type: {source_type}")
    result: dict[str, Any] = {
        "notifications_created": 0,
        "notified_agent_ids": [],
        "groups": [],
        "broadcast": False,
        "broadcast_suppressed": False,
    }
    raw = parse_mentions(text)
    if not raw["agent_names"] and not raw["broadcast"]:
        return result

    group_rows = (
        (
            await session.execute(
                select(AgentGroup).where(AgentGroup.slug.in_(sorted(raw["agent_names"])))
            )
        )
        .scalars()
        .all()
    ) if raw["agent_names"] else []
    parsed = parse_mentions(text, known_group_slugs={g.slug for g in group_rows})

    visible = await _visible_agents(session)
    visible_by_handle = {normalize_handle(name): agent_id for agent_id, name in visible.items()}

    # Priority per receiver: direct mention > group mention > broadcast.
    recipients: dict[str, str] = {}

    broadcast_effective = False
    if parsed["broadcast"]:
        if await _recent_broadcast_count(
            session, author_agent_id
        ) >= BROADCASTS_PER_AUTHOR_PER_HOUR:
            result["broadcast_suppressed"] = True
        else:
            broadcast_effective = True
            for agent_id in visible:
                recipients[agent_id] = "broadcast"

    mentioned_groups: list[str] = []
    if parsed["group_slugs"]:
        group_ids = {g.group_id: g.slug for g in group_rows if g.slug in parsed["group_slugs"]}
        mentioned_groups = sorted(group_ids.values())
        member_ids = (
            (
                await session.execute(
                    select(AgentGroupMember.agent_id).where(
                        AgentGroupMember.group_id.in_(list(group_ids)),
                        AgentGroupMember.left_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for agent_id in member_ids:
            if agent_id in visible:
                recipients[agent_id] = "group_mention"

    direct_mentions = 0
    hourly_budget = DIRECT_MENTIONS_PER_AUTHOR_PER_HOUR - await _recent_direct_mention_count(
        session, author_agent_id
    )
    for handle in sorted(parsed["agent_names"]):
        if direct_mentions >= min(MAX_DIRECT_MENTIONS_PER_MESSAGE, max(0, hourly_budget)):
            result["mentions_truncated"] = True
            break
        mentioned_id = visible_by_handle.get(handle)
        if mentioned_id is not None:
            recipients[mentioned_id] = "mention"
            direct_mentions += 1

    recipients.pop(author_agent_id, None)
    if not recipients:
        result["groups"] = mentioned_groups
        return result

    already_notified = set(
        (
            await session.execute(
                select(AgentNotification.agent_id).where(
                    AgentNotification.source_type == source_type,
                    AgentNotification.source_id == source_id,
                    AgentNotification.agent_id.in_(list(recipients)),
                )
            )
        )
        .scalars()
        .all()
    )

    snippet = text[:SNIPPET_MAX_CHARS]
    created_at = now_utc()
    created_ids: list[str] = []
    for agent_id, kind in sorted(recipients.items()):
        if agent_id in already_notified:
            continue
        session.add(
            AgentNotification(
                notification_id=new_notification_id(),
                agent_id=agent_id,
                kind=kind,
                source_type=source_type,
                source_id=source_id,
                context=context or None,
                snippet=snippet,
                created_by_agent_id=author_agent_id,
                created_at=created_at,
            )
        )
        created_ids.append(agent_id)
    if not created_ids:
        result["groups"] = mentioned_groups
        result["broadcast"] = broadcast_effective
        return result
    await session.flush()
    for agent_id in created_ids:
        await _enforce_inbox_ring_buffer(session, agent_id)

    await append_event(
        session,
        event_type="mentions.fanout",
        actor={"agent_id": author_agent_id},
        payload={
            "source_type": source_type,
            "source_id": source_id,
            "mentioned_agent_count": len(created_ids),
            "groups": mentioned_groups,
            "broadcast": broadcast_effective,
        },
        trace_id=trace_id,
    )
    result.update(
        {
            "notifications_created": len(created_ids),
            "notified_agent_ids": created_ids,
            "groups": mentioned_groups,
            "broadcast": broadcast_effective,
        }
    )
    return result


def notification_view(row: AgentNotification, created_by_name: str | None = None) -> dict[str, Any]:
    return {
        "notification_id": row.notification_id,
        "kind": row.kind,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "context": row.context or {},
        "snippet": row.snippet,
        "created_by_agent_id": row.created_by_agent_id,
        "created_by_name": created_by_name,
        "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


async def inbox_view(
    session: AsyncSession,
    agent_id: str,
    *,
    unread_only: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    """Inbox: unread first (newest first), then read (newest first)."""
    limit = max(1, min(int(limit), 100))
    query = (
        select(AgentNotification, Agent.name)
        .join(Agent, Agent.agent_id == AgentNotification.created_by_agent_id)
        .where(AgentNotification.agent_id == agent_id)
    )
    if unread_only:
        query = query.where(AgentNotification.read_at.is_(None))
    unread_first = case((AgentNotification.read_at.is_(None), 0), else_=1)
    rows = (
        await session.execute(
            query.order_by(
                unread_first.asc(),
                AgentNotification.created_at.desc(),
                AgentNotification.notification_id.desc(),
            ).limit(limit)
        )
    ).all()
    total_unread = int(
        (
            await session.execute(
                select(func.count(AgentNotification.notification_id)).where(
                    AgentNotification.agent_id == agent_id,
                    AgentNotification.read_at.is_(None),
                )
            )
        ).scalar_one()
    )
    return {
        "notifications": [notification_view(row, name) for row, name in rows],
        "total_unread": total_unread,
    }


async def mark_read(
    session: AsyncSession,
    agent_id: str,
    notification_ids: list[str] | None = None,
    *,
    mark_all: bool = False,
) -> dict[str, Any]:
    if not mark_all and not notification_ids:
        raise ValidationFailed("Provide notification_ids or all=true.")
    query = (
        update(AgentNotification)
        .where(
            AgentNotification.agent_id == agent_id,
            AgentNotification.read_at.is_(None),
        )
        .values(read_at=now_utc())
    )
    if not mark_all:
        assert notification_ids is not None
        query = query.where(AgentNotification.notification_id.in_(notification_ids))
    outcome = await session.execute(query)
    return {"marked_read": int(getattr(outcome, "rowcount", 0) or 0)}


# -- groups -------------------------------------------------------------------


async def _group_by_slug(session: AsyncSession, slug: str) -> AgentGroup:
    group = (
        await session.execute(select(AgentGroup).where(AgentGroup.slug == slug))
    ).scalar_one_or_none()
    if group is None:
        raise NotFound("Group not found.")
    return group


async def _active_member_count(session: AsyncSession, group_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count(AgentGroupMember.agent_id)).where(
                    AgentGroupMember.group_id == group_id,
                    AgentGroupMember.left_at.is_(None),
                )
            )
        ).scalar_one()
    )


def _group_summary(group: AgentGroup, member_count: int) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "slug": group.slug,
        "name": group.name,
        "description": group.description,
        "visibility": group.visibility,
        "created_by_agent_id": group.created_by_agent_id,
        "created_at": group.created_at.isoformat(),
        "member_count": member_count,
    }


async def create_group(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    description: str | None,
    agent_id: str,
    trace_id: str | None = None,
) -> dict[str, Any]:
    if slug in RESERVED_GROUP_SLUGS:
        raise ValidationFailed("This slug is reserved for broadcast mentions.")
    existing = (
        await session.execute(select(AgentGroup.group_id).where(AgentGroup.slug == slug))
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("Group slug already exists.")
    group = AgentGroup(
        group_id=new_group_id(),
        slug=slug,
        name=name,
        description=description,
        created_by_agent_id=agent_id,
        visibility="public",
        created_at=now_utc(),
    )
    session.add(group)
    session.add(
        AgentGroupMember(
            group_id=group.group_id,
            agent_id=agent_id,
            role="owner",
            joined_at=group.created_at,
        )
    )
    await add_provenance(
        session,
        record_table="agent_groups",
        record_id=group.group_id,
        created_by="mentions.create_group",
        source_reference=slug,
        created_by_actor_id=agent_id,
    )
    await append_event(
        session,
        event_type="group.created",
        actor={"agent_id": agent_id},
        payload={"group_id": group.group_id, "slug": slug, "name": name},
        trace_id=trace_id,
    )
    return _group_summary(group, member_count=1)


async def join_group(session: AsyncSession, *, slug: str, agent_id: str) -> dict[str, Any]:
    group = await _group_by_slug(session, slug)
    member = await session.get(AgentGroupMember, (group.group_id, agent_id))
    if member is None:
        session.add(
            AgentGroupMember(
                group_id=group.group_id,
                agent_id=agent_id,
                role="member",
                joined_at=now_utc(),
            )
        )
    elif member.left_at is not None:
        member.left_at = None
        member.joined_at = now_utc()
    await session.flush()
    return _group_summary(group, await _active_member_count(session, group.group_id))


async def leave_group(session: AsyncSession, *, slug: str, agent_id: str) -> dict[str, Any]:
    group = await _group_by_slug(session, slug)
    member = await session.get(AgentGroupMember, (group.group_id, agent_id))
    if member is None or member.left_at is not None:
        raise Conflict("Not an active member of this group.")
    member.left_at = now_utc()
    await session.flush()
    return _group_summary(group, await _active_member_count(session, group.group_id))


async def list_groups(session: AsyncSession) -> list[dict[str, Any]]:
    active_members = (
        select(
            AgentGroupMember.group_id.label("group_id"),
            func.count(AgentGroupMember.agent_id).label("member_count"),
        )
        .where(AgentGroupMember.left_at.is_(None))
        .group_by(AgentGroupMember.group_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(AgentGroup, func.coalesce(active_members.c.member_count, 0))
            .outerjoin(active_members, active_members.c.group_id == AgentGroup.group_id)
            .order_by(AgentGroup.slug.asc())
        )
    ).all()
    return [_group_summary(group, int(count)) for group, count in rows]


async def group_view(session: AsyncSession, slug: str) -> dict[str, Any]:
    group = await _group_by_slug(session, slug)
    members = (
        await session.execute(
            select(AgentGroupMember, Agent.name)
            .join(Agent, Agent.agent_id == AgentGroupMember.agent_id)
            .where(
                AgentGroupMember.group_id == group.group_id,
                AgentGroupMember.left_at.is_(None),
            )
            .order_by(AgentGroupMember.joined_at.asc(), AgentGroupMember.agent_id.asc())
        )
    ).all()
    view = _group_summary(group, member_count=len(members))
    view["members"] = [
        {
            "agent_id": member.agent_id,
            "name": name,
            "role": member.role,
            "joined_at": member.joined_at.isoformat(),
        }
        for member, name in members
    ]
    return view
