"""Genesis wave 2 challenge bootstrap tests.

Run only with scripts/run-isolated-tests.sh. Production guard cases monkeypatch
AGORA_ENV for the settings reader only; database isolation stays TEST.
"""

import pytest
from agora_api.config import get_settings
from agora_api.db import session_factory
from agora_api.errors import Conflict
from agora_api.forum_consensus_service import (
    GENESIS_WAVE2_CHALLENGES,
    GENESIS_WAVE2_SEQUENCE_START,
    ensure_genesis_wave2_challenges,
)
from agora_api.models import RecordProvenance, TokoinLedgerEntry
from agora_api.provenance import reclassify_provenance
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

ENDPOINT = "/v1/world/genesis/wave2/bootstrap"
TRAINING_ENDPOINT = "/v1/forums/research-genesis/ensure-training-challenges"
WAVE2_SEQUENCES = set(
    range(
        GENESIS_WAVE2_SEQUENCE_START,
        GENESIS_WAVE2_SEQUENCE_START + len(GENESIS_WAVE2_CHALLENGES),
    )
)


async def _real_agent(api_client, name: str) -> dict:
    reg = await register_agent(api_client, SigningKeypair(), name)
    async with session_factory()() as session:
        await reclassify_provenance(
            session,
            record_table="agents",
            record_id=reg["agent_id"],
            new_class="real",
            actor="test.owner_authorized",
            reason="test real genesis wave 2 cohort",
            evidence_reference=name,
        )
        await session.commit()
    return reg


async def _ledger_count() -> int:
    async with session_factory()() as session:
        return (
            await session.execute(select(func.count(TokoinLedgerEntry.entry_id)))
        ).scalar_one()


async def test_wave2_bootstrap_creates_five_rewarded_missions_idempotently(
    api_client, unique_name
):
    await api_client.post("/v1/world/magna/bootstrap")
    await _real_agent(api_client, f"{unique_name}-w2-a")
    await _real_agent(api_client, f"{unique_name}-w2-b")
    ledger_before = await _ledger_count()

    ensured = await api_client.post(ENDPOINT)
    assert ensured.status_code == 201, ensured.text
    body = ensured.json()
    assert body["wave"] == 2
    assert body["challenge_kind"] == "genesis_training"
    assert body["created_count"] == 5
    assert body["existing_count"] == 0
    assert body["upgraded_count"] == 0
    assert body["target_count"] == 5
    assert body["reward_aceros_per_challenge"] == 100_000_000
    assert body["reward_requires_resolved_verified"] is True
    assert body["tokoin_moved"] is False
    assert body["agents_modified"] is False
    assert {item["sequence"] for item in body["created"]} == WAVE2_SEQUENCES
    assert all(item["reward_aceros"] == 100_000_000 for item in body["created"])

    repeated = await api_client.post(ENDPOINT)
    assert repeated.status_code == 201, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["created_count"] == 0
    assert repeated_body["existing_count"] == 5
    assert repeated_body["upgraded_count"] == 0

    active = (await api_client.get("/v1/mission-challenges/active")).json()
    wave2 = [
        item
        for item in active["mission_challenges"]
        if item["challenge_kind"] == "genesis_training"
        and item["challenge_problem"].get("genesis_wave") == 2
    ]
    assert len(wave2) == 5
    assert {item["challenge_problem"]["genesis_sequence"] for item in wave2} == WAVE2_SEQUENCES
    assert all(item["reward_aceros"] == 100_000_000 for item in wave2)
    assert all(item["challenge_problem"]["real_world_open_problem"] is False for item in wave2)
    assert all(
        item["completion_policy"]["reward_requires_resolved_verified"] is True
        and item["completion_policy"]["reward_split"]
        == {
            "proposal_author_bps": 100,
            "value_contributor_pool_bps": 1000,
            "winner_or_team_bps": 8900,
        }
        for item in wave2
    )

    mission_ids = [item["mission_id"] for item in body["created"]]
    async with session_factory()() as session:
        provenance_rows = (
            await session.execute(
                select(
                    RecordProvenance.created_by_actor_or_process,
                    RecordProvenance.source_reference,
                ).where(
                    RecordProvenance.record_table == "missions",
                    RecordProvenance.record_id.in_(mission_ids),
                )
            )
        ).all()
    assert len(provenance_rows) == 5
    assert {row[0] for row in provenance_rows} == {"genesis_wave2.ensure"}
    assert {row[1] for row in provenance_rows} == {
        spec["slug"] for spec in GENESIS_WAVE2_CHALLENGES
    }

    # Wave 1 keeps its own disjoint sequences after the refactor: the training
    # bootstrap still creates its full set and re-running wave 2 stays stable.
    training = await api_client.post(TRAINING_ENDPOINT)
    assert training.status_code == 201, training.text
    training_body = training.json()
    assert training_body["created_count"] == 10
    assert training_body["existing_count"] == 0
    assert training_body["target_count"] == 10

    wave2_again = await api_client.post(ENDPOINT)
    assert wave2_again.status_code == 201, wave2_again.text
    assert wave2_again.json()["created_count"] == 0
    assert wave2_again.json()["existing_count"] == 5

    training_again = await api_client.post(TRAINING_ENDPOINT)
    assert training_again.status_code == 201, training_again.text
    assert training_again.json()["created_count"] == 0
    assert training_again.json()["existing_count"] == 10

    assert await _ledger_count() == ledger_before


async def test_wave2_fails_closed_in_production_without_release_gate(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("AGORA_ENV", "production")
    monkeypatch.delenv("AGORA_RESEARCH_WINDOW_PRODUCTION_OPTIN", raising=False)
    try:
        assert get_settings().is_production is True
        assert get_settings().research_window_production_optin is False
        async with session_factory()() as session:
            with pytest.raises(Conflict):
                await ensure_genesis_wave2_challenges(session)
    finally:
        get_settings.cache_clear()


async def test_wave2_allowed_in_production_with_release_gate(api_client, unique_name):
    await api_client.post("/v1/world/magna/bootstrap")
    await _real_agent(api_client, f"{unique_name}-w2-optin")

    monkeypatch = pytest.MonkeyPatch()
    get_settings.cache_clear()
    monkeypatch.setenv("AGORA_ENV", "production")
    monkeypatch.setenv("AGORA_RESEARCH_WINDOW_PRODUCTION_OPTIN", "true")
    try:
        assert get_settings().is_production is True
        assert get_settings().research_window_production_optin is True
        async with session_factory()() as session:
            result = await ensure_genesis_wave2_challenges(session)
            await session.commit()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()

    assert result["target_count"] == 5
    assert result["created_count"] + result["existing_count"] == 5
    assert result["tokoin_moved"] is False
    assert result["agents_modified"] is False
