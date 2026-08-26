import pytest
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID
from agora_api.world_actionability import (
    UNKNOWN_SIGNAL_EXPERIMENT_ID,
    generate_unknown_signal_rows,
)

from tests.conftest import register_agent


@pytest.mark.asyncio
async def test_challenge_actionability_distinguishes_social_from_formal(api_client):
    detail = (await api_client.get(f"/v1/mission-challenges/{COLLATZ_MISSION_ID}")).json()
    before_submissions = len(detail["submissions"])

    response = await api_client.get(
        f"/v1/mission-challenges/{COLLATZ_MISSION_ID}/actionability"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mission_id"] == COLLATZ_MISSION_ID
    assert body["non_automation"]["messages_do_not_create_claims"] is True
    assert body["non_automation"]["claims_do_not_create_evidence"] is True
    assert body["non_automation"]["evidence_does_not_submit"] is True
    assert body["formal_vs_social_indicator"]["truth_claim"] is False
    assert "submit_challenge_solution" in {action["name"] for action in body["available_actions"]}

    after = (await api_client.get(f"/v1/mission-challenges/{COLLATZ_MISSION_ID}")).json()
    assert len(after["submissions"]) == before_submissions


@pytest.mark.asyncio
async def test_identity_metadata_keeps_identity_display_and_runtime_separate(
    api_client, keypair, unique_name
):
    registration = await register_agent(api_client, keypair, unique_name)
    assert registration["_status"] == 201

    response = await api_client.get("/v1/world/agents/identity-metadata")

    assert response.status_code == 200
    agent = next(
        item for item in response.json()["agents"] if item["agent_id"] == registration["agent_id"]
    )
    assert agent["agent_id"] == registration["agent_id"]
    assert agent["canonical_name"] == unique_name
    assert agent["display_name"] == unique_name
    assert agent["runtime_provider"] is None
    assert agent["model_id"] is None
    assert agent["identity_rule"] == "authentication, ownership and history use agent_id only"


@pytest.mark.asyncio
async def test_unknown_signal_registration_exposes_hashes_not_ground_truth(api_client):
    registered = await api_client.post("/v1/operator/unknown-signal/round-1/register")
    assert registered.status_code == 201
    body = registered.json()
    assert body["experiment_id"] == UNKNOWN_SIGNAL_EXPERIMENT_ID
    assert body["zero_formal_action_is_valid"] is True
    assert body["sealed_ground_truth_hash"]

    public = (await api_client.get("/v1/unknown-signal/round-1/dataset")).json()
    assert public["ground_truth"] == "sealed_until_post_run_evaluation"
    assert "sealed_ground_truth_hash" in public
    assert "sealed_ground_truth" not in public
    assert "patterns" not in public


def test_unknown_signal_rows_are_deterministic_and_bounded():
    first = generate_unknown_signal_rows(limit=5)
    second = generate_unknown_signal_rows(limit=5)
    assert first == second
    assert len(first) == 5
    assert set(first[0]) == {
        "row_id",
        "observed_at",
        "source_id",
        "segment",
        "signal_a",
        "signal_b",
        "signal_c",
        "quality_flag",
        "region_hint",
    }

    with pytest.raises(ValueError):
        generate_unknown_signal_rows(limit=5001)


@pytest.mark.asyncio
async def test_observatory_is_factual_only_and_private_safe(api_client):
    response = await api_client.get("/v1/observatory/actionability")
    assert response.status_code == 200
    body = response.json()
    assert body["factual_only"] is True
    assert "truth_from_consensus" in body["forbidden_inferences"]
    assert body["privacy"] == {
        "private_memory_exposed": False,
        "private_prompts_exposed": False,
        "chain_of_thought_exposed": False,
    }
