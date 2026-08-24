"""Sprint 09 Civic Intelligence integration tests."""

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, unique_name: str, suffix: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), f"{unique_name}-{suffix}")


async def _events(api_client, agent_id: str) -> list[dict]:
    rows = (await api_client.get(f"/v1/agents/{agent_id}/events")).json()["events"]
    return sorted(rows, key=lambda row: row["event_id"])


async def test_civic_roles_summaries_disagreement_and_replay(api_client, unique_name):
    a = await _register(api_client, unique_name, "summarizer-a")
    b = await _register(api_client, unique_name, "summarizer-b")

    role = await api_client.post(
        "/v1/civic/roles",
        json={
            "role": "summarizer",
            "name": "Public Debate Summarizer",
            "description": "Produces auditable public summaries with uncertainty.",
        },
        headers=_auth(a),
    )
    assert role.status_code == 201, role.text

    subscribed = await api_client.post(
        "/v1/civic/subscriptions",
        json={"role_id": role.json()["role_id"], "scope": PLAZA, "filters": {"kind": "claim"}},
        headers=_auth(a),
    )
    assert subscribed.status_code == 201

    # Create a real ledger event range through existing Claim publication.
    claim = await api_client.post(
        "/v1/claims",
        json={
            "space_id": PLAZA,
            "claim_type": "observation",
            "text": "Civic summaries should expose uncertainty.",
        },
        headers=_auth(a),
    )
    assert claim.status_code == 201, claim.text
    events = await _events(api_client, a["agent_id"])
    assert events
    start = events[0]["event_id"]
    end = events[-1]["event_id"]

    first = await api_client.post(
        "/v1/civic/summaries",
        json={
            "coverage_event_ids": [event["event_id"] for event in events],
            "snapshot_start_event_id": start,
            "snapshot_end_event_id": end,
            "content": "The range shows one agent publishing a civic summary claim.",
            "explicit_uncertainty": "Limited to events visible in the selected range.",
            "source_pointers": [claim.json()["claim_id"]],
        },
        headers=_auth(a),
    )
    assert first.status_code == 201, first.text
    assert first.json()["finding"] is None

    second = await api_client.post(
        "/v1/civic/summaries",
        json={
            "coverage_event_ids": [event["event_id"] for event in events],
            "snapshot_start_event_id": start,
            "snapshot_end_event_id": end,
            "content": "A totally different interpretation about governance failure and risk.",
            "explicit_uncertainty": "Independent summarizer disagrees materially.",
        },
        headers=_auth(b),
    )
    assert second.status_code == 201, second.text
    assert second.json()["finding"]["finding_type"] == "SUMMARY_DISAGREEMENT"

    replay = await api_client.post(
        "/v1/replay",
        json={"start_event_id": start, "end_event_id": end, "speed": 4},
        headers=_auth(a),
    )
    assert replay.status_code == 201, replay.text
    body = replay.json()
    assert body["read_only"] is True
    assert body["snapshot"]["external_effects_replayed"] is False
    assert body["snapshot"]["event_count"] >= 1


async def test_source_audit_contradiction_reputation_and_governance_guards(api_client, unique_name):
    genesis = await _register(api_client, unique_name, "genesis")
    ada = await _register(api_client, unique_name, "ada")

    genesis_claim = (
        await api_client.post(
            "/v1/claims",
            json={
                "space_id": PLAZA,
                "claim_type": "policy_proposal",
                "text": "Consensus must not be treated as truth.",
            },
            headers=_auth(genesis),
        )
    ).json()
    evidence = (
        await api_client.post(
            "/v1/evidence",
            json={
                "source_type": "url",
                "locator": "https://example.org/civic-note",
                "role": "supports",
                "provenance_level": "reference_only",
                "title": "Civic note",
            },
            headers=_auth(genesis),
        )
    ).json()
    attached = await api_client.post(
        f"/v1/claims/{genesis_claim['claim_id']}/evidence",
        json={"evidence_id": evidence["evidence_id"], "role": "supports"},
        headers=_auth(genesis),
    )
    assert attached.status_code == 201, attached.text

    audit = await api_client.post(
        "/v1/civic/source-audits",
        json={"claim_id": genesis_claim["claim_id"]},
        headers=_auth(ada),
    )
    assert audit.status_code == 201, audit.text
    assert audit.json()["findings"][0]["finding_type"] == "SOURCE_AUDIT"

    ada_claim = (
        await api_client.post(
            "/v1/claims",
            json={
                "space_id": PLAZA,
                "claim_type": "policy_proposal",
                "text": "Consensus can be weak evidence in governance.",
            },
            headers=_auth(ada),
        )
    ).json()
    relation = await api_client.post(
        "/v1/claim-relations",
        json={
            "source_claim_id": ada_claim["claim_id"],
            "target_claim_id": genesis_claim["claim_id"],
            "relation_type": "contradicts",
        },
        headers=_auth(ada),
    )
    assert relation.status_code == 201, relation.text
    contradictions = await api_client.post(
        "/v1/civic/contradictions",
        json={"claim_id": genesis_claim["claim_id"]},
        headers=_auth(ada),
    )
    assert contradictions.status_code == 201
    assert contradictions.json()["findings"][0]["finding_type"] == "CONTRADICTION"

    forbidden = await api_client.post(
        "/v1/forge/rfcs",
        json={
            "title": "Delete constitution",
            "problem": "Security roots are inconvenient.",
            "proposal": "Delete constitution and disable security.",
        },
        headers=_auth(genesis),
    )
    assert forbidden.status_code == 422

    reputation = await api_client.post(
        "/v1/reputation/events",
        json={
            "agent_id": ada["agent_id"],
            "dimension": "Critical Analysis",
            "delta": 0.4,
            "context": "Found a real contradiction relation.",
            "sample_size": 1,
        },
        headers=_auth(genesis),
    )
    assert reputation.status_code == 201
    summary = (await api_client.get(f"/v1/reputation/agents/{ada['agent_id']}")).json()
    assert summary["truth_score"] is None
    assert summary["single_universal_karma"] is None
    assert "Critical Analysis" in summary["dimensions"]


async def test_agent_version_evolution_lineage_activation_and_skill_passport(
    api_client, unique_name
):
    agent = await _register(api_client, unique_name, "evolver")
    original_version = agent["agent_version_id"]

    proposal = await api_client.post(
        "/v1/agents/me/improvement-proposals",
        json={
            "observation": "I missed weak-source warnings.",
            "hypothesis": "A source-audit checklist will improve reliability.",
            "proposed_change": "Add a local checklist before publishing civic findings.",
            "benchmark": {"before": 0.5, "after_target": 0.7},
            "expected_result": "Better source audit consistency.",
            "risk": "May over-warn on weak but useful evidence.",
            "rollback": "Reactivate parent AgentVersion.",
            "owner_policy": "manual",
        },
        headers=_auth(agent),
    )
    assert proposal.status_code == 201, proposal.text

    published = await api_client.post(
        "/v1/agents/me/versions",
        json={
            "proposal_id": proposal.json()["proposal_id"],
            "public_changelog": "Adds source-audit checklist.",
            "skills": ["source-audit"],
            "capabilities": ["civic.findings.write"],
            "benchmarks": {"source_audit_consistency": {"before": 0.5, "after": 0.72}},
        },
        headers=_auth(agent),
    )
    assert published.status_code == 201, published.text
    version = published.json()["version"]
    assert version["parent_agent_version_id"] == original_version

    activated = await api_client.post(
        f"/v1/agents/me/versions/{version['agent_version_id']}/activate",
        json={"reason": "manual owner policy"},
        headers=_auth(agent),
    )
    assert activated.status_code == 200
    assert activated.json()["from_agent_version_id"] == original_version

    rollback = await api_client.post(
        f"/v1/agents/me/versions/{original_version}/activate",
        json={"reason": "rollback test"},
        headers=_auth(agent),
    )
    assert rollback.status_code == 200
    assert rollback.json()["to_agent_version_id"] == original_version

    passport = await api_client.post(
        f"/v1/agents/{agent['agent_id']}/skill-passport",
        json={
            "skill": "source-audit",
            "evidence_refs": ["mission:deterministic-test"],
            "source_kind": "mission",
        },
        headers=_auth(agent),
    )
    assert passport.status_code == 201, passport.text
    listed = (await api_client.get(f"/v1/agents/{agent['agent_id']}/skill-passport")).json()
    assert listed["skills"][0]["skill"] == "source-audit"
