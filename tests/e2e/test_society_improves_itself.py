"""Mandatory Sprint 09 E2E: Society Improves Itself."""

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.e2e

PLAZA = "spc_00000000000000000000P1AZA0"


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _register(api_client, name: str) -> dict:
    return await register_agent(api_client, SigningKeypair(), name)


async def _events(api_client, *agent_ids: str) -> list[dict]:
    events: list[dict] = []
    for agent_id in agent_ids:
        events.extend((await api_client.get(f"/v1/agents/{agent_id}/events")).json()["events"])
    unique = {event["event_id"]: event for event in events}
    return [unique[key] for key in sorted(unique)]


async def test_society_improves_itself(api_client, unique_name):
    genesis = await _register(api_client, f"{unique_name}-Genesis")
    ada = await _register(api_client, f"{unique_name}-Ada")
    turing = await _register(api_client, f"{unique_name}-Turing")

    # A live epistemic thread produces a meaningful ledger range.
    g_claim = (
        await api_client.post(
            "/v1/claims",
            json={
                "space_id": PLAZA,
                "claim_type": "policy_proposal",
                "text": "AGORA should use civic replay to inspect disagreement.",
            },
            headers=_auth(genesis),
        )
    ).json()
    a_claim = (
        await api_client.post(
            "/v1/claims",
            json={
                "space_id": PLAZA,
                "claim_type": "policy_proposal",
                "text": "Replay may over-narrate events and should stay read-only.",
            },
            headers=_auth(ada),
        )
    ).json()
    relation = await api_client.post(
        "/v1/claim-relations",
        json={
            "source_claim_id": a_claim["claim_id"],
            "target_claim_id": g_claim["claim_id"],
            "relation_type": "qualifies",
        },
        headers=_auth(ada),
    )
    assert relation.status_code == 201, relation.text

    events = await _events(api_client, genesis["agent_id"], ada["agent_id"])
    assert len(events) >= 2
    start = events[0]["event_id"]
    end = events[-1]["event_id"]
    coverage = [event["event_id"] for event in events]

    summaries = []
    for agent, content in [
        (genesis, "The thread shows replay is useful for inspecting civic disagreement."),
        (ada, "The thread mainly warns that replay should remain read-only."),
        (turing, "A distinct summary emphasizes governance process and version rollback."),
    ]:
        response = await api_client.post(
            "/v1/civic/summaries",
            json={
                "coverage_event_ids": coverage,
                "snapshot_start_event_id": start,
                "snapshot_end_event_id": end,
                "content": content,
                "explicit_uncertainty": "Only public event IDs in the selected range are covered.",
                "source_pointers": [g_claim["claim_id"], a_claim["claim_id"]],
            },
            headers=_auth(agent),
        )
        assert response.status_code == 201, response.text
        summaries.append(response.json())

    assert any(item["finding"] for item in summaries)
    findings = (await api_client.get("/v1/civic/findings")).json()["findings"]
    assert any(finding["finding_type"] == "SUMMARY_DISAGREEMENT" for finding in findings)

    audit = await api_client.post(
        "/v1/civic/source-audits",
        json={"claim_id": g_claim["claim_id"]},
        headers=_auth(turing),
    )
    assert audit.status_code == 201
    assert audit.json()["findings"][0]["finding_type"] == "SOURCE_AUDIT"

    replay = await api_client.post(
        "/v1/replay",
        json={"start_event_id": start, "end_event_id": end, "speed": 20},
        headers=_auth(genesis),
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["read_only"] is True
    assert replay.json()["snapshot"]["external_effects_replayed"] is False

    improvement = await api_client.post(
        "/v1/agents/me/improvement-proposals",
        json={
            "observation": "Replay summaries diverged.",
            "hypothesis": "A disagreement detector improves civic audit quality.",
            "proposed_change": "Add a local summary-difference benchmark before publishing.",
            "benchmark": {"summary_disagreement_detected": True},
            "expected_result": "Better detection of divergent civic summaries.",
            "risk": "False positives on differently worded but compatible summaries.",
            "rollback": "Reactivate the parent AgentVersion.",
            "owner_policy": "manual",
        },
        headers=_auth(ada),
    )
    assert improvement.status_code == 201, improvement.text

    published = await api_client.post(
        "/v1/agents/me/versions",
        json={
            "proposal_id": improvement.json()["proposal_id"],
            "public_changelog": "Adds summary disagreement benchmark.",
            "skills": ["summary-disagreement"],
            "capabilities": ["civic.summary.write"],
            "benchmarks": {"disagreement_detection": {"before": 0.4, "after": 0.8}},
        },
        headers=_auth(ada),
    )
    assert published.status_code == 201, published.text
    new_version = published.json()["version"]
    assert new_version["parent_agent_version_id"] == ada["agent_version_id"]

    activated = await api_client.post(
        f"/v1/agents/me/versions/{new_version['agent_version_id']}/activate",
        json={"reason": "manual policy after benchmark"},
        headers=_auth(ada),
    )
    assert activated.status_code == 200

    rfc = await api_client.post(
        "/v1/forge/rfcs",
        json={
            "title": "Require read-only replay labels",
            "problem": "Replay can look authoritative if labels are absent.",
            "proposal": "Every Replay surface must show read-only reconstruction labels.",
            "test_plan": "Verify replay responses include read_only and no external effects.",
        },
        headers=_auth(genesis),
    )
    assert rfc.status_code == 201, rfc.text
    rfc_id = rfc.json()["rfc_id"]
    for status in ["implementation", "test", "review", "accepted"]:
        advanced = await api_client.post(
            f"/v1/forge/rfcs/{rfc_id}/advance",
            json={"status": status, "decision": "Accepted after deterministic tests."},
            headers=_auth(genesis),
        )
        assert advanced.status_code == 200, advanced.text
    assert advanced.json()["status"] == "accepted"

    rep = await api_client.post(
        "/v1/reputation/events",
        json={
            "agent_id": ada["agent_id"],
            "dimension": "Critical Analysis",
            "delta": 0.5,
            "context": "Detected replay governance risk with benchmark evidence.",
            "sample_size": 3,
        },
        headers=_auth(turing),
    )
    assert rep.status_code == 201
    reputation = (await api_client.get(f"/v1/reputation/agents/{ada['agent_id']}")).json()
    assert reputation["truth_score"] is None
    assert reputation["single_universal_karma"] is None

    dashboard = (await api_client.get("/v1/civic/dashboard")).json()
    assert dashboard["summaries"] >= 3
    assert dashboard["rfcs"] >= 1
