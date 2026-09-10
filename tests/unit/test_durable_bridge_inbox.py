"""Crash/disconnect regression tests: no provider, network or live state."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from agora_bridge.config import BridgeConfig
from agora_bridge.inbox import A2AInbox
from agora_bridge.realtime import RealtimeConnection
from agora_bridge.runtime import TaskResult


def test_result_survives_restart_and_ack_replay(tmp_path):
    path = tmp_path / "inbox.sqlite3"
    inbox = A2AInbox(path=path)
    assert inbox.offer({"task_id": "t1"})
    assert inbox.take()["content"]["task_id"] == "t1"
    inbox.mark_running("t1")
    result = inbox.save_result("t1", [{"text": "saved"}])
    inbox.close()
    recovered = A2AInbox(path=path)
    assert not recovered.offer({"task_id": "t1"})
    assert recovered.take() is None
    assert recovered.pending_results() == [result]
    assert not recovered.acknowledge("t1", "failed")
    assert recovered.acknowledge("t1", "completed")
    assert not recovered.acknowledge("t1", "completed")
    recovered.close()
    reopened = A2AInbox(path=path)
    assert reopened.pending_results() == []
    assert not reopened.offer({"task_id": "t1"})
    reopened.close()


def test_crash_during_runtime_requires_reconciliation_not_reexecution(tmp_path):
    path = tmp_path / "inbox.sqlite3"
    original = A2AInbox(path=path)
    original.offer({"task_id": "ambiguous"})
    original.take()
    original.mark_running("ambiguous")
    original.close()  # simulates durable state left by terminated process
    recovered = A2AInbox(path=path)
    assert recovered.take() is None
    assert recovered.pending_results()[0]["status"] == "failed"
    assert "reconciliation" in recovered.pending_results()[0]["reason"]
    recovered.close()


def test_only_one_process_owner_and_bound_backpressure(tmp_path):
    path = tmp_path / "inbox.sqlite3"
    first = A2AInbox(limit=1, path=path)
    with pytest.raises(RuntimeError, match="another Bridge"):
        A2AInbox(path=path)
    assert first.offer({"task_id": "one"})
    first.take()
    first.mark_running("one")
    first.save_result("one", [])
    assert not first.offer({"task_id": "two"})
    assert first.acknowledge("one", "completed")
    assert first.offer({"task_id": "two"})
    first.close()


@pytest.mark.asyncio
async def test_lost_send_then_restart_resends_without_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    config = BridgeConfig(agent_id="agt_test", api_url="http://test")
    runtime = Mock()
    runtime.handle_task.return_value = TaskResult(True, [{"text": "result"}])
    first = RealtimeConnection(config, "test", runtime, Mock())

    async def claim_then_disconnect(raw):
        payload = json.loads(raw)
        if payload["type"] == "a2a_task_claim":
            await first._handle_frame(
                broken, json.dumps({**payload, "type": "a2a_task_claim_ack", "accepted": True})
            )
        else:
            raise OSError("disconnected")

    broken = SimpleNamespace(send=AsyncMock(side_effect=claim_then_disconnect))
    frame = json.dumps({"type": "a2a_task", "task_id": "t1"})
    with pytest.raises(OSError):
        await first._handle_frame(broken, frame)
    first.inbox.close()
    second = RealtimeConnection(config, "test", runtime, Mock())
    socket = SimpleNamespace(send=AsyncMock())
    await second._handle_frame(socket, frame)
    assert runtime.handle_task.call_count == 1
    result = json.loads(socket.send.call_args.args[0])
    assert result["status"] == "completed"
    assert second.inbox.pending_results() == [result]
    await second._handle_frame(
        socket, json.dumps({"type": "a2a_result_ack", "task_id": "t1", "status": "completed"})
    )
    assert second.inbox.pending_results() == []
    second.inbox.close()


@pytest.mark.asyncio
async def test_runtime_exception_does_not_publish_exception_text(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    runtime = Mock()
    runtime.handle_task.side_effect = RuntimeError("SECRET_MUST_NOT_BE_SENT")
    conn = RealtimeConnection(BridgeConfig(agent_id="agt_test"), "test", runtime, Mock())

    async def claim_ack(raw):
        payload = json.loads(raw)
        if payload["type"] == "a2a_task_claim":
            await conn._handle_frame(
                socket, json.dumps({**payload, "type": "a2a_task_claim_ack", "accepted": True})
            )

    socket = SimpleNamespace(send=AsyncMock(side_effect=claim_ack))
    await conn._handle_frame(socket, json.dumps({"type": "a2a_task", "task_id": "t"}))
    sent = socket.send.call_args.args[0]
    assert "SECRET_MUST_NOT_BE_SENT" not in sent
    assert json.loads(sent)["status"] == "failed"
    conn.inbox.close()


@pytest.mark.asyncio
async def test_other_executor_denied_before_any_runtime_call(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    runtime = Mock()
    conn = RealtimeConnection(BridgeConfig(agent_id="agt_test"), "test", runtime, Mock())

    async def deny_claim(raw):
        payload = json.loads(raw)
        assert payload["type"] == "a2a_task_claim"
        await conn._handle_frame(
            socket, json.dumps({**payload, "type": "a2a_task_claim_ack", "accepted": False})
        )

    socket = SimpleNamespace(send=AsyncMock(side_effect=deny_claim))
    frame = json.dumps({"type": "a2a_task", "task_id": "owned-elsewhere"})
    await conn._handle_frame(socket, frame)
    await conn._handle_frame(socket, frame)
    runtime.handle_task.assert_not_called()
    assert conn.inbox.pending_results() == []
    conn.inbox.close()


def test_disconnect_before_execution_keeps_same_claim_id(tmp_path):
    path = tmp_path / "inbox.sqlite3"
    inbox = A2AInbox(path=path)
    inbox.offer({"task_id": "claiming"})
    inbox.take()
    execution_id = inbox.execution_id("claiming")
    inbox.close()
    restarted = A2AInbox(path=path)
    assert restarted.pending_count() == 1
    assert restarted.pending_results() == []
    assert restarted.execution_id("claiming") == execution_id
    restarted.close()


@pytest.mark.asyncio
async def test_lost_claim_send_never_executes_and_remains_queued(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    runtime = Mock()
    conn = RealtimeConnection(BridgeConfig(agent_id="agt_test"), "test", runtime, Mock())
    socket = SimpleNamespace(send=AsyncMock(side_effect=OSError("claim disconnected")))
    with pytest.raises(OSError):
        await conn._handle_frame(socket, json.dumps({"type": "a2a_task", "task_id": "claiming"}))
    runtime.handle_task.assert_not_called()
    assert conn.inbox.pending_count() == 1
    assert conn.inbox.pending_results() == []
    conn.inbox.close()


@pytest.mark.asyncio
async def test_revoked_after_claim_ack_prevents_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    runtime = Mock()
    conn = RealtimeConnection(BridgeConfig(agent_id="agt_test"), "test", runtime, Mock())

    async def ack_then_revoke(raw):
        payload = json.loads(raw)
        await conn._handle_frame(
            socket, json.dumps({**payload, "type": "a2a_task_claim_ack", "accepted": True})
        )
        await conn._handle_frame(socket, json.dumps({"type": "revoked"}))

    socket = SimpleNamespace(send=AsyncMock(side_effect=ack_then_revoke))
    await conn._handle_frame(socket, json.dumps({"type": "a2a_task", "task_id": "revoked"}))
    runtime.handle_task.assert_not_called()
    assert conn.inbox.pending_count() == 1
    conn.inbox.close()


@pytest.mark.asyncio
async def test_disk_pause_after_claim_prevents_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    runtime = Mock()
    config = BridgeConfig(agent_id="agt_test")
    conn = RealtimeConnection(config, "test", runtime, Mock())

    async def ack_then_pause(raw):
        payload = json.loads(raw)
        (tmp_path / "config.json").write_text(
            json.dumps({"agent_id": config.agent_id, "api_url": config.api_url, "paused": True})
        )
        await conn._handle_frame(
            socket, json.dumps({**payload, "type": "a2a_task_claim_ack", "accepted": True})
        )

    socket = SimpleNamespace(send=AsyncMock(side_effect=ack_then_pause))
    await conn._handle_frame(socket, json.dumps({"type": "a2a_task", "task_id": "pause"}))
    runtime.handle_task.assert_not_called()
    assert conn.inbox.pending_count() == 1
    assert conn._stop.is_set()
    conn.inbox.close()
