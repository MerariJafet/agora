"""A2A persistence contract: execute only through isolated test wrapper."""

import asyncio
import secrets

import pytest
from agora_api.a2a_service import A2AResultConflict, complete_task, pending_tasks_for
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.ids import new_task_id
from agora_api.models import A2ATask
from sqlalchemy import func, select

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


async def _actors(client, name):
    initiator = await register_agent(client, SigningKeypair(), f"{name}-I")
    target = await register_agent(client, SigningKeypair(), f"{name}-T")
    return initiator, target


async def _send(client, initiator, target, message):
    return await client.post(
        f"/v1/a2a/agents/{target['agent_id']}/jsonrpc",
        headers={"Authorization": f"Bearer {initiator['session_token']}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": message}},
    )


async def test_concurrent_retry_has_one_task_and_changed_payload_conflicts(api_client, unique_name):
    initiator, target = await _actors(api_client, unique_name)
    message = {
        "messageId": secrets.token_hex(16), "role": "ROLE_USER", "parts": [{"text": "hello"}],
    }
    responses = await asyncio.gather(*[
        _send(api_client, initiator, target, message) for _ in range(3)
    ])
    assert all(response.status_code == 200 for response in responses), [r.text for r in responses]
    ids = {r.json()["result"]["task"]["id"] for r in responses}
    assert len(ids) == 1
    changed = await _send(
        api_client, initiator, target, {**message, "parts": [{"text": "changed"}]}
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "a2a_request_conflict"
    async with session_factory()() as session:
        count = await session.scalar(select(func.count()).select_from(A2ATask).where(
            A2ATask.initiator_agent_id == initiator["agent_id"],
            A2ATask.target_agent_id == target["agent_id"],
        ))
        assert count == 1


async def test_request_identity_is_scoped_to_sender_and_target(api_client, unique_name):
    initiator, target = await _actors(api_client, unique_name)
    other = await register_agent(api_client, SigningKeypair(), f"{unique_name}-O")
    message = {"messageId": "same-id", "role": "ROLE_USER", "parts": [{"text": "hello"}]}
    responses = [await _send(api_client, a, b, message) for a, b in (
        (initiator, target), (other, target), (initiator, other),
    )]
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()["result"]["task"]["id"] for r in responses}) == 3


async def test_terminal_result_replay_is_exact_and_failure_is_observable(api_client, unique_name):
    initiator, target = await _actors(api_client, unique_name)
    response = await _send(api_client, initiator, target, {
        "messageId": secrets.token_hex(16), "role": "ROLE_USER", "parts": [{"text": "hello"}],
    })
    task_id = response.json()["result"]["task"]["id"]
    for first in (True, False):
        async with session_factory()() as session:
            assert await complete_task(
                session, task_id, [], completing_agent_id=target["agent_id"],
                result_status="rejected", reason="operator_declined",
            ) is first
    async with session_factory()() as session:
        with pytest.raises(A2AResultConflict):
            await complete_task(session, task_id, [], completing_agent_id=target["agent_id"])
    poll = await api_client.post(
        f"/v1/a2a/agents/{target['agent_id']}/jsonrpc",
        headers={"Authorization": f"Bearer {initiator['session_token']}"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tasks/get", "params": {"id": task_id}},
    )
    task = poll.json()["result"]["task"]
    assert task["status"]["state"] == "TASK_STATE_REJECTED"
    assert task["metadata"]["agora_result_reason"] == "operator_declined"


async def test_backlog_query_is_bounded_and_cursor_reaches_beyond_256(api_client, unique_name):
    initiator, target = await _actors(api_client, unique_name)
    async with session_factory()() as session:
        ids = []
        for _ in range(300):
            task_id = new_task_id()
            ids.append(task_id)
            session.add(A2ATask(
                task_id=task_id, context_id=task_id, initiator_agent_id=initiator["agent_id"],
                target_agent_id=target["agent_id"], status="submitted", message={},
                created_at=now_utc(), updated_at=now_utc(),
            ))
        await session.flush()
        cursor, seen = None, []
        while True:
            page = await pending_tasks_for(
                session, target["agent_id"], limit=64, after_task_id=cursor
            )
            if not page:
                break
            assert len(page) <= 64
            seen.extend(row.task_id for row in page)
            cursor = page[-1].task_id
        assert seen == sorted(ids)
        assert len(await pending_tasks_for(session, target["agent_id"], limit=10000)) == 256
        # Synthetic tasks are rolled back, not retained in the test database.


async def test_concurrent_executor_claim_is_sticky_and_results_are_bound(api_client, unique_name):
    from uuid import uuid4

    from agora_api.a2a_service import A2AExecutionConflict, claim_task
    from agora_api.errors import NotFound

    initiator, target = await _actors(api_client, unique_name)
    response = await _send(api_client, initiator, target, {
        "messageId": secrets.token_hex(16), "role": "ROLE_USER", "parts": [{"text": "claim"}],
    })
    task_id = response.json()["result"]["task"]["id"]
    executors = [str(uuid4()), str(uuid4())]

    async def attempt(execution_id):
        async with session_factory()() as session:
            return await claim_task(
                session, task_id, completing_agent_id=target["agent_id"], execution_id=execution_id,
            )

    async with session_factory()() as session:
        with pytest.raises(NotFound):
            await claim_task(
                session, task_id, completing_agent_id=initiator["agent_id"],
                execution_id=executors[0],
            )
    results = await asyncio.gather(*(attempt(executor) for executor in executors))
    assert results.count(True) == 1
    winner = executors[results.index(True)]
    loser = executors[results.index(False)]
    assert await attempt(winner) is True
    assert await attempt(loser) is False
    for unauthorized_execution in (None, loser):
        async with session_factory()() as session:
            with pytest.raises(A2AExecutionConflict):
                await complete_task(
                    session, task_id, [], completing_agent_id=target["agent_id"],
                    execution_id=unauthorized_execution, require_claim=True,
                )
    async with session_factory()() as session:
        assert await complete_task(
            session, task_id, [], completing_agent_id=target["agent_id"],
            execution_id=winner, require_claim=True,
        ) is True
    assert await attempt(winner) is True  # reconnect can resend an already committed result
    assert await attempt(loser) is False
    async with session_factory()() as session:
        assert await complete_task(
            session, task_id, [], completing_agent_id=target["agent_id"],
            execution_id=winner, require_claim=True,
        ) is False


async def test_wire_result_requires_claim_even_for_authenticated_target(api_client, unique_name):
    from agora_api.a2a_service import A2AExecutionConflict

    initiator, target = await _actors(api_client, unique_name)
    response = await _send(api_client, initiator, target, {
        "messageId": secrets.token_hex(16), "role": "ROLE_USER", "parts": [{"text": "claim"}],
    })
    task_id = response.json()["result"]["task"]["id"]
    async with session_factory()() as session:
        with pytest.raises(A2AExecutionConflict):
            await complete_task(
                session, task_id, [], completing_agent_id=target["agent_id"], require_claim=True,
            )
