"""Pure websocket handler probes: no API server, database, or broker required."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from agora_api.errors import DeviceRevoked
from agora_api.routes import realtime
from fastapi import WebSocketDisconnect


class FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None


class ResultSocket:
    headers = {"authorization": "Bearer test-session"}

    def __init__(self):
        self.accepted = False
        self.received = False

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if self.received:
            raise WebSocketDisconnect()
        self.received = True
        return json.dumps({
            "type": "a2a_result", "task_id": "test-task", "artifacts": [],
            "agent_id": "spoofed-target",  # remote identity is never authority
        })


async def _blocked_pump(*args):
    await asyncio.Event().wait()


def _install(monkeypatch, *, revoked=False):
    device = SimpleNamespace(agent_id="authenticated-agent", device_id="test-device")
    resolve = AsyncMock(side_effect=[device, DeviceRevoked()] if revoked else [device, device])
    complete = AsyncMock(return_value=True)
    monkeypatch.setattr(realtime, "session_factory", lambda: FakeSession)
    monkeypatch.setattr(realtime, "resolve_device_session", resolve)
    monkeypatch.setattr(realtime, "pending_tasks_for", AsyncMock(return_value=[]))
    monkeypatch.setattr(realtime, "complete_task", complete)
    monkeypatch.setattr(realtime, "_pump", _blocked_pump)
    monkeypatch.setattr(realtime, "_refill_pending", _blocked_pump)
    monkeypatch.setattr(realtime, "gateway", SimpleNamespace(register=Mock(), unregister=Mock()))
    return resolve, complete


async def test_result_uses_fresh_authenticated_identity_not_frame_identity(monkeypatch):
    resolve, complete = _install(monkeypatch)
    await realtime.bridge_ws(ResultSocket())
    assert resolve.await_count == 2  # handshake plus result
    complete.assert_awaited_once()
    assert complete.await_args.kwargs == {
        "completing_agent_id": "authenticated-agent", "result_status": "completed", "reason": None,
        "execution_id": None, "require_claim": True,
    }
    assert complete.await_args.args[1:] == ("test-task", [])


async def test_result_from_device_revoked_after_handshake_never_completes(monkeypatch):
    resolve, complete = _install(monkeypatch, revoked=True)
    await realtime.bridge_ws(ResultSocket())
    assert resolve.await_count == 2
    complete.assert_not_awaited()


async def test_browser_cannot_subscribe_agent_scope_but_public_space_works(monkeypatch):
    gateway = SimpleNamespace(register=Mock(), unregister=Mock())
    execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: "spc_public"))
    session = FakeSession()
    session.execute = execute
    monkeypatch.setattr(realtime, "session_factory", lambda: lambda: session)
    monkeypatch.setattr(realtime, "resolve_web_session", AsyncMock())
    monkeypatch.setattr(realtime, "gateway", gateway)
    monkeypatch.setattr(realtime, "_pump", _blocked_pump)
    frames = iter([
        {"type": "subscribe", "space_id": "agt_private_target"},
        {"type": "subscribe", "space_id": "spc_public"},
    ])

    class BrowserSocket:
        cookies = {}

        async def accept(self):
            pass

        async def receive_text(self):
            try:
                return json.dumps(next(frames))
            except StopIteration:
                raise WebSocketDisconnect() from None

    await realtime.web_ws(BrowserSocket())
    client = gateway.register.call_args.args[0]
    assert client.spaces == {"spc_public"}
    assert client.queue.get_nowait() == {"type": "subscribe_rejected", "reason": "not_found"}
    assert client.queue.get_nowait() == {"type": "subscribed", "space_id": "spc_public"}
    execute.assert_awaited_once()  # agent scope rejected before querying spaces


async def test_unknown_public_space_is_not_subscribable():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    assert await realtime._public_space_exists(session, "spc_unknown") is False


async def test_gateway_never_sends_directed_a2a_to_browser_even_with_injected_scope():
    from agora_api.realtime import RealtimeGateway, RtClient

    gateway = RealtimeGateway()
    browser = RtClient(kind="browser", spaces={"agt_target", "spc_public"})
    bridge = RtClient(kind="bridge", agent_id="agt_target", a2a_ready=True)
    gateway.register(browser)
    gateway.register(bridge)
    private = {"scope": "agt_target", "kind": "a2a_task", "data": {"task_id": "private"}}
    await gateway._on_nats(SimpleNamespace(data=json.dumps(private).encode()))
    assert browser.queue.empty()
    assert bridge.queue.get_nowait() == {"type": "a2a_task", "task_id": "private"}
    # A directed frame misrouted to a space subject still must not leak.
    private["scope"] = "spc_public"
    await gateway._on_nats(SimpleNamespace(data=json.dumps(private).encode()))
    assert browser.queue.empty()
    public = {"scope": "spc_public", "kind": "message", "data": {"content": "public"}}
    await gateway._on_nats(SimpleNamespace(data=json.dumps(public).encode()))
    assert browser.queue.get_nowait() == {
        "type": "message", "space_id": "spc_public", "content": "public",
    }


async def test_public_mission_and_arena_interests_are_typed_and_a2a_stays_private():
    from agora_api.realtime import RealtimeGateway, RtClient

    gateway = RealtimeGateway()
    browser = RtClient(kind="browser", spaces={"mis_public", "arena", "agt_private"})
    gateway.register(browser)
    for scope, kind, allowed in (
        ("mis_public", "mission", True),
        ("mis_public", "artifact", True),
        ("mis_public", "mission_challenge", True),
        ("arena", "arena", True),
        ("arena", "mission", False),
        ("mis_public", "a2a_task", False),
        ("arena", "a2a_completed", False),
        ("agt_private", "a2a_task", False),
    ):
        frame = {"scope": scope, "kind": kind, "data": {"event": "fixture"}}
        await gateway._on_nats(SimpleNamespace(data=json.dumps(frame).encode()))
        if allowed:
            assert browser.queue.get_nowait()["type"] == kind
        else:
            assert browser.queue.empty()


async def test_typed_interest_lookup_denies_unknown_mission_and_unknown_namespace():
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    )
    assert await realtime._public_interest_exists(session, "mis_unknown") is False
    assert await realtime._public_interest_exists(session, "agt_private") is False
    assert await realtime._public_interest_exists(session, "arbitrary_topic") is False
    assert await realtime._public_interest_exists(session, "arena") is True
    session.execute.assert_awaited_once()


async def test_committed_result_replay_receives_ack(monkeypatch):
    _, complete = _install(monkeypatch)
    complete.return_value = False  # exact prior committed result replay
    await realtime.bridge_ws(ResultSocket())
    client = realtime.gateway.register.call_args.args[0]
    assert client.queue.get_nowait()["type"] == "welcome"
    assert client.queue.get_nowait() == {
        "type": "a2a_result_ack", "task_id": "test-task", "status": "completed",
    }


async def test_conflicting_result_receives_rejection_not_ack(monkeypatch):
    from agora_api.a2a_service import A2AResultConflict

    _, complete = _install(monkeypatch)
    complete.side_effect = A2AResultConflict()
    await realtime.bridge_ws(ResultSocket())
    client = realtime.gateway.register.call_args.args[0]
    client.queue.get_nowait()  # welcome
    assert client.queue.get_nowait() == {
        "type": "a2a_result_rejected", "task_id": "test-task", "code": "a2a_result_conflict",
    }
    assert client.queue.empty()


async def test_delivery_protocol_must_be_explicitly_negotiated(monkeypatch):
    _install(monkeypatch)
    versions = iter([1, "2", 2])

    class CapabilitySocket(ResultSocket):
        async def receive_text(self):
            try:
                version = next(versions)
            except StopIteration:
                raise WebSocketDisconnect() from None
            client = realtime.gateway.register.call_args.args[0]
            assert client.a2a_ready is False
            return json.dumps({"type": "bridge_capabilities", "a2a_delivery_protocol": version})

    await realtime.bridge_ws(CapabilitySocket())
    client = realtime.gateway.register.call_args.args[0]
    assert client.a2a_ready is True
    assert client.queue.get_nowait()["type"] == "welcome"
    for _ in range(2):
        assert client.queue.get_nowait() == {
            "type": "bridge_capabilities_rejected", "required_a2a_delivery_protocol": 2,
        }
    assert client.queue.get_nowait() == {
        "type": "bridge_capabilities_ack", "a2a_delivery_protocol": 2,
    }
