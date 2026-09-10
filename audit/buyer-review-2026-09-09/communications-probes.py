"""Pure/mocked findings reproduction. No DB, broker, network, credentials, or model calls."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from agora_api.a2a_service import build_agent_card, create_task
from agora_api.card_signing import CARD_SIGNING_ALG, canonical_payload, verify_card_signature
from agora_api.realtime import RtClient
from agora_bridge.config import BridgeConfig
from agora_bridge.realtime import RealtimeConnection
from agora_bridge.runtime import TaskResult
from joserfc import jws
from joserfc.jwk import OKPKey


async def main():
    runtime = Mock()
    runtime.handle_task.return_value = TaskResult(True, [])
    connection = RealtimeConnection(
        BridgeConfig(agent_name="TEST_NOT_REAL"), "test", runtime, Mock()
    )
    socket = SimpleNamespace(send=AsyncMock(side_effect=OSError("simulated result disconnect")))
    frame = json.dumps({"type": "a2a_task", "task_id": "tsk_fixture"})
    try:
        await connection._handle_frame(socket, frame)
    except OSError:
        pass
    await connection._handle_frame(socket, frame)
    assert runtime.handle_task.call_count == 1
    assert socket.send.await_count == 1
    assert connection.inbox.duplicates_dropped == 1
    print("CONFIRMED result-send failure: same-process redelivery discarded; no resend")
    restarted = RealtimeConnection(
        BridgeConfig(agent_name="TEST_NOT_REAL"), "test", runtime, Mock()
    )
    await restarted._handle_frame(SimpleNamespace(send=AsyncMock()), frame)
    assert runtime.handle_task.call_count == 2
    print("CONFIRMED process restart: same task executes again because inbox is volatile")

    queue = RtClient(kind="bridge", agent_id="agt_fixture")
    queue.offer({"type": "welcome"})
    for i in range(300):
        queue.offer({"type": "a2a_task", "task_id": f"tsk_{i}"})
    retained = []
    while not queue.queue.empty():
        retained.append(queue.queue.get_nowait())
    assert len(retained) == 256 and retained[0]["task_id"] == "tsk_44"
    print(
        "CONFIRMED offline backlog 300: initial websocket enqueue retains 256; "
        "drops first 44 tasks and welcome"
    )

    session = SimpleNamespace(add=Mock())
    target = SimpleNamespace(agent_id="agt_fixture")
    message = {
        "messageId": "retry-same-message",
        "role": "ROLE_USER",
        "parts": [{"text": "TEST_NOT_REAL"}],
    }
    with patch("agora_api.a2a_service.append_event", new=AsyncMock()):
        first = await create_task(
            session,
            initiator_agent_id="agt_sender",
            target=target,
            message=message,
            trace_id=None,
            commit=False,
        )
        second = await create_task(
            session,
            initiator_agent_id="agt_sender",
            target=target,
            message=message,
            trace_id=None,
            commit=False,
        )
    assert first.task_id != second.task_id
    print("CONFIRMED repeated messageId generates different tasks; no request-level dedup")

    agent = SimpleNamespace(agent_id="agt_fixture", name="TEST_NOT_REAL", current_version_id="v1")
    canonical = build_agent_card(agent, "https://api.example.org")
    served = build_agent_card(agent, "http://internal-proxy:8700")
    key = OKPKey.generate_key("Ed25519")
    compact = jws.serialize_compact(
        {"alg": CARD_SIGNING_ALG, "kid": "dev_fixture"},
        canonical_payload(canonical),
        key,
        algorithms=[CARD_SIGNING_ALG],
    )
    public = key.as_dict()["x"]
    assert verify_card_signature(canonical, compact, public, "dev_fixture")
    assert not verify_card_signature(served, compact, public, "dev_fixture")
    print(
        "CONFIRMED signed canonical card fails verification if served with a different proxy origin"
    )


asyncio.run(main())
