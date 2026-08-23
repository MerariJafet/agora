"""Bounded argument-graph neighborhood queries (S4-T08, ADR-0022).

PostgreSQL, not a graph database: at Sprint 04 scale a claim's neighborhood
is a handful of indexed lookups. Depth 1 is two indexed queries (outgoing +
incoming relations); depth 2 repeats that for the depth-1 frontier with a
row cap per level so the traversal cannot explode. There is no recursive CTE
and no unbounded default — every query call takes explicit limits.
"""

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.claims_service import claim_view, relation_view
from agora_api.errors import NotFound, ValidationFailed
from agora_api.models import Claim, ClaimEvidence, ClaimRelation

MAX_DEPTH = 2
MAX_RELATIONS_PER_LEVEL = 200
MAX_NODES = 300


async def _relations_touching(
    session: AsyncSession, claim_ids: set[str], limit: int
) -> list[ClaimRelation]:
    rows = (
        await session.execute(
            select(ClaimRelation)
            .where(
                ClaimRelation.status == "active",
                or_(
                    ClaimRelation.source_claim_id.in_(claim_ids),
                    ClaimRelation.target_claim_id.in_(claim_ids),
                ),
            )
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def _evidence_counts(session: AsyncSession, claim_ids: list[str]) -> dict[str, int]:
    if not claim_ids:
        return {}
    rows = (
        await session.execute(
            select(ClaimEvidence.claim_id, func.count())
            .where(ClaimEvidence.claim_id.in_(claim_ids))
            .group_by(ClaimEvidence.claim_id)
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def get_neighborhood(
    session: AsyncSession, *, claim_id: str, depth: int = 1
) -> dict[str, Any]:
    if depth < 1 or depth > MAX_DEPTH:
        raise ValidationFailed(f"depth must be between 1 and {MAX_DEPTH}.")
    root = await session.get(Claim, claim_id)
    if root is None:
        raise NotFound("Claim not found.")

    seen_claim_ids = {claim_id}
    all_relations: dict[str, ClaimRelation] = {}
    frontier = {claim_id}

    for _level in range(depth):
        if len(seen_claim_ids) >= MAX_NODES:
            break
        relations = await _relations_touching(session, frontier, MAX_RELATIONS_PER_LEVEL)
        next_frontier: set[str] = set()
        for relation in relations:
            all_relations[relation.relation_id] = relation
            for cid in (relation.source_claim_id, relation.target_claim_id):
                if cid not in seen_claim_ids and len(seen_claim_ids) < MAX_NODES:
                    seen_claim_ids.add(cid)
                    next_frontier.add(cid)
        frontier = next_frontier
        if not frontier:
            break

    claims = (
        await session.execute(select(Claim).where(Claim.claim_id.in_(seen_claim_ids)))
    ).scalars().all()
    evidence_counts = await _evidence_counts(session, list(seen_claim_ids))

    return {
        "root_claim_id": claim_id,
        "depth": depth,
        "claims": [
            {**claim_view(c), "evidence_count": evidence_counts.get(c.claim_id, 0)}
            for c in claims
        ],
        "relations": [relation_view(r) for r in all_relations.values()],
        "truncated": len(seen_claim_ids) >= MAX_NODES,
    }
