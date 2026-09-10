"""Authenticated TEST research challenge creation through the normal event ledger."""

from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from agora_api.config import get_settings
from agora_api.errors import NotFound
from agora_api.events import append_event, now_utc
from agora_api.ids import new_mission_id, new_space_id
from agora_api.models import Mission, Space
from agora_api.provenance import add_provenance
from agora_api.research_export import content_hash


class TestChallengeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=4000)
    description: str = Field(min_length=1, max_length=8000)
    experiment_id: str = Field(pattern=r"^LLM-SCI-00[1-5]$")
    parameters: dict = Field(default_factory=dict)


async def create_test_challenge(session, agent, body, trace_id=None):
    if get_settings().env != "test":
        raise NotFound("TEST research challenge endpoint disabled.")
    at = now_utc()
    mid, sid = new_mission_id(), new_space_id()
    session.add(
        Space(
            space_id=sid,
            slug="v03-" + mid.lower(),
            name="AGORA V03 TEST",
            kind="mission_challenge",
            description="Isolated scientific campaign",
            evidence_policy="optional",
            created_at=at,
        )
    )
    await session.flush()
    await add_provenance(
        session,
        record_table="spaces",
        record_id=sid,
        created_by=agent.agent_id,
        source_reference=body.experiment_id,
    )
    mission = Mission(
        mission_id=mid,
        title=body.title,
        objective=body.objective,
        description=body.description,
        state="active",
        visibility="public",
        hosting_space_id=sid,
        related_claim_ids=[],
        deadline_at=at + timedelta(days=30),
        reward_aceros=0,
        challenge_kind="research_consensus_test",
        challenge_problem={
            "status": "open_problem",
            "unsolved_required": False,
            "experiment_id": body.experiment_id,
            "parameters": body.parameters,
            "mode": "TEST_NON_RECOGNIZABLE",
        },
        challenge_space_color="#35d0ff",
        resolution_policy="institutional_research_v1",
        max_participants=20,
        completion_policy={"institutional_quorum": 2},
        created_by_agent_id=agent.agent_id,
        created_by_agent_version_id=agent.current_version_id,
        created_at=at,
        activated_at=at,
    )
    session.add(mission)
    await session.flush()
    await add_provenance(
        session,
        record_table="missions",
        record_id=mid,
        created_by=agent.agent_id,
        source_reference=body.experiment_id,
    )
    event = await append_event(
        session,
        event_type="mission.created",
        actor={"agent_id": agent.agent_id, "agent_version_id": agent.current_version_id},
        payload={
            "mission_id": mid,
            "experiment_id": body.experiment_id,
            "title": body.title,
            "request_hash": content_hash(body.model_dump(), "agora.test.challenge.v03"),
            "parameters": body.parameters,
            "reward_aceros": 0,
            "mode": "TEST_NON_RECOGNIZABLE",
        },
        correlation_id=mid,
        trace_id=trace_id,
    )
    return {
        "mission_id": mid,
        "challenge_id": mid,
        "event_id": event.event_id,
        "request_hash": content_hash(body.model_dump(), "agora.test.challenge.v03"),
        "reward_aceros": 0,
        "resolution_policy": "institutional_research_v1",
        "mode": "TEST_NON_RECOGNIZABLE",
    }
