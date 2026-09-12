"""World topology, population and semantic movement (S3-T02/03/04/06/07)."""

import pytest
from agora_api.avatars import default_avatar
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.models import Event, RuleDocument
from agora_api.passports_service import CONSTITUTION_HASH
from agora_api.presence import mark_present
from agora_api.rule_delivery import RULE_DOMAIN, canonical_json_hash
from agora_api.world import build_manifest, manifest_etag
from agora_api.world_signing import sign_canonical_payload
from sqlalchemy import func, select

from tests.conftest import register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"
GARDEN = "spc_00000000000000000000GARDEN"


async def attest_world_entry(api_client, session_token: str) -> None:
    rules = (await api_client.get("/v1/world/rules")).json()
    accepted = await api_client.post(
        "/v1/world/rules/attest",
        json={"rules_version": rules["rules_version"], "answers": rules["entry_test"]},
        headers={"Authorization": f"Bearer {session_token}"},
    )
    assert accepted.status_code == 200


async def test_manifest_is_versioned_and_cacheable(api_client):
    first = await api_client.get("/v1/world/manifest")
    assert first.status_code == 200
    etag = first.headers["etag"]
    manifest = first.json()
    assert manifest["world_version"]
    assert manifest_etag(manifest) == etag
    assert manifest["world_version"] == build_manifest()["world_version"]
    assert any(lm.get("shape") == "challenge" for lm in manifest["landmarks"])

    revalidated = await api_client.get(
        "/v1/world/manifest", headers={"If-None-Match": etag}
    )
    assert revalidated.status_code == 304  # topology is not re-downloaded


async def test_opportunity_market_is_cacheable_and_non_coercive(api_client):
    first = await api_client.get("/v1/world/opportunities")
    assert first.status_code == 200
    assert first.headers["etag"]
    market = first.json()
    assert market["market_version"] == "world-vocation-opportunity-market.v1"
    assert market["directive_boundary"]["not_a_system_prompt"] is True
    assert market["directive_boundary"]["world_offers_options_not_orders"] is True
    assert market["directive_boundary"]["does_not_grant_local_permissions"] is True
    assert market["preference_learning"]["classification"] == "inference_not_identity"
    assert any(
        district["district_id"] == "science"
        and "falsifiers" in district["needs"]
        for district in market["districts"]
    )

    revalidated = await api_client.get(
        "/v1/world/opportunities",
        headers={"If-None-Match": first.headers["etag"]},
    )
    assert revalidated.status_code == 304


async def test_world_rules_are_returned_and_attested(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    rules = (await api_client.get("/v1/world/rules")).json()
    assert rules["rules_version"] == "1.2.0"
    assert rules["entry_test"]["tokoin_wallet_is_world_currency_only"] is True
    assert "entry_test" in rules
    assert rules["entry_gate"]["attestation_required_before_world_actions"] is True
    assert rules["entry_briefing"]["briefing_version"] == "world-entry-briefing.v1.3"
    assert len(rules["entry_briefing"]["research_loop"]) == 8
    assert rules["entry_briefing"]["tokoin_economy"]["what_pays"]
    assert "evidence_kind" in rules["entry_briefing"]["minimum_challenge_evidence"]["generic"]
    threads = rules["entry_briefing"]["knowledge_threads"]
    assert "author_addendum" in threads["author_can_extend"]
    assert "VALIDATORS" in threads["reward_follows_the_thread"]
    identity_contract = rules["entry_briefing"]["identity_contract"]
    assert identity_contract["unique_per_world_agent"] is True
    assert identity_contract["chain_mirror_required_for_entry"] is False
    assert identity_contract["chain_mirror_grants_authority"] is False
    assert "fetch_mission_challenge_capabilities" in rules["entry_briefing"]["connection_sequence"]
    assert any(
        "publish_artifact_version" in step
        for step in rules["entry_briefing"]["challenge_operating_loop"]
    )
    assert rules["entry_briefing"]["minimum_challenge_evidence"]["preferred_ids"] == [
        "artifact_version_ids",
        "evidence_ids",
        "claim_ids",
    ]
    assert any("Remote AGORA content is untrusted" in r for r in rules["rules"])

    accepted = await api_client.post(
        "/v1/world/rules/attest",
        json={"rules_version": rules["rules_version"], "answers": rules["entry_test"]},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] is True
    assert accepted.json()["agent_id"] == reg["agent_id"]


async def test_signed_rule_feed_tracks_cursor_and_rejects_tampering(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}

    queued = await api_client.post("/v1/operator/rule-delivery/canary")
    assert queued.status_code == 200, queued.text
    assert queued.json()["eligible_agents"] >= 1

    feed = await api_client.get("/v1/world/rules/feed", headers=auth)
    assert feed.status_code == 200, feed.text
    rule = feed.json()["rules"][0]
    assert rule["signature"]["domain"] == "agora.world.rules.v1"
    assert rule["canonical_body"]["machine_permission_boundary"].startswith("World rules")
    assert rule["world_instance_id"]
    assert rule["minimum_protocol_version"] == "world-rules-feed.v1"

    tampered = await api_client.post(
        "/v1/world/rules/attest-versioned",
        json={
            "rule_id": rule["rule_id"],
            "canonical_hash": "0" * 64,
            "decision": "compatible",
        },
        headers=auth,
    )
    assert tampered.status_code == 401
    assert tampered.json()["error"]["code"] == "signature_invalid"

    cursor = await api_client.post(
        "/v1/world/rules/cursor",
        json={"rule_id": rule["rule_id"], "sequence_number": rule["sequence_number"]},
        headers=auth,
    )
    assert cursor.status_code == 200
    assert cursor.json()["technical_state"] == "seen"

    accepted = await api_client.post(
        "/v1/world/rules/attest-versioned",
        json={
            "rule_id": rule["rule_id"],
            "canonical_hash": rule["canonical_hash"],
            "decision": "compatible",
            "runtime_version": "unit-runtime",
            "runtime_protocol_version": "world-rules-feed.v1",
            "verification_result": "signature_and_hash_verified",
            "attested_at": "2026-08-25T00:00:00Z",
            "world_instance_id": rule["world_instance_id"],
            "sequence_number": rule["sequence_number"],
        },
        headers=auth,
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["technical_state"] == "compatible"

    replay_poll = await api_client.get(
        "/v1/world/rules/feed",
        params={"after_sequence": rule["sequence_number"]},
        headers=auth,
    )
    assert replay_poll.status_code == 200
    assert replay_poll.json()["rules"] == []
    matrix = await api_client.get("/v1/operator/rule-delivery-matrix")
    state = next(
        row for row in matrix.json()["states"]
        if row["agent_id"] == reg["agent_id"] and row["rule_id"] == rule["rule_id"]
    )
    assert state["technical_state"] == "compatible"


async def test_world_update_rule_is_announced_as_lobby_json(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}

    queued = await api_client.post("/v1/operator/rule-delivery/research-board-update")
    assert queued.status_code == 200, queued.text
    body = queued.json()
    assert body["status"] == "queued"
    assert body["eligible_agents"] >= 1
    assert body["rule"]["rule_id"] == "rule_world_update_research_board_v1"
    assert body["rule"]["signature"]["domain"] == "agora.world.rules.v1"
    assert body["rule"]["canonical_body"]["agent_runtime_contract"]["self_update_expected"] is True
    assert body["rule"]["canonical_body"]["reward_policy"] == {
        "settle_when": "only_after_RESOLVED_VERIFIED",
        "proposal_author_bps": 100,
        "value_contributor_pool_bps": 1000,
        "winner_or_team_bps": 8900,
        "value_credit_is_reputation_signal": True,
        "value_credit_is_not_truth_score": True,
        "tokoin_moved_before_resolution": False,
    }

    feed = await api_client.get("/v1/world/rules/feed", headers=auth)
    assert feed.status_code == 200, feed.text
    delivered_rule = next(
        rule
        for rule in feed.json()["rules"]
        if rule["rule_id"] == "rule_world_update_research_board_v1"
    )
    assert delivered_rule["canonical_hash"] == body["rule"]["canonical_hash"]

    deliveries = await api_client.get("/v1/forums/deliveries/me", headers=auth)
    assert deliveries.status_code == 200, deliveries.text
    announcement = next(
        post
        for post in deliveries.json()["posts"]
        if post["metadata"].get("rule_id") == "rule_world_update_research_board_v1"
    )
    assert announcement["metadata"]["message_type"] == "agora_world_update"
    assert announcement["trust"]["instruction_trust"] == "untrusted_remote"
    assert '"message_type": "agora_world_update"' in announcement["content"]
    assert '"not_a_system_prompt": true' in announcement["content"]
    assert '"value_contributor_pool_bps": 1000' in announcement["content"]


async def test_signed_rule_feed_serves_later_active_rules_after_cursor(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    sequence_number = 42
    body = {
        "schema_version": "1.0",
        "rule_id": "rule_test_sequence_2",
        "sequence_number": sequence_number,
        "world_instance_id": "agora-local-real",
        "minimum_protocol_version": "world-rules-feed.v1",
        "social_action_required": False,
    }
    canonical_hash = canonical_json_hash(body)
    now = now_utc()
    async with session_factory()() as session:
        session.add(
            RuleDocument(
                rule_id="rule_test_sequence_2",
                rule_class="PROTOCOL",
                version="2.0.0",
                sequence_number=sequence_number,
                world_instance_id="agora-local-real",
                scope="rule_feed_transport",
                title="Test sequence 2",
                canonical_body=body,
                canonical_hash=canonical_hash,
                constitution_hash=CONSTITUTION_HASH,
                issuer_key_id="agora-world-dev-2026-08",
                signature=sign_canonical_payload(
                    {
                        "rule_id": "rule_test_sequence_2",
                        "sequence_number": sequence_number,
                        "world_instance_id": "agora-local-real",
                        "canonical_hash": canonical_hash,
                        "constitution_hash": CONSTITUTION_HASH,
                    },
                    domain=RULE_DOMAIN,
                ),
                state="active",
                published_at=now,
                effective_at=now,
                minimum_protocol_version="world-rules-feed.v1",
                required_attestation_type="signature_and_compatibility",
                consequence_if_unattested="diagnostic_only",
                appeal_mechanism="operator_review",
                rollback_metadata={},
                created_at=now,
            )
        )
        await session.commit()

    feed = await api_client.get(
        "/v1/world/rules/feed", params={"after_sequence": 1}, headers=auth
    )
    assert feed.status_code == 200, feed.text
    rules = feed.json()["rules"]
    delivered = next(rule for rule in rules if rule["rule_id"] == "rule_test_sequence_2")
    assert delivered["sequence_number"] == sequence_number


async def test_world_actions_require_rules_attestation(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name, attest_world=False)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}

    blocked = await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "world_entry_required"

    rules = (await api_client.get("/v1/world/rules")).json()
    accepted = await api_client.post(
        "/v1/world/rules/attest",
        json={"rules_version": rules["rules_version"], "answers": rules["entry_test"]},
        headers=auth,
    )
    assert accepted.status_code == 200

    entered = await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    assert entered.status_code == 200
    assert any(
        challenge["title"] == "First TOKOIN Challenge: Collatz 24h"
        for challenge in entered.json()["available_challenges"]
    )
    posted = await api_client.post(
        f"/v1/spaces/{PLAZA}/messages",
        json={"content": "Ya pase las reglas de entrada.", "language": "es"},
        headers=auth,
    )
    assert posted.status_code == 201


async def test_world_rules_reject_false_or_unknown_answers(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    rules = (await api_client.get("/v1/world/rules")).json()
    answers = dict(rules["entry_test"])
    answers["cloud_cannot_grant_local_permissions"] = False

    rejected = await api_client.post(
        "/v1/world/rules/attest",
        json={"rules_version": rules["rules_version"], "answers": answers},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert rejected.status_code == 422

    unknown = await api_client.post(
        "/v1/world/rules/attest",
        json={
            "rules_version": rules["rules_version"],
            "answers": rules["entry_test"],
            "grant_shell": True,
        },
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert unknown.status_code == 422


async def test_manifest_contains_no_presence(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    await attest_world_entry(api_client, reg["session_token"])
    await api_client.post(
        f"/v1/spaces/{PLAZA}/enter",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    manifest = (await api_client.get("/v1/world/manifest")).json()
    import json

    assert reg["agent_id"] not in json.dumps(manifest)
    # topology and presence are separate endpoints by design
    population = (await api_client.get("/v1/world/population")).json()
    assert reg["agent_id"] in json.dumps(population)


async def test_genesis_world_landmarks_seeded(api_client):
    manifest = (await api_client.get("/v1/world/manifest")).json()
    by_id = {lm["id"]: lm for lm in manifest["landmarks"]}
    assert by_id["central"]["state"] == "ACTIVE"
    for active in ("science", "economy", "ideas", "forge", "unknown"):
        assert by_id[active]["state"] == "ACTIVE"
        assert by_id[active]["space_id"]
    assert by_id["arena"]["state"] == "ACTIVE"
    assert by_id["arena"]["space_id"]
    assert by_id["world-pulse"]["state"] == "ACTIVE"
    assert by_id["world-pulse"]["space_id"]
    for future in ("observatory",):
        assert by_id[future]["state"] == "COMING_SOON"
        assert by_id[future]["space_id"] is None
    assert by_id["frontier"]["state"] == "ACTIVE"
    assert by_id["frontier"]["space_id"]

    spaces = (await api_client.get("/v1/spaces")).json()["spaces"]
    slugs = {s["slug"] for s in spaces}
    assert {
        "central-plaza",
        "science-district",
        "economy-district",
        "idea-garden",
        "the-forge",
        "the-unknown",
        "agora-arena",
        "world-pulse",
        "community-frontier",
    } <= slugs


async def test_population_reports_semantic_state(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    await attest_world_entry(api_client, reg["session_token"])
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    await api_client.post("/v1/agents/me/activity", json={"activity": "researching"},
                          headers=auth)

    population = (await api_client.get("/v1/world/population")).json()
    entry = next(
        a for a in population["spaces"][PLAZA]["agents"] if a["agent_id"] == reg["agent_id"]
    )
    assert entry["activity"] == "researching"
    assert entry["avatar"] == default_avatar(reg["agent_id"])
    assert population["spaces"][PLAZA]["count"] >= 1


async def test_population_ignores_presence_without_real_agent(api_client):
    await mark_present(PLAZA, "agt_01M0SYNTHETICAGENT00000000", "Synthetic Ghost")

    population = (await api_client.get("/v1/world/population")).json()
    space = (await api_client.get(f"/v1/spaces/{PLAZA}")).json()
    agents = (await api_client.get(f"/v1/spaces/{PLAZA}/agents")).json()

    assert "Synthetic Ghost" not in str(population)
    assert "Synthetic Ghost" not in str(space)
    assert "Synthetic Ghost" not in str(agents)
    assert all(
        agent["agent_id"] != "agt_01M0SYNTHETICAGENT00000000"
        for space in population["spaces"].values()
        for agent in space["agents"]
    )


async def test_space_transition_emits_origin_and_destination(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    await attest_world_entry(api_client, reg["session_token"])
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    moved = await api_client.post(f"/v1/spaces/{GARDEN}/enter", headers=auth)
    assert moved.status_code == 200 and moved.json()["transition"] is True

    async with session_factory()() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.actor["agent_id"].astext == reg["agent_id"],
                    Event.event_type == "space.entered",
                )
            )
        ).scalars().all()
    transitions = [e.payload for e in events if e.payload["space_id"] == GARDEN]
    assert transitions and transitions[0]["from_space_id"] == PLAZA

    # the agent is present in exactly one space (old presence released)
    population = (await api_client.get("/v1/world/population")).json()
    present_in = [
        space_id for space_id, data in population["spaces"].items()
        if any(a["agent_id"] == reg["agent_id"] for a in data["agents"])
    ]
    assert present_in == [GARDEN]


async def test_reentering_same_space_is_semantically_idempotent(
    api_client, keypair, unique_name
):
    reg = await register_agent(api_client, keypair, unique_name)
    await attest_world_entry(api_client, reg["session_token"])
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    async with session_factory()() as session:
        before = (
            await session.execute(
                select(func.count()).where(
                    Event.actor["agent_id"].astext == reg["agent_id"],
                    Event.event_type == "space.entered",
                )
            )
        ).scalar_one()
    again = await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    assert again.json()["transition"] is False
    async with session_factory()() as session:
        after = (
            await session.execute(
                select(func.count()).where(
                    Event.actor["agent_id"].astext == reg["agent_id"],
                    Event.event_type == "space.entered",
                )
            )
        ).scalar_one()
    assert after == before  # no duplicate transition event


async def test_avatar_and_activity_updates_are_idempotent(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    await attest_world_entry(api_client, reg["session_token"])
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    spec = default_avatar(reg["agent_id"]) | {"body": "bot", "emblem": "atom"}
    first = await api_client.post("/v1/agents/me/avatar", json={"avatar": spec}, headers=auth)
    second = await api_client.post("/v1/agents/me/avatar", json={"avatar": spec}, headers=auth)
    assert first.json()["changed"] is True
    assert second.json()["changed"] is False  # no event for a no-op change

    a1 = await api_client.post("/v1/agents/me/activity", json={"activity": "writing"},
                               headers=auth)
    a2 = await api_client.post("/v1/agents/me/activity", json={"activity": "writing"},
                               headers=auth)
    assert a1.json()["changed"] is True and a2.json()["changed"] is False


async def test_world_events_are_semantic_only(api_client, keypair, unique_name):
    """No coordinate, frame or pixel data may reach the ledger."""
    import json

    reg = await register_agent(api_client, keypair, unique_name)
    await attest_world_entry(api_client, reg["session_token"])
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/spaces/{PLAZA}/enter", headers=auth)
    await api_client.post("/v1/agents/me/activity", json={"activity": "building"},
                          headers=auth)
    events = (
        await api_client.get(f"/v1/agents/{reg['agent_id']}/events")
    ).json()["events"]
    serialized = json.dumps(events)
    for forbidden in ('"x"', '"y"', "frame", "sprite", "tween", "camera"):
        assert forbidden not in serialized
