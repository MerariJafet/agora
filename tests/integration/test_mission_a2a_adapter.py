"""Canonical A2A MissionTask adapter (S5.1-T02..T05): delegation creates a
correlated canonical A2A Task, MissionTask stays the workflow source of
truth, duplicate/late submissions from a superseded attempt are rejected,
and cancellation cannot leave contradictory final states."""

import pytest
from agora_api.db import session_factory
from agora_api.models import A2ATask

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _auth(reg: dict) -> dict:
    return {"Authorization": f"Bearer {reg['session_token']}"}


async def _mission_with_task(api_client, coordinator: dict) -> tuple[str, dict]:
    mission = (
        await api_client.post(
            "/v1/missions", json={"title": "M", "objective": "..."}, headers=_auth(coordinator)
        )
    ).json()
    task = (
        await api_client.post(
            f"/v1/missions/{mission['mission_id']}/tasks",
            json={"title": "T", "description": "..."}, headers=_auth(coordinator),
        )
    ).json()
    return mission["mission_id"], task


async def test_delegate_creates_correlated_a2a_task(api_client, unique_name):
    kp_c, kp_w = SigningKeypair(), SigningKeypair()
    coordinator = await register_agent(api_client, kp_c, f"{unique_name}-C")
    worker = await register_agent(api_client, kp_w, f"{unique_name}-W")
    mission_id, task = await _mission_with_task(api_client, coordinator)

    r = await api_client.post(
        f"/v1/mission-tasks/{task['mission_task_id']}/delegate",
        json={"target_agent_id": worker["agent_id"]}, headers=_auth(coordinator),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "assigned"
    assert body["assigned_agent_id"] == worker["agent_id"]
    a2a_task_id = body["a2a_task_id"]

    async with session_factory()() as session:
        a2a_task = await session.get(A2ATask, a2a_task_id)
        assert a2a_task is not None
        assert a2a_task.target_agent_id == worker["agent_id"]
        assert a2a_task.initiator_agent_id == coordinator["agent_id"]
        assert a2a_task.message["metadata"]["agora_mission_task_id"] == task["mission_task_id"]
        assert a2a_task.message["metadata"]["agora_mission_id"] == mission_id

    delegation = (
        await api_client.get(f"/v1/mission-tasks/{task['mission_task_id']}/delegation")
    ).json()
    assert delegation["a2a_task_id"] == a2a_task_id
    assert delegation["a2a_status"] == "submitted"


async def test_only_coordinator_may_delegate(api_client, unique_name):
    kp_c, kp_w, kp_other = SigningKeypair(), SigningKeypair(), SigningKeypair()
    coordinator = await register_agent(api_client, kp_c, f"{unique_name}-C")
    worker = await register_agent(api_client, kp_w, f"{unique_name}-W")
    other = await register_agent(api_client, kp_other, f"{unique_name}-O")
    _, task = await _mission_with_task(api_client, coordinator)

    r = await api_client.post(
        f"/v1/mission-tasks/{task['mission_task_id']}/delegate",
        json={"target_agent_id": worker["agent_id"]}, headers=_auth(other),
    )
    assert r.status_code == 403


async def test_a2a_task_completion_does_not_auto_accept_mission_task(api_client, unique_name):
    """The A2A exchange finishing must never silently move the MissionTask
    to accepted — that still requires the explicit Mission submit/accept
    calls (S5.1-T03)."""
    kp_c, kp_w = SigningKeypair(), SigningKeypair()
    coordinator = await register_agent(api_client, kp_c, f"{unique_name}-C")
    worker = await register_agent(api_client, kp_w, f"{unique_name}-W")
    _, task = await _mission_with_task(api_client, coordinator)
    delegated = (
        await api_client.post(
            f"/v1/mission-tasks/{task['mission_task_id']}/delegate",
            json={"target_agent_id": worker["agent_id"]}, headers=_auth(coordinator),
        )
    ).json()

    from agora_api.a2a_service import complete_task

    async with session_factory()() as session:
        changed = await complete_task(session, delegated["a2a_task_id"], artifacts=[])
        assert changed is True

    refreshed = (
        await api_client.get(f"/v1/mission-tasks/{task['mission_task_id']}")
    ).json()
    assert refreshed["state"] == "assigned"  # unchanged: A2A completion is not a Mission transition

    delegation = (
        await api_client.get(f"/v1/mission-tasks/{task['mission_task_id']}/delegation")
    ).json()
    assert delegation["a2a_status"] == "completed"
    assert delegation["hint"] == "delegate_finished_awaiting_explicit_submission"


async def test_stale_attempt_submission_rejected(api_client, unique_name):
    kp_c, kp_w = SigningKeypair(), SigningKeypair()
    coordinator = await register_agent(api_client, kp_c, f"{unique_name}-C")
    worker = await register_agent(api_client, kp_w, f"{unique_name}-W")
    mission_id, task = await _mission_with_task(api_client, coordinator)
    task_id = task["mission_task_id"]

    await api_client.post(
        f"/v1/mission-tasks/{task_id}/delegate",
        json={"target_agent_id": worker["agent_id"]}, headers=_auth(coordinator),
    )
    first_attempt = (await api_client.get(f"/v1/mission-tasks/{task_id}")).json()["attempt"]

    # Lease is force-expired and the coordinator redelegates -> attempt+1.
    async with session_factory()() as session:
        from agora_api.models import MissionTask

        row = await session.get(MissionTask, task_id)
        row.lease_expires_at = None
        row.state = "ready"
        await session.commit()
    await api_client.post(
        f"/v1/mission-tasks/{task_id}/delegate",
        json={"target_agent_id": worker["agent_id"]}, headers=_auth(coordinator),
    )
    second_attempt = (await api_client.get(f"/v1/mission-tasks/{task_id}")).json()["attempt"]
    assert second_attempt == first_attempt + 1

    # A late submission tagged with the OLD attempt number must be rejected,
    # never silently accepted as if it were the current attempt's result.
    stale = await api_client.post(
        f"/v1/mission-tasks/{task_id}/submit",
        json={"attempt": first_attempt}, headers=_auth(worker),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "stale_attempt"

    current = await api_client.post(
        f"/v1/mission-tasks/{task_id}/submit",
        json={"attempt": second_attempt}, headers=_auth(worker),
    )
    assert current.status_code == 200
    assert current.json()["state"] == "submitted"


async def test_cancel_mission_leaves_no_contradictory_final_state(api_client, unique_name):
    kp_c, kp_w = SigningKeypair(), SigningKeypair()
    coordinator = await register_agent(api_client, kp_c, f"{unique_name}-C")
    worker = await register_agent(api_client, kp_w, f"{unique_name}-W")
    mission_id, task = await _mission_with_task(api_client, coordinator)
    await api_client.post(
        f"/v1/mission-tasks/{task['mission_task_id']}/delegate",
        json={"target_agent_id": worker["agent_id"]}, headers=_auth(coordinator),
    )
    cancelled = await api_client.post(
        f"/v1/missions/{mission_id}/cancel", headers=_auth(coordinator)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"

    # The MissionTask itself is untouched by cancelling the Mission (no
    # cascading task-state mutation defined this sprint) but the Mission's
    # own state is a clean terminal value, never a mix of "cancelled" and
    # "completed".
    mission = (await api_client.get(f"/v1/missions/{mission_id}")).json()
    assert mission["state"] == "cancelled"
    assert mission["completed_at"] is None
