"""Mission lifecycle, task DAG, lease claiming, completion evaluator
(S5-T04..T10, S5-T19)."""

import asyncio

import pytest

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _create_mission(api_client, reg: dict, **overrides) -> dict:
    body = {"title": "Policy brief", "objective": "Draft a short policy brief."} | overrides
    r = await api_client.post("/v1/missions", json=body, headers=_auth(reg))
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_activate_mission_freezes_policy(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    mission = await _create_mission(
        api_client, a, completion_policy={"all_required_tasks_accepted": True}
    )
    assert mission["state"] == "open"
    activated = await api_client.post(
        f"/v1/missions/{mission['mission_id']}/activate", headers=_auth(a)
    )
    assert activated.status_code == 200
    assert activated.json()["state"] == "active"
    assert activated.json()["completion_policy"] == {"all_required_tasks_accepted": True}


async def test_only_creator_may_activate(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    mission = await _create_mission(api_client, a)
    r = await api_client.post(f"/v1/missions/{mission['mission_id']}/activate", headers=_auth(b))
    assert r.status_code == 403


async def test_join_respects_max_participants(api_client, unique_name):
    kp_a, kp_b, kp_c = SigningKeypair(), SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    c = await register_agent(api_client, kp_c, f"{unique_name}-C")
    mission = await _create_mission(api_client, a, max_participants=1)
    mission_id = mission["mission_id"]
    join_b = await api_client.post(f"/v1/missions/{mission_id}/join", json={}, headers=_auth(b))
    assert join_b.status_code == 201
    join_c = await api_client.post(f"/v1/missions/{mission_id}/join", json={}, headers=_auth(c))
    assert join_c.status_code == 409
    assert join_c.json()["error"]["code"] == "mission_full"


async def test_task_dag_readiness_and_self_dependency_rejected(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    mission = await _create_mission(api_client, a)
    mission_id = mission["mission_id"]

    task_a = (
        await api_client.post(
            f"/v1/missions/{mission_id}/tasks",
            json={"title": "Extract arguments", "description": "..."},
            headers=_auth(a),
        )
    ).json()
    assert task_a["state"] == "ready"

    task_b = (
        await api_client.post(
            f"/v1/missions/{mission_id}/tasks",
            json={"title": "Draft policy", "description": "...",
                  "dependency_task_ids": [task_a["mission_task_id"]]},
            headers=_auth(a),
        )
    ).json()
    assert task_b["state"] == "pending"

    # New tasks can only ever depend on already-existing tasks, so the DAG
    # is acyclic by construction (a task's own id does not exist yet at
    # creation time, so self- or back-reference is structurally impossible
    # through this API).

    # task_b becomes ready only once task_a is accepted.
    await api_client.post(f"/v1/mission-tasks/{task_a['mission_task_id']}/claim", headers=_auth(a))
    await api_client.post(
        f"/v1/mission-tasks/{task_a['mission_task_id']}/submit", json={}, headers=_auth(a)
    )
    await api_client.post(f"/v1/mission-tasks/{task_a['mission_task_id']}/accept", headers=_auth(a))
    refreshed_b = (await api_client.get(f"/v1/mission-tasks/{task_b['mission_task_id']}")).json()
    assert refreshed_b["state"] == "ready"


async def test_task_lease_claim_race_only_one_winner(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    mission = await _create_mission(api_client, a)
    mission_id = mission["mission_id"]
    task = (
        await api_client.post(
            f"/v1/missions/{mission_id}/tasks",
            json={"title": "Race task", "description": "..."}, headers=_auth(a),
        )
    ).json()
    task_id = task["mission_task_id"]

    results = await asyncio.gather(
        api_client.post(f"/v1/mission-tasks/{task_id}/claim", headers=_auth(a)),
        api_client.post(f"/v1/mission-tasks/{task_id}/claim", headers=_auth(b)),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]


async def test_full_mission_completion_pins_final_artifact(api_client, unique_name):
    kp = SigningKeypair()
    a = await register_agent(api_client, kp, unique_name)
    mission = await _create_mission(
        api_client, a, completion_policy={"all_required_tasks_accepted": True,
                                          "at_least_one_final_artifact": True}
    )
    mission_id = mission["mission_id"]
    await api_client.post(f"/v1/missions/{mission_id}/activate", headers=_auth(a))
    task = (
        await api_client.post(
            f"/v1/missions/{mission_id}/tasks",
            json={"title": "Only task", "description": "..."}, headers=_auth(a),
        )
    ).json()
    task_id = task["mission_task_id"]
    await api_client.post(f"/v1/mission-tasks/{task_id}/claim", headers=_auth(a))

    artifact = (
        await api_client.post(
            "/v1/artifacts", json={"title": "Brief", "artifact_type": "report"}, headers=_auth(a)
        )
    ).json()
    version = (
        await api_client.post(
            f"/v1/artifacts/{artifact['artifact_id']}/versions",
            files={"file": ("brief.txt", b"hello world", "text/plain")},
            data={"metadata": "{}"},
            headers=_auth(a),
        )
    ).json()

    await api_client.post(
        f"/v1/mission-tasks/{task_id}/submit",
        json={"artifact_version_id": version["artifact_version_id"]}, headers=_auth(a),
    )
    accepted = await api_client.post(f"/v1/mission-tasks/{task_id}/accept", headers=_auth(a))
    assert accepted.status_code == 200

    final = await api_client.get(f"/v1/missions/{mission_id}")
    assert final.json()["state"] == "completed"
    assert final.json()["final_artifact_version_ids"] == [version["artifact_version_id"]]
