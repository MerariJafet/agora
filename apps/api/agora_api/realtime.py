"""Realtime gateway (S2-T08/T09, ADR-0010).

Two planes, deliberately distinct:
- Durable ledger events: outbox → NATS JetStream `agora.events.>` (Sprint 01).
- Ephemeral realtime fanout: core NATS subjects `agora.rt.{scope}.{kind}`
  where scope is a space_id (space-scoped interest), an agent_id (directed
  relay, e.g. A2A tasks) or `system` (control frames such as revocation).

Every fanout crosses NATS even when publisher and subscriber share a process,
so a second API process behaves identically (no process-local-only paths).

Clients:
- Bridges: outbound WS `/v1/realtime/bridge`, authenticated with the device
  session in the `Authorization` header (never a query string). Revocation
  closes the socket (system frame + per-heartbeat re-auth).
- Browsers: `/v1/realtime/web`, authenticated by the owner session cookie;
  subscribe to explicit space_ids only.
Outbound per-client queues are bounded; a slow client loses frames rather
than growing server memory (realtime is ephemeral by definition).
"""

import asyncio
import contextlib
import json
from dataclasses import dataclass, field

import nats

from agora_api.config import get_settings
from agora_api.logging import get_logger

log = get_logger("agora.api.realtime")

RT_PREFIX = "agora.rt"
CLIENT_QUEUE_LIMIT = 256


def rt_subject(scope: str, kind: str) -> str:
    return f"{RT_PREFIX}.{scope}.{kind}"


@dataclass(eq=False)  # identity semantics: clients live in a set
class RtClient:
    kind: str  # "bridge" | "browser"
    agent_id: str | None = None
    device_id: str | None = None
    spaces: set[str] = field(default_factory=set)
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(CLIENT_QUEUE_LIMIT))
    closed: bool = False

    def offer(self, frame: dict) -> None:
        """Bounded, lossy for ephemeral fanout: drop oldest when full."""
        try:
            self.queue.put_nowait(frame)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(frame)


class RealtimeGateway:
    def __init__(self) -> None:
        self._nc: nats.NATS | None = None
        self._clients: set[RtClient] = set()
        self._sub = None

    async def start(self) -> None:
        self._nc = await nats.connect(get_settings().nats_url)
        self._sub = await self._nc.subscribe(f"{RT_PREFIX}.>", cb=self._on_nats)
        log.info("realtime.gateway_started")

    async def stop(self) -> None:
        if self._sub is not None:
            await self._sub.unsubscribe()
            self._sub = None
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None

    # -- publication (any API process) -----------------------------------
    async def publish(self, scope: str, kind: str, data: dict) -> None:
        assert self._nc is not None, "gateway not started"
        await self._nc.publish(
            rt_subject(scope, kind), json.dumps({"scope": scope, "kind": kind, "data": data}).encode()
        )

    # -- fanout ------------------------------------------------------------
    async def _on_nats(self, msg) -> None:
        try:
            frame = json.loads(msg.data)
        except ValueError:
            return
        scope, kind = frame.get("scope"), frame.get("kind")
        for client in list(self._clients):
            if client.closed:
                continue
            if scope == "system":
                if kind == "device_revoked" and client.device_id == frame["data"].get("device_id"):
                    client.offer({"type": "revoked"})
                    client.closed = True
                continue
            if client.kind == "bridge" and scope == client.agent_id:
                client.offer({"type": kind, **frame["data"]})
            elif scope in client.spaces:
                client.offer({"type": kind, "space_id": scope, **frame["data"]})

    # -- registry ------------------------------------------------------------
    def register(self, client: RtClient) -> None:
        self._clients.add(client)

    def unregister(self, client: RtClient) -> None:
        self._clients.discard(client)
        client.closed = True

    def bridge_online(self, agent_id: str) -> bool:
        return any(
            c.kind == "bridge" and c.agent_id == agent_id and not c.closed
            for c in self._clients
        )


gateway = RealtimeGateway()
