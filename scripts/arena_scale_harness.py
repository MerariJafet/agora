"""Sprint 06 Arena scale baseline.

Seeds synthetic Challenges/Instances/Submissions/ScoreEvents directly into
Postgres and measures the read paths Arena uses. No model inference, no
arbitrary verifier execution, no external network.

Run: .venv/bin/python scripts/arena_scale_harness.py
"""

import asyncio
import secrets
import time

from sqlalchemy import func, select

N_CHALLENGES = 250
N_INSTANCES = 500
N_SUBMISSIONS = 4000
N_SCORES = 4000


def pctl(values: list[float], p: float) -> float:
    return sorted(values)[max(0, int(len(values) * p) - 1)]


async def seed() -> dict[str, str]:
    from agora_api.db import session_factory
    from agora_api.events import now_utc
    from agora_api.ids import (
        new_agent_id,
        new_arena_challenge_id,
        new_challenge_instance_id,
        new_challenge_version_id,
        new_score_event_id,
        new_submission_id,
    )
    from agora_api.models import (
        Agent,
        ArenaRating,
        Challenge,
        ChallengeInstance,
        ChallengeVersion,
        ScoreEvent,
        Submission,
    )

    async with session_factory()() as session:
        agent_ids = []
        for i in range(32):
            agent_id = new_agent_id()
            agent_ids.append(agent_id)
            session.add(
                Agent(
                    agent_id=agent_id,
                    name=f"ArenaScale-{secrets.token_hex(3)}-{i}",
                    status="registered",
                    created_at=now_utc(),
                    updated_at=now_utc(),
                )
            )
        await session.flush()

        challenge_ids: list[str] = []
        version_ids: list[str] = []
        for i in range(N_CHALLENGES):
            cid = new_arena_challenge_id()
            vid = new_challenge_version_id()
            challenge_ids.append(cid)
            version_ids.append(vid)
            session.add(
                Challenge(
                    challenge_id=cid,
                    title=f"Synthetic Arena Challenge {i}",
                    description="scale baseline",
                    kind=["math", "forecasting", "debate", "coding"][i % 4],
                    domain=["Math", "Forecasting", "Debate", "Software"][i % 4],
                    state="active",
                    created_by_agent_id=agent_ids[0],
                    current_version_id=vid,
                    created_at=now_utc(),
                    updated_at=now_utc(),
                )
            )
            session.add(
                ChallengeVersion(
                    challenge_version_id=vid,
                    challenge_id=cid,
                    version_number=1,
                    complexity={
                        "reasoning": 2,
                        "computation": 2,
                        "data": 1,
                        "domain_expertise": 2,
                        "uncertainty": 1,
                        "adversariality": 1,
                        "verification_cost": 1,
                        "time_budget": 1,
                    },
                    certified_difficulty=1.375,
                    verifier_manifest={"schema_version": "1.0", "verifier_type": "exact_text",
                                       "expected_answer": "ok"},
                    scoring_formula={
                        "schema_version": "1.0",
                        "base_points": 100,
                        "difficulty_weight": 1,
                        "opponent_weight": 0,
                        "validation_weight": 1,
                        "anti_farming_weight": 1,
                    },
                    frozen_at=now_utc(),
                    created_at=now_utc(),
                )
            )
        await session.flush()

        instance_ids: list[str] = []
        for i in range(N_INSTANCES):
            iid = new_challenge_instance_id()
            instance_ids.append(iid)
            j = i % N_CHALLENGES
            session.add(
                ChallengeInstance(
                    challenge_instance_id=iid,
                    challenge_id=challenge_ids[j],
                    challenge_version_id=version_ids[j],
                    state="resolved",
                    max_participants=16,
                    created_at=now_utc(),
                    started_at=now_utc(),
                    resolved_at=now_utc(),
                )
            )
        await session.flush()

        score_rows: list[tuple[str, str, str]] = []
        for i in range(N_SUBMISSIONS):
            sid = new_submission_id()
            agent_id = agent_ids[i % len(agent_ids)]
            instance_id = instance_ids[i % N_INSTANCES]
            session.add(
                Submission(
                    submission_id=sid,
                    challenge_instance_id=instance_id,
                    agent_id=agent_id,
                    answer={"value": "ok"},
                    state="judged",
                    created_at=now_utc(),
                )
            )
            if i < N_SCORES:
                score_rows.append((sid, instance_id, agent_id))
        await session.flush()

        for i, (sid, instance_id, agent_id) in enumerate(score_rows):
            delta = float(100 + (i % 7))
            session.add(
                ScoreEvent(
                    score_event_id=new_score_event_id(),
                    challenge_instance_id=instance_id,
                    submission_id=sid,
                    agent_id=agent_id,
                    score_delta=delta,
                    rating_delta=1.0,
                    formula_version="1.0",
                    factors={"correctness": 1.0, "truth_claim": False},
                    created_at=now_utc(),
                )
            )
        for agent_id in agent_ids:
            session.add(
                ArenaRating(
                    agent_id=agent_id,
                    domain="global",
                    rating=1500,
                    rating_deviation=300,
                    points=0,
                    updated_at=now_utc(),
                )
            )
        await session.commit()

    return {"challenge_id": challenge_ids[0], "instance_id": instance_ids[0]}


async def main() -> None:
    from agora_api.db import session_factory
    from agora_api.models import ArenaRating, Challenge, ChallengeInstance, ScoreEvent, Submission

    print("== AGORA Arena scale harness ==")
    t0 = time.perf_counter()
    seeded = await seed()
    print(
        f"seeded {N_CHALLENGES} challenges, {N_INSTANCES} instances, "
        f"{N_SUBMISSIONS} submissions, {N_SCORES} score events in {time.perf_counter()-t0:.1f}s"
    )

    async with session_factory()() as session:
        async def bench(label: str, fn, n: int = 30) -> None:
            times = []
            for _ in range(n):
                start = time.perf_counter()
                await fn()
                times.append((time.perf_counter() - start) * 1000)
            print(f"{label}: p50 {pctl(times, 0.5):.1f} ms · p95 {pctl(times, 0.95):.1f} ms")

        await bench("challenge list", lambda: session.execute(select(Challenge).limit(50)))
        await bench(
            "instance detail submissions",
            lambda: session.execute(
                select(Submission).where(
                    Submission.challenge_instance_id == seeded["instance_id"]
                )
            ),
        )
        await bench(
            "leaderboard projection",
            lambda: session.execute(
                select(ArenaRating).where(ArenaRating.domain == "global")
                .order_by(ArenaRating.points.desc()).limit(50)
            ),
        )
        await bench(
            "leaderboard rebuild from score events",
            lambda: session.execute(
                select(ScoreEvent.agent_id, func.sum(ScoreEvent.score_delta))
                .group_by(ScoreEvent.agent_id)
                .order_by(func.sum(ScoreEvent.score_delta).desc())
                .limit(50)
            ),
        )
        await bench(
            "instance list",
            lambda: session.execute(select(ChallengeInstance).limit(50)),
        )


if __name__ == "__main__":
    asyncio.run(main())
