import pytest
from agora_api.config import get_settings
from agora_api.events import now_utc
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID
from agora_api.models import (
    Event,
    MissionParticipant,
    RecordProvenance,
    RecordProvenanceAudit,
    RecordQuarantine,
)
from agora_api.provenance import add_provenance, record_key
from agora_api.scoped_invariants import canonical_hash, capture_snapshot_manifest
from agora_api.unknown_signal_readiness import (
    UNKNOWN_SIGNAL_ENVIRONMENT_ID,
    UNKNOWN_SIGNAL_RUN_ID,
    apply_unknown_signal_adjudication_manifest,
    build_unknown_signal_adjudication_manifest,
)
from agora_api.world_actionability import (
    UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
    UNKNOWN_SIGNAL_DATASET_ID,
    UNKNOWN_SIGNAL_EXPERIMENT_ID,
    UNKNOWN_SIGNAL_MISSION_ID,
    generate_unknown_signal_rows,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.conftest import SigningKeypair, register_agent


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


@pytest.mark.asyncio
async def test_unknown_signal_provenance_adjudication_exact_idempotent_and_auditable(
    api_client, unique_name
):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    registered = await api_client.post("/v1/operator/unknown-signal/round-1/register")
    assert registered.status_code == 201

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        for table, record_id in [
            ("world_experiments", UNKNOWN_SIGNAL_EXPERIMENT_ID),
            ("unknown_signal_datasets", UNKNOWN_SIGNAL_DATASET_ID),
            ("missions", UNKNOWN_SIGNAL_MISSION_ID),
            ("spaces", UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID),
        ]:
            row = await session.get(RecordProvenance, (table, record_id))
            assert row is not None
            row.provenance_class = "test"
            row.environment_id = "local-dev"
            row.run_id = "test-p2-readiness"
        await session.commit()
    async with Session() as session:
        before_agent_provenance = (
            await session.execute(select(func.count()).select_from(RecordProvenance))
        ).scalar_one()
        manifest = await build_unknown_signal_adjudication_manifest(session)
        selected = {(row["record_table"], row["record_id"]) for row in manifest["records"]}
        assert selected == {
            ("world_experiments", UNKNOWN_SIGNAL_EXPERIMENT_ID),
            ("unknown_signal_datasets", UNKNOWN_SIGNAL_DATASET_ID),
            ("missions", UNKNOWN_SIGNAL_MISSION_ID),
            ("spaces", UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID),
        }
        assert not any(row["record_table"] in {"agents", "devices"} for row in manifest["records"])
        first = await apply_unknown_signal_adjudication_manifest(session, manifest)
        second_manifest = await build_unknown_signal_adjudication_manifest(session)
        second = await apply_unknown_signal_adjudication_manifest(session, second_manifest)
        await session.commit()

    async with Session() as session:
        rows = (
            await session.execute(
                select(RecordProvenance).where(
                    RecordProvenance.record_table.in_(
                        ["world_experiments", "unknown_signal_datasets", "missions", "spaces"]
                    ),
                    RecordProvenance.record_id.in_(
                        [
                            UNKNOWN_SIGNAL_EXPERIMENT_ID,
                            UNKNOWN_SIGNAL_DATASET_ID,
                            UNKNOWN_SIGNAL_MISSION_ID,
                            UNKNOWN_SIGNAL_CHALLENGE_SPACE_ID,
                        ]
                    ),
                )
            )
        ).scalars().all()
        audit_count = (
            await session.execute(
                select(func.count(RecordProvenanceAudit.audit_id)).where(
                    RecordProvenanceAudit.evidence_reference == manifest["manifest_hash"]
                )
            )
        ).scalar_one()
        after_agent_provenance = (
            await session.execute(select(func.count()).select_from(RecordProvenance))
        ).scalar_one()
    await engine.dispose()

    assert first["changed"] == 4
    assert second["changed"] == 0
    assert audit_count >= 4
    assert after_agent_provenance >= before_agent_provenance
    assert all(row.provenance_class == "real" for row in rows)
    assert all(row.environment_id == UNKNOWN_SIGNAL_ENVIRONMENT_ID for row in rows)
    assert all(row.run_id == UNKNOWN_SIGNAL_RUN_ID for row in rows)
    assert reg["agent_id"]


@pytest.mark.asyncio
async def test_unknown_signal_rejects_test_actor_joining_real_challenge(
    api_client, unique_name
):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    await api_client.post("/v1/operator/unknown-signal/round-1/register")

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        manifest = await build_unknown_signal_adjudication_manifest(session)
        await apply_unknown_signal_adjudication_manifest(session, manifest)
        await session.commit()

    joined = await api_client.post(
        f"/v1/mission-challenges/{UNKNOWN_SIGNAL_MISSION_ID}/join",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert joined.status_code == 403
    assert joined.json()["error"]["code"] == "provenance_mismatch"

    async with Session() as session:
        event = (
            await session.execute(
                select(Event)
                .where(Event.event_type == "provenance.mismatch_rejected")
                .order_by(Event.occurred_at.desc())
                .limit(1)
            )
        ).scalar_one()
        event_provenance = await session.get(RecordProvenance, ("events", event.event_id))
        participant_provenance = await session.get(
            RecordProvenance,
            ("mission_participants", f"{UNKNOWN_SIGNAL_MISSION_ID}|{reg['agent_id']}"),
        )
    await engine.dispose()

    assert event_provenance is not None
    assert event_provenance.provenance_class == "real"
    assert event_provenance.environment_id == UNKNOWN_SIGNAL_ENVIRONMENT_ID
    assert event_provenance.run_id == UNKNOWN_SIGNAL_RUN_ID
    assert participant_provenance is None


@pytest.mark.asyncio
async def test_operator_quarantines_participant_actor_provenance_mismatches(
    api_client, unique_name
):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    await api_client.post("/v1/operator/unknown-signal/round-1/register")

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        manifest = await build_unknown_signal_adjudication_manifest(session)
        await apply_unknown_signal_adjudication_manifest(session, manifest)
        session.add(
            MissionParticipant(
                mission_id=UNKNOWN_SIGNAL_MISSION_ID,
                agent_id=reg["agent_id"],
                agent_version_id=reg["agent_version_id"],
                roles=["challenger"],
                joined_at=now_utc(),
            )
        )
        await add_provenance(
            session,
            record_table="mission_participants",
            record_id=record_key(UNKNOWN_SIGNAL_MISSION_ID, reg["agent_id"]),
            provenance_class="real",
            environment_id=UNKNOWN_SIGNAL_ENVIRONMENT_ID,
            run_id=UNKNOWN_SIGNAL_RUN_ID,
            world_instance_id="agora-local-real",
            created_by="test.intentional_mismatch",
            source_reference="world-data-hygiene-test",
            created_by_actor_id=reg["agent_id"],
            created_by_actor_provenance="test",
        )
        await session.commit()

    applied = await api_client.post("/v1/operator/data-hygiene/quarantine-mismatches")
    assert applied.status_code == 200, applied.text
    assert applied.json()["quarantined_new"] >= 1

    async with Session() as session:
        row = (
            await session.execute(
                select(RecordQuarantine).where(
                    RecordQuarantine.record_table == "mission_participants",
                    RecordQuarantine.record_id
                    == record_key(UNKNOWN_SIGNAL_MISSION_ID, reg["agent_id"]),
                    RecordQuarantine.reason == "PROVENANCE_ACTOR_RELATION_MISMATCH",
                )
            )
        ).scalar_one_or_none()
    await engine.dispose()
    assert row is not None


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


@pytest.mark.asyncio
async def test_unknown_signal_snapshot_hash_is_stable_and_ground_truth_safe(
    api_client, unique_name
):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    await api_client.post("/v1/operator/unknown-signal/round-1/register")
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        manifest = await build_unknown_signal_adjudication_manifest(session)
        await apply_unknown_signal_adjudication_manifest(session, manifest)
        before = await capture_snapshot_manifest(session)
        after_same = await capture_snapshot_manifest(session)
        await session.commit()

    assert before["configuration_hashes"]["unknown_signal"]
    assert before["configuration_hashes"] == after_same["configuration_hashes"]
    assert "tokoin" in before["critical_invariants"]
    assert "collatz" in before["critical_invariants"]
    assert "manifest" in before["critical_invariants"]
    serialized = str(before["critical_invariants"]["unknown_signal"])
    assert "sealed_ground_truth_hash" in serialized
    assert "patterns" not in serialized

    posted = await api_client.post(
        "/v1/spaces/spc_00000000000000000000P1AZA0/messages",
        json={"content": "ordinary message must not alter Unknown Signal config"},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert posted.status_code == 201

    async with Session() as session:
        after_message = await capture_snapshot_manifest(session)
    joined = await api_client.post(
        f"/v1/mission-challenges/{UNKNOWN_SIGNAL_MISSION_ID}/join",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert joined.status_code == 403
    assert joined.json()["error"]["code"] == "provenance_mismatch"
    async with Session() as session:
        after_formal_action = await capture_snapshot_manifest(session)
    await engine.dispose()
    assert after_message["configuration_hashes"] == before["configuration_hashes"]
    assert after_formal_action["configuration_hashes"] == before["configuration_hashes"]


def test_unknown_signal_configuration_hash_is_sensitive_to_immutable_fields():
    config = {
        "experiment_id": UNKNOWN_SIGNAL_EXPERIMENT_ID,
        "run_id": UNKNOWN_SIGNAL_RUN_ID,
        "mission_id": UNKNOWN_SIGNAL_MISSION_ID,
        "environment_id": UNKNOWN_SIGNAL_ENVIRONMENT_ID,
        "provenance_class": "real",
        "cohort_manifest_hash": "cohort",
        "cohort_agent_ids_versions_digest": "members",
        "dataset_manifest_hash": "dataset",
        "dataset_row_count": 20_000,
        "sealed_ground_truth_hash": "sealed",
        "public_instruction_hash": "instruction",
        "world_commit": "world",
        "world_version": "world",
        "constitution_hash": "constitution",
        "metrics_version": "metrics",
        "verifier_version": "verifier",
        "economic_reward": 0,
        "roles_assigned": 0,
        "complementary_shards": 0,
        "participant_access_policy": "equal read-only",
        "non_automation_flags": {"operator_messages_to_agents": 0},
        "formal_action_schema_versions": {"mission_challenges": "1.0"},
        "registered_stopping_rules": ["default_observation_duration_60_minutes"],
        "duration_minutes": 60,
    }
    baseline = canonical_hash(config)
    for field in config:
        mutated = dict(config)
        mutated[field] = f"mutated-{field}"
        assert canonical_hash(mutated) != baseline, field
