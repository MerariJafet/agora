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


def public_interest_allows(scope: str, kind: str) -> bool:
    """Defense in depth after resource visibility checks at subscription time."""
    if kind in {"a2a_task", "a2a_completed"}:
        return False
    if scope.startswith("spc_"):
        return True
    if scope.startswith("mis_"):
        return kind in {"mission", "artifact", "mission_challenge"}
    return scope == "arena" and kind == "arena"


@dataclass(eq=False)  # identity semantics: clients live in a set
class RtClient:
    kind: str  # "bridge" | "browser"
    agent_id: str | None = None
    device_id: str | None = None
    spaces: set[str] = field(default_factory=set)
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(CLIENT_QUEUE_LIMIT))
    closed: bool = False
    a2a_ready: bool = False

    def offer(self, frame: dict) -> bool:
        """Only browser notifications are lossy. Bridge work is DB-refilled.

        Refuse overload rather than evicting queued work; reserve control
        headroom so task bursts do not displace result ACKs/revocation.
        """
        if self.kind == "bridge" and frame.get("type") == "a2a_task":
            if not self.a2a_ready:
                return False
            if self.queue.qsize() >= max(1, self.queue.maxsize - 16):
                return False
        try:
            self.queue.put_nowait(frame)
            return True
        except asyncio.QueueFull:
            if self.kind == "bridge":
                return False
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                self.queue.put_nowait(frame)
                return True
            return False


class RealtimeGateway:
    def __init__(self) -> None:
        self._nc: nats.NATS | None = None
        self._clients: set[RtClient] = set()
        self._sub: object | None = None

    async def start(self) -> None:
        self._nc = await nats.connect(get_settings().nats_url)
        self._sub = await self._nc.subscribe(f"{RT_PREFIX}.>", cb=self._on_nats)
        log.info("realtime.gateway_started")

    async def stop(self) -> None:
        if self._sub is not None:
            await self._sub.unsubscribe()  # type: ignore[attr-defined]
            self._sub = None
        if self._nc is not None:
            await self._nc.drain()
            self._nc = None

    # -- publication (any API process) -----------------------------------
    async def publish(self, scope: str, kind: str, data: dict) -> None:
        if self._nc is None:
            # Gateway not running (dev/test without lifespan): realtime fanout
            # is ephemeral by contract, so dropping it is safe. Production
            # fails at startup if NATS is unavailable (main.py lifespan).
            log.debug("realtime.publish_skipped_gateway_down", scope=scope, kind=kind)
            return
        body = json.dumps({"scope": scope, "kind": kind, "data": data}).encode()
        await self._nc.publish(rt_subject(scope, kind), body)

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
            elif (
                isinstance(scope, str)
                and isinstance(kind, str)
                and scope in client.spaces
                and public_interest_allows(scope, kind)
            ):
                # Even a corrupted/injected subscription set cannot cross the
                # direct-agent/public-interest boundary. A2A bodies stay directed.
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
