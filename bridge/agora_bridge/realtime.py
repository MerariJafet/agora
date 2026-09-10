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
from agora_bridge.config import BridgeConfig, config_path
from agora_bridge.inbox import A2AInbox, durable_inbox_path
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
        self._config_path = config_path()
        self._require_local_config = self._config_path.exists()
        self._token = session_token
        self.runtime = runtime
        self.audit = audit or LocalAuditLog()
        self.inbox = A2AInbox(path=durable_inbox_path(config))
        self._claims: dict[str, tuple[str, asyncio.Future]] = {}
        self._worker_active = False
        self._work_available = asyncio.Event()
        self._protocol_ready = asyncio.Event()
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
        try:
            await self._run_until_stopped()
        finally:
            self.inbox.close()

    async def _run_until_stopped(self) -> None:
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
                self.audit.record(
                    "realtime.reconnect_scheduled",
                    attempt=attempt,
                    delay_seconds=round(delay, 1),
                    error=type(exc).__name__,
                )
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)

    async def _session(self) -> None:
        async with websockets.connect(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self._token}"},
            max_size=1 << 20,
        ) as ws:
            self._ws = ws
            self._protocol_ready.clear()
            self.connected.set()
            self.audit.record("realtime.connected", agent=self.config.agent_name)
            heartbeat = asyncio.create_task(self._heartbeat_loop(ws))
            self._worker_active = True
            self._work_available.set()
            worker = asyncio.create_task(self._work_loop(ws))
            stop_watcher = asyncio.create_task(self._close_when_stopped(ws))
            try:
                await ws.send(
                    json.dumps({"type": "bridge_capabilities", "a2a_delivery_protocol": 2})
                )
                async for raw in ws:
                    if self._stop.is_set():
                        break
                    await self._handle_frame(ws, raw)
                    if self.revoked:
                        break
            finally:
                self.connected.clear()
                for job in (heartbeat, worker, stop_watcher):
                    job.cancel()
                for job in (heartbeat, worker, stop_watcher):
                    with contextlib.suppress(
                        asyncio.CancelledError, OSError, websockets.WebSocketException
                    ):
                        await job
                self._worker_active = False
                self._ws = None
            if not self._protocol_ready.is_set() and not self._stop.is_set() and not self.revoked:
                raise OSError("server does not support required durable delivery protocol")

    async def _heartbeat_loop(self, ws) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"type": "heartbeat"}))
                if self._protocol_ready.is_set():
                    await self._flush_results(ws)

    async def _handle_frame(self, ws, raw: str | bytes) -> None:
        try:
            frame = json.loads(raw)
        except ValueError:
            return
        if not isinstance(frame, dict):
            return
        ftype = frame.get("type")
        if ftype == "bridge_capabilities_ack":
            if frame.get("a2a_delivery_protocol") == 2:
                self._protocol_ready.set()
                self._work_available.set()
                await self._flush_results(ws)
            return
        if ftype == "revoked":
            self.revoked = True
            self._stop.set()
            self.audit.record("realtime.revoked_by_server")
            return
        if ftype == "a2a_task_claim_ack":
            task_id = frame.get("task_id")
            pending = self._claims.get(task_id) if isinstance(task_id, str) else None
            if pending and pending[0] == frame.get("execution_id") and not pending[1].done():
                pending[1].set_result(frame.get("accepted") is True)
            return
        if ftype == "a2a_result_ack":
            task_id, status = frame.get("task_id"), frame.get("status")
            if isinstance(task_id, str) and isinstance(status, str):
                if self.inbox.acknowledge(task_id, status):
                    self.audit.record("a2a.result_acknowledged", task_id=task_id, status=status)
            return
        if ftype == "a2a_result_rejected":
            self.audit.record("a2a.result_requires_reconciliation", task_id=frame.get("task_id"))
            return
        if ftype == "a2a_task":
            accepted = self.inbox.offer(frame)
            self.audit.record("a2a.task_received", task_id=frame.get("task_id"), accepted=accepted)
            if accepted and self.runtime is not None:
                self._work_available.set()
                if not self._worker_active:
                    await self._process_one(ws)
            elif not accepted:
                # A duplicate after a lost send/ACK resends the persisted result.
                await self._flush_results(ws)
            return
        if ftype in ("message", "presence", "a2a_completed"):
            # Social/relay notifications: bounded, untrusted.
            self.notifications.append(wrap_untrusted(frame))

    def _local_pause_requested(self) -> bool:
        if self.config.paused:
            return True
        if not self._config_path.exists():
            return self._require_local_config
        try:
            current = json.loads(self._config_path.read_text())
            return (
                not isinstance(current, dict)
                or current.get("paused") is not False
                or current.get("agent_id") != self.config.agent_id
                or current.get("api_url", "").rstrip("/") != self.config.api_url.rstrip("/")
            )
        except (OSError, ValueError, AttributeError):
            return True  # ambiguous local authority fails closed

    async def _close_when_stopped(self, ws) -> None:
        started = asyncio.get_running_loop().time()
        while not self._stop.is_set():
            if (
                not self._protocol_ready.is_set()
                and asyncio.get_running_loop().time() - started > 10
            ):
                self.audit.record("realtime.delivery_protocol_unavailable")
                break
            if self._local_pause_requested():
                self._stop.set()
                self.audit.record("realtime.paused_locally")
                break
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._stop.wait(), timeout=0.5)
        await ws.close()

    async def _flush_results(self, ws) -> None:
        for frame in self.inbox.pending_results():
            await ws.send(json.dumps(frame))

    async def _work_loop(self, ws) -> None:
        try:
            await self._protocol_ready.wait()
            while not self._stop.is_set() and not self.revoked:
                await self._work_available.wait()
                self._work_available.clear()
                while self.runtime is not None and self.inbox.pending_count():
                    if self._local_pause_requested():
                        self._stop.set()
                    if self._stop.is_set() or self.revoked:
                        break
                    await self._process_one(ws)
        except (OSError, TimeoutError, websockets.WebSocketException):
            # Let the receive loop end and reconnect. Result is already on disk.
            await ws.close()

    async def _process_one(self, ws) -> None:
        if self.runtime is None:
            return
        wrapped = self.inbox.take()
        if wrapped is None:
            return
        task_id = wrapped["content"]["task_id"]
        execution_id = self.inbox.execution_id(task_id)
        decision = asyncio.get_running_loop().create_future()
        self._claims[task_id] = (execution_id, decision)
        try:
            await ws.send(
                json.dumps(
                    {"type": "a2a_task_claim", "task_id": task_id, "execution_id": execution_id}
                )
            )
            accepted = await asyncio.wait_for(decision, timeout=10)
        except BaseException:
            # No runtime was called; replaying the same persistent claim is safe.
            self.inbox.release_claim_wait(task_id)
            raise
        finally:
            self._claims.pop(task_id, None)
        if not accepted:
            self.inbox.release_claim_wait(task_id, claimed_elsewhere=True)
            self.audit.record("a2a.task_owned_elsewhere", task_id=task_id)
            return
        if self.revoked or self._stop.is_set() or self._local_pause_requested():
            self._stop.set()
            self.inbox.release_claim_wait(task_id)
            self.audit.record("a2a.execution_blocked_by_local_state", task_id=task_id)
            return
        self.inbox.mark_running(task_id)
        # Keep receiving ACKs/revocation and sending heartbeats during model work.
        execution = asyncio.create_task(asyncio.to_thread(self.runtime.handle_task, wrapped))
        cancelled = False
        try:
            try:
                result = await asyncio.shield(execution)
            except asyncio.CancelledError:
                # A Python thread cannot safely be killed. Persist its eventual
                # result before allowing reconnect/shutdown to release ownership.
                cancelled = True
                result = await execution
            if result.accepted:
                frame = self.inbox.save_result(task_id, result.artifacts)
            else:
                frame = self.inbox.save_result(
                    task_id, [], status="rejected", reason="runtime_declined"
                )
        except Exception:
            frame = self.inbox.save_result(
                task_id,
                [],
                status="failed",
                reason="runtime_execution_failed_requires_reconciliation",
            )
        self.audit.record("a2a.result_persisted", task_id=task_id, status=frame["status"])
        if cancelled:
            raise asyncio.CancelledError
        await ws.send(json.dumps(frame))
