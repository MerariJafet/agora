"""Authenticated TEST-only challenge creation without direct fixture writes or issuance.

Run only with scripts/run-isolated-tests.sh. Non-TEST guard cases monkeypatch
only the endpoint service's settings reader; database isolation stays TEST.
"""

from types import SimpleNamespace

import pytest
from agora_api.db import session_factory
from agora_api.models import (
    Event,
    EventOutbox,
    Mission,
    RecordProvenance,
    Space,
    TokoinLedgerEntry,
    TokoinWallet,
)
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration
ENDPOINT = "/v1/research-protocol/test-challenges"


def payload(title):
    return {
        "title": title,
        "objective": "Test a bounded falsifiable claim.",
        "description": "Explicit synthetic TEST challenge; no scientific validation claim.",
        "experiment_id": "LLM-SCI-001",
        "parameters": {"seed": 83, "sample_size": 17, "mode": "deterministic-test"},
    }


async def counts():
    async with session_factory()() as session:
        result = {
            model.__tablename__: await session.scalar(select(func.count()).select_from(model))
            for model in (Mission, Space, Event, TokoinLedgerEntry)
        }
        result["wallet_balances"] = [
            tuple(row)
            for row in (
                await session.execute(
                    select(TokoinWallet.wallet_id, TokoinWallet.balance).order_by(
                        TokoinWallet.wallet_id
                    )
                )
            ).all()
        ]
        return result


async def test_authenticated_creation_has_event_provenance_and_no_sql_issuance(
    api_client, unique_name
):
    creator = await register_agent(api_client, SigningKeypair(), unique_name)
    before = await counts()
    body = payload(unique_name)
    trace_id = "73" * 16
    response = await api_client.post(
        ENDPOINT,
        json=body,
        headers={
            "Authorization": f"Bearer {creator['session_token']}",
            "traceparent": f"00-{trace_id}-" + "19" * 8 + "-01",
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["mode"] == "TEST_NON_RECOGNIZABLE"
    assert result["reward_aceros"] == 0
    assert result["challenge_id"] == result["mission_id"]
    assert result["resolution_policy"] == "institutional_research_v1"
    after = await counts()
    assert after["missions"] == before["missions"] + 1
    assert after["spaces"] == before["spaces"] + 1
    assert after["events"] == before["events"] + 1
    assert after["tokoin_ledger_entries"] == before["tokoin_ledger_entries"]
    assert after["wallet_balances"] == before["wallet_balances"]
    async with session_factory()() as session:
        mission = await session.get(Mission, result["mission_id"])
        event = await session.get(Event, result["event_id"])
        assert mission.created_by_agent_id == creator["agent_id"]
        assert mission.created_by_agent_version_id == creator["agent_version_id"]
        assert mission.reward_aceros == 0
        assert mission.title == body["title"]
        assert mission.objective == body["objective"]
        assert mission.description == body["description"]
        assert mission.challenge_problem["parameters"] == body["parameters"]
        assert mission.challenge_problem["experiment_id"] == body["experiment_id"]
        assert mission.challenge_problem["mode"] == "TEST_NON_RECOGNIZABLE"
        assert event.event_type == "mission.created"
        assert event.actor == {
            "agent_id": creator["agent_id"],
            "agent_version_id": creator["agent_version_id"],
        }
        assert event.correlation_id == mission.mission_id
        assert event.trace_id == trace_id
        assert event.payload["parameters"] == body["parameters"]
        assert event.payload["reward_aceros"] == 0
        assert event.payload["mode"] == "TEST_NON_RECOGNIZABLE"
        for table, record_id in (
            ("missions", mission.mission_id),
            ("spaces", mission.hosting_space_id),
            ("events", event.event_id),
        ):
            provenance = await session.get(RecordProvenance, (table, record_id))
            assert provenance is not None and provenance.provenance_class == "test"
            assert provenance.environment_id == "isolated-local"
            assert provenance.run_id
            if table != "events":
                assert provenance.created_by_actor_or_process == creator["agent_id"]
                assert provenance.source_reference == body["experiment_id"]
        outbox = await session.scalar(
            select(EventOutbox).where(EventOutbox.event_id == event.event_id)
        )
        assert outbox is not None and outbox.subject == "agora.events.mission.created"
        entries = await session.scalar(
            select(func.count())
            .select_from(TokoinLedgerEntry)
            .where(TokoinLedgerEntry.mission_id == mission.mission_id)
        )
        assert entries == 0


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-session"}])
async def test_authentication_required_without_side_effects(api_client, unique_name, headers):
    before = await counts()
    response = await api_client.post(ENDPOINT, json=payload(unique_name), headers=headers)
    assert response.status_code == 401, response.text
    assert await counts() == before


@pytest.mark.parametrize("environment", ["development", "staging", "production"])
async def test_disabled_outside_test_without_changing_database_environment(
    api_client, unique_name, monkeypatch, environment
):
    import agora_api.v03_test_challenges as service

    creator = await register_agent(api_client, SigningKeypair(), unique_name)
    before = await counts()
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(env=environment))
    response = await api_client.post(
        ENDPOINT,
        json=payload(unique_name),
        headers={"Authorization": f"Bearer {creator['session_token']}"},
    )
    assert response.status_code == 404, response.text
    assert await counts() == before


@pytest.mark.parametrize(
    "override",
    [
        {"reward_aceros": 100000000},
        {"created_by_agent_id": "forged-agent"},
        {"experiment_id": "NOT-A-CAMPAIGN"},
        {"parameters": "invalid"},
    ],
)
async def test_cannot_inject_reward_actor_or_malformed_campaign(api_client, unique_name, override):
    creator = await register_agent(api_client, SigningKeypair(), unique_name)
    before = await counts()
    response = await api_client.post(
        ENDPOINT,
        json={**payload(unique_name), **override},
        headers={"Authorization": f"Bearer {creator['session_token']}"},
    )
    assert response.status_code == 422, response.text
    assert await counts() == before


async def test_event_failure_rolls_back_challenge_and_provenance(
    api_client, unique_name, monkeypatch
):
    import agora_api.v03_test_challenges as service
    from agora_api.errors import ValidationFailed

    creator = await register_agent(api_client, SigningKeypair(), unique_name)
    before = await counts()
    async with session_factory()() as session:
        provenance_before = await session.scalar(select(func.count()).select_from(RecordProvenance))

    async def reject_event(*args, **kwargs):
        raise ValidationFailed("Injected TEST event failure.")

    monkeypatch.setattr(service, "append_event", reject_event)
    response = await api_client.post(
        ENDPOINT,
        json=payload(unique_name),
        headers={"Authorization": f"Bearer {creator['session_token']}"},
    )
    assert response.status_code == 422, response.text
    assert await counts() == before
    async with session_factory()() as session:
        provenance_after = await session.scalar(select(func.count()).select_from(RecordProvenance))
    assert provenance_after == provenance_before
