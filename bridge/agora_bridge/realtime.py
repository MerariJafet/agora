"""RealtimeConnection (S2-T08, ADR-0010): outbound-only authenticated WS.

- Auth: `Authorization: Bearer <session>` header — never a query string.
- Reconnect: bounded exponential backoff with jitter; NEVER reconnects after
  an explicit local pause, `agora revoke`, or a server `revoked` frame.
- Bounded queues: incoming A2A work goes to the bounded A2AInbox; incoming
  notifications to a bounded deque. Nothing grows without limit.
- Presence: heartbeat frame every HEARTBEAT_INTERVAL seconds (server holds
  the TTL); a crashed Bridge just expires.
"""

import asyncio
import contextlib
import json
import random
from collections import deque
from typing import Any

import websockets

from agora_bridge.audit import LocalAuditLog
from agora_bridge.config import BridgeConfig
from agora_bridge.inbox import A2AInbox
from agora_bridge.runtime import RuntimeAdapter
from agora_bridge.trust import wrap_untrusted

HEARTBEAT_INTERVAL = 10.0
BACKOFF_BASE = 1.0
BACKOFF_MAX = 60.0
MAX_RECONNECT_ATTEMPTS = 30
NOTIFICATIONS_LIMIT = 200


class RealtimeConnection:
    def __init__(
        self,
        config: BridgeConfig,
        session_token: str,
        runtime: RuntimeAdapter | None = None,
        audit: LocalAuditLog | None = None,
    ):
        self.config = config
        self._token = session_token
        self.runtime = runtime
        self.audit = audit or LocalAuditLog()
        self.inbox = A2AInbox()
        self.notifications: deque[dict[str, Any]] = deque(maxlen=NOTIFICATIONS_LIMIT)
        self.revoked = False
        self._stop = asyncio.Event()
        self._ws: Any = None
        self.connected = asyncio.Event()

    @property
    def ws_url(self) -> str:
        base = self.config.api_url.replace("http://", "ws://").replace("https://", "wss://")
        return f"{base}/v1/realtime/bridge"

    def stop(self) -> None:
        """Graceful shutdown (also used after pause/revoke: no reconnect)."""
        self._stop.set()

    async def run(self) -> None:
        attempt = 0
        while not self._stop.is_set() and not self.revoked:
            try:
                await self._session()
                attempt = 0  # clean session reset backoff
            except (OSError, websockets.WebSocketException) as exc:
                if self._stop.is_set() or self.revoked:
                    break
                attempt += 1
                if attempt > MAX_RECONNECT_ATTEMPTS:
                    self.audit.record("realtime.giving_up", attempts=attempt)
                    break
                delay = min(BACKOFF_MAX, BACKOFF_BASE * (2 ** (attempt - 1)))
                delay *= 0.5 + random.random()  # jitter  # noqa: S311
                self.audit.record("realtime.reconnect_scheduled",
                                  attempt=attempt, delay_seconds=round(delay, 1),
                                  error=type(exc).__name__)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)

    async def _session(self) -> None:
        async with websockets.connect(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self._token}"},
            max_size=1 << 20,
        ) as ws:
            self._ws = ws
            self.connected.set()
            self.audit.record("realtime.connected", agent=self.config.agent_name)
            heartbeat = asyncio.create_task(self._heartbeat_loop(ws))
            try:
                async for raw in ws:
                    if self._stop.is_set():
                        break
                    await self._handle_frame(ws, raw)
                    if self.revoked:
                        break
            finally:
                self.connected.clear()
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
                self._ws = None

    async def _heartbeat_loop(self, ws) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"type": "heartbeat"}))

    async def _handle_frame(self, ws, raw: str | bytes) -> None:
        try:
            frame = json.loads(raw)
        except ValueError:
            return
        ftype = frame.get("type")
        if ftype == "revoked":
            self.revoked = True
            self._stop.set()
            self.audit.record("realtime.revoked_by_server")
            return
        if ftype == "a2a_task":
            accepted = self.inbox.offer(frame)
            self.audit.record("a2a.task_received",
                              task_id=frame.get("task_id"), accepted=accepted)
            if accepted and self.runtime is not None:
                await self._process_one(ws)
            return
        if ftype in ("message", "presence", "a2a_completed"):
            # Social/relay notifications: bounded, untrusted.
            self.notifications.append(wrap_untrusted(frame))

    async def _process_one(self, ws) -> None:
        if self.runtime is None:
            return
        wrapped = self.inbox.take()
        if wrapped is None:
            return
        result = self.runtime.handle_task(wrapped)
        task_id = wrapped["content"].get("task_id")
        if result.accepted:
            await ws.send(json.dumps(
                {"type": "a2a_result", "task_id": task_id, "artifacts": result.artifacts}
            ))
            self.audit.record("a2a.task_completed", task_id=task_id)
        else:
            self.audit.record("a2a.task_rejected", task_id=task_id, reason=result.reason)
