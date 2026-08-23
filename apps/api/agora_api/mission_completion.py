"""Mission completion policy evaluator (S5-T19, ADR-0026).

The completion_policy is frozen at activation (missions_service.activate_mission
never lets it change afterward). Evaluation is a pure read of current state
plus a transactional, idempotent write when conditions are met — calling
`evaluate` twice on an already-completed Mission is a safe no-op.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.artifacts_service import independent_review_count
from agora_api.events import append_event, now_utc
from agora_api.models import ArtifactVersion, Mission, MissionTask


async def evaluate_completion(
    session: AsyncSession, *, mission: Mission, trace_id: str | None
) -> bool:
    """Returns True if the Mission was (or already is) completed."""
    if mission.state == "completed":
        return True
    if mission.state not in ("active", "review", "blocked"):
        return False

    policy: dict[str, Any] = mission.completion_policy or {}
    tasks = (
        await session.execute(select(MissionTask).where(MissionTask.mission_id == mission.mission_id))
    ).scalars().all()

    if policy.get("no_open_needs_revision_tasks", True):
        if any(t.state == "needs_revision" for t in tasks):
            return False

    required_tasks = [t for t in tasks if t.state != "cancelled"]
    if policy.get("all_required_tasks_accepted", True):
        if not required_tasks or any(t.state != "accepted" for t in required_tasks):
            return False

    final_version_ids: list[str] = []
    for task in required_tasks:
        if task.result_artifact_version_id:
            final_version_ids.append(task.result_artifact_version_id)
    final_version_ids = sorted(set(final_version_ids))

    if policy.get("at_least_one_final_artifact", True) and not final_version_ids:
        return False

    min_reviews = policy.get("minimum_independent_reviews", 0)
    if min_reviews:
        for version_id in final_version_ids:
            if await independent_review_count(session, version_id) < min_reviews:
                return False

    mission.state = "completed"
    mission.completed_at = now_utc()
    mission.final_artifact_version_ids = final_version_ids
    await append_event(
        session,
        event_type="mission.completed",
        actor={"agent_id": mission.created_by_agent_id},
        payload={
            "mission_id": mission.mission_id,
            "final_artifact_version_ids": final_version_ids,
        },
        trace_id=trace_id,
    )
    return True
