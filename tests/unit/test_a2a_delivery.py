"""Pure API delivery/receipt probes without a DB, broker or network."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from agora_api.a2a_service import build_agent_card
from agora_api.card_signing import CARD_SIGNING_ALG, canonical_payload, verify_card_signature
from agora_api.realtime import RtClient
from agora_api.routes import a2a, realtime
from joserfc import jws
from joserfc.jwk import OKPKey
from starlette.requests import Request


class Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def test_refill_round_robin_reaches_all_300_pending_tasks(monkeypatch):
    tasks = [SimpleNamespace(
        task_id=f"tsk_{i:026d}", context_id="fixture", message={}, nonce="fixture",
        initiator_agent_id="agt_sender", target_agent_id="agt_target",
    ) for i in range(300)]
    client = RtClient(kind="bridge", agent_id="agt_target", a2a_ready=True)
    seen, cursors = set(), []

    async def pending(session, agent_id, *, limit, after_task_id):
        cursors.append(after_task_id)
        return [t for t in tasks if after_task_id is None or t.task_id > after_task_id][:limit]

    async def tick(delay):
        while not client.queue.empty():
            seen.add(client.queue.get_nowait()["task_id"])
        if len(seen) == 300:
            client.closed = True

    monkeypatch.setattr(realtime, "session_factory", lambda: Session)
    monkeypatch.setattr(realtime, "resolve_device_session", AsyncMock(
        return_value=SimpleNamespace(agent_id="agt_target")
    ))
    monkeypatch.setattr(realtime, "pending_tasks_for", pending)
    monkeypatch.setattr(realtime.asyncio, "sleep", tick)
    await realtime._refill_pending(client, "synthetic-token")
    assert len(seen) == 300
    assert cursors[:2] == [None, tasks[63].task_id]


def test_bridge_overload_never_evicts_queued_work_or_control():
    client = RtClient(kind="bridge", a2a_ready=True)
    assert client.offer({"type": "welcome"})
    accepted = []
    for i in range(300):
        if client.offer({"type": "a2a_task", "task_id": str(i)}):
            accepted.append(str(i))
    assert client.offer({"type": "a2a_result_ack", "task_id": "done"})
    queued = []
    while not client.queue.empty():
        queued.append(client.queue.get_nowait())
    assert queued[0] == {"type": "welcome"}
    assert [f["task_id"] for f in queued if f["type"] == "a2a_task"] == accepted
    assert queued[-1]["type"] == "a2a_result_ack"
    assert len(accepted) < 300  # unqueued work remains in durable server storage


async def test_served_card_signature_covers_exact_bytes_despite_proxy_origin(monkeypatch):
    from agora_api import card_signing, config

    agent = SimpleNamespace(agent_id="agt_fixture", name="TEST", current_version_id="v1")
    canonical = build_agent_card(agent, "https://public.example.org")
    key = OKPKey.generate_key("Ed25519")
    compact = jws.serialize_compact(
        {"alg": CARD_SIGNING_ALG, "kid": "dev_fixture"}, canonical_payload(canonical), key,
        algorithms=[CARD_SIGNING_ALG],
    )
    protected, _, signature = compact.split(".")
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(
        public_base_url="https://public.example.org"
    ))
    monkeypatch.setattr(card_signing, "signature_state", AsyncMock(
        return_value=("verified", {"protected": protected, "signature": signature})
    ))
    agent.status = "registered"
    request = Request({"type": "http", "scheme": "http", "path": "/", "root_path": "",
                       "headers": [(b"host", b"internal-proxy:8700")],
                       "server": ("internal-proxy", 8700), "query_string": b""})
    response = await a2a.agent_card("agt_fixture", request, SimpleNamespace(get=AsyncMock(
        return_value=agent
    )))
    assert verify_card_signature(response["card"], compact, key.as_dict()["x"], "dev_fixture")
    assert response["card"]["supportedInterfaces"][0]["url"].startswith("https://public.example.org/")


async def test_legacy_bridge_gets_no_tasks_from_nats_or_durable_refill(monkeypatch):
    import json

    from agora_api.realtime import RealtimeGateway

    client = RtClient(kind="bridge", agent_id="agt_target")
    gateway = RealtimeGateway()
    gateway.register(client)
    frame = {"scope": "agt_target", "kind": "a2a_task", "data": {"task_id": "unsafe-old-client"}}
    await gateway._on_nats(SimpleNamespace(data=json.dumps(frame).encode()))
    assert client.queue.empty()
    pending = AsyncMock()

    async def tick(delay):
        client.closed = True

    monkeypatch.setattr(realtime, "session_factory", lambda: Session)
    monkeypatch.setattr(realtime, "resolve_device_session", AsyncMock(
        return_value=SimpleNamespace(agent_id="agt_target")
    ))
    monkeypatch.setattr(realtime, "pending_tasks_for", pending)
    monkeypatch.setattr(realtime.asyncio, "sleep", tick)
    await realtime._refill_pending(client, "synthetic-token")
    pending.assert_not_awaited()
    assert client.queue.empty()
    client.closed = False
    client.a2a_ready = True
    await gateway._on_nats(SimpleNamespace(data=json.dumps(frame).encode()))
    assert client.queue.get_nowait()["type"] == "a2a_task"
