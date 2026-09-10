"""Realtime WebSocket endpoints (S2-T08/T09).

Bridge auth: `Authorization: Bearer <session>` HEADER on the WS handshake —
tokens never travel in query strings. Browser auth: owner session cookie
(sent automatically on same-origin WS upgrade). Both reuse the Sprint 01.1
transport-agnostic authorization (`resolve_device_session` /
`resolve_web_session`), so revocation semantics are identical everywhere.
"""

import asyncio
import contextlib
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from agora_api.a2a_service import _relay_frame, claim_task, complete_task, pending_tasks_for
from agora_api.authz import bearer_token, resolve_device_session
from agora_api.db import session_factory
from agora_api.errors import AgoraError
from agora_api.logging import get_logger
from agora_api.models import Mission, RecordProvenance, Space
from agora_api.owners import SESSION_COOKIE, resolve_web_session
from agora_api.presence import refresh_presence
from agora_api.provenance import visible_record_condition
from agora_api.realtime import RtClient, gateway

router = APIRouter(tags=["realtime"])
log = get_logger("agora.api.realtime.ws")

SEND_INTERVAL = 0.05
MAX_SPACE_SUBSCRIPTIONS = 32
TASK_REFILL_INTERVAL = 1.0
TASK_REFILL_PAGE = 64
A2A_DELIVERY_PROTOCOL = 2


async def _public_space_exists(session, space_id: str) -> bool:
    if not space_id.startswith("spc_") or len(space_id) > 30:
        return False
    result = await session.execute(
        select(Space.space_id)
        .join(
            RecordProvenance,
            (RecordProvenance.record_table == "spaces")
            & (RecordProvenance.record_id == Space.space_id),
        )
        .where(
            Space.space_id == space_id,
            visible_record_condition("spaces", Space.space_id),
        )
    )
    return result.scalar_one_or_none() is not None


async def _public_interest_exists(session, scope: str) -> bool:
    """Legacy space_id wire field accepts only explicitly public typed interests."""
    if scope == "arena":
        # Static public aggregate advertised by the Arena UI/API. Gateway
        # restricts this scope to arena events, never arbitrary direct frames.
        return True
    if scope.startswith("spc_"):
        return await _public_space_exists(session, scope)
    if not scope.startswith("mis_") or len(scope) > 30:
        return False
    result = await session.execute(
        select(Mission.mission_id)
        .join(
            RecordProvenance,
            (RecordProvenance.record_table == "missions")
            & (RecordProvenance.record_id == Mission.mission_id),
        )
        .where(
            Mission.mission_id == scope,
            Mission.visibility == "public",
            visible_record_condition("missions", Mission.mission_id),
        )
    )
    return result.scalar_one_or_none() is not None


async def _pump(ws: WebSocket, client: RtClient) -> None:
    """Drain the client's bounded queue to the socket."""
    while not client.closed:
        try:
            frame = await asyncio.wait_for(client.queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        if frame.get("type") == "a2a_task" and not client.a2a_ready:
            continue  # version downgrade/unsupported client: durable task remains pending
        await ws.send_text(json.dumps(frame))
        if frame.get("type") == "revoked":
            client.closed = True
    with contextlib.suppress(Exception):
        await ws.close(code=4403)


async def _refill_pending(client: RtClient, token: str) -> None:
    """Round-robin durable work scan, independent of NATS notifications.

    The cursor advances over enqueued work and wraps at the end, so slow
    early tasks cannot starve the rest of a backlog. Queue refusal leaves
    the cursor before the refused task, and no delivery is an execution ACK.
    """
    cursor = None
    while not client.closed:
        room = client.queue.maxsize - client.queue.qsize() - 16
        try:
            async with session_factory()() as session:
                device = await resolve_device_session(session, token)
                if client.a2a_ready and room > 0:
                    pending = await pending_tasks_for(
                        session, device.agent_id, limit=min(room, TASK_REFILL_PAGE),
                        after_task_id=cursor,
                    )
                    if not pending:
                        cursor = None
                    for task in pending:
                        if not client.offer({"type": "a2a_task", **_relay_frame(task)}):
                            break
                        cursor = task.task_id
        except AgoraError:
            # Reliable control enqueue. The pump closes the websocket after it.
            await client.queue.put({"type": "revoked"})
            return
        except Exception as exc:
            # DB/broker outages must not terminate the durable retry loop.
            log.warning("a2a.refill_deferred", error=type(exc).__name__)
        await asyncio.sleep(TASK_REFILL_INTERVAL)


@router.websocket("/v1/realtime/bridge")
async def bridge_ws(ws: WebSocket) -> None:
    token = None
    auth = ws.headers.get("authorization")
    try:
        token = bearer_token(auth)
        async with session_factory()() as session:
            device = await resolve_device_session(session, token)
    except AgoraError:
        await ws.close(code=4401)
        return

    await ws.accept()
    client = RtClient(kind="bridge", agent_id=device.agent_id, device_id=device.device_id)
    gateway.register(client)
    client.offer({"type": "welcome", "agent_id": device.agent_id, "device_id": device.device_id})
    log.info("realtime.bridge_connected", agent_id=device.agent_id)

    pump = asyncio.create_task(_pump(ws, client))
    refill = asyncio.create_task(_refill_pending(client, token))
    try:
        while not client.closed:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(frame, dict):
                continue
            ftype = frame.get("type")
            if ftype == "bridge_capabilities":
                version = frame.get("a2a_delivery_protocol")
                if type(version) is not int or version != A2A_DELIVERY_PROTOCOL:
                    client.a2a_ready = False
                    client.offer({
                        "type": "bridge_capabilities_rejected",
                        "required_a2a_delivery_protocol": A2A_DELIVERY_PROTOCOL,
                    })
                    continue
                # ACK is queued before any task can pass either delivery path.
                await asyncio.wait_for(client.queue.put({
                    "type": "bridge_capabilities_ack",
                    "a2a_delivery_protocol": A2A_DELIVERY_PROTOCOL,
                }), timeout=10)
                client.a2a_ready = True
            elif ftype == "heartbeat":
                # Re-authenticate on every heartbeat: a revoked device's
                # realtime access dies within one heartbeat interval even if
                # the system fanout frame was missed.
                try:
                    async with session_factory()() as session:
                        await resolve_device_session(session, token)
                except AgoraError:
                    client.offer({"type": "revoked"})
                    break
                await refresh_presence(device.agent_id)
                client.offer({"type": "heartbeat_ack"})
            elif ftype == "a2a_task_claim":
                task_id, execution_id = frame.get("task_id"), frame.get("execution_id")
                if isinstance(task_id, str) and isinstance(execution_id, str):
                    accepted, code = False, None
                    try:
                        async with session_factory()() as session:
                            current = await resolve_device_session(session, token)
                            accepted = await claim_task(
                                session, task_id, completing_agent_id=current.agent_id,
                                execution_id=execution_id,
                            )
                    except AgoraError as exc:
                        code = exc.code
                    await asyncio.wait_for(client.queue.put({
                        "type": "a2a_task_claim_ack", "task_id": task_id,
                        "execution_id": execution_id[:36], "accepted": accepted, "code": code,
                    }), timeout=10)
            elif ftype == "a2a_result":
                task_id = frame.get("task_id")
                artifacts = frame.get("artifacts")
                if isinstance(task_id, str) and isinstance(artifacts, list):
                    try:
                        async with session_factory()() as session:
                            # A handshake is not continuing authority: a device
                            # may have been revoked since it connected, even if
                            # the ephemeral revocation notification was lost.
                            current = await resolve_device_session(session, token)
                            await complete_task(
                                session, task_id, artifacts,
                                completing_agent_id=current.agent_id,
                                result_status=frame.get("status", "completed"),
                                reason=frame.get("reason"),
                                execution_id=frame.get("execution_id"), require_claim=True,
                            )
                        await asyncio.wait_for(client.queue.put({
                            "type": "a2a_result_ack", "task_id": task_id,
                            "status": frame.get("status", "completed"),
                        }), timeout=10)
                    except AgoraError as exc:
                        client.offer({"type": "a2a_result_rejected",
                                      "task_id": task_id, "code": exc.code})
    except WebSocketDisconnect:
        pass
    finally:
        gateway.unregister(client)
        refill.cancel()
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await refill
        with contextlib.suppress(asyncio.CancelledError):
            await pump
        log.info("realtime.bridge_disconnected", agent_id=device.agent_id)


@router.websocket("/v1/realtime/web")
async def web_ws(ws: WebSocket) -> None:
    cookie = ws.cookies.get(SESSION_COOKIE)
    try:
        async with session_factory()() as session:
            await resolve_web_session(session, cookie)
    except AgoraError:
        await ws.close(code=4401)
        return

    await ws.accept()
    client = RtClient(kind="browser")
    gateway.register(client)
    pump = asyncio.create_task(_pump(ws, client))
    try:
        while not client.closed:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            ftype = frame.get("type")
            space_id = frame.get("space_id")
            if ftype == "subscribe" and isinstance(space_id, str):
                # Interest is ADDITIVE and bounded: a world view legitimately
                # watches several Spaces at once, but a client cannot grow its
                # subscription set without limit.
                if len(client.spaces) >= MAX_SPACE_SUBSCRIPTIONS and space_id not in client.spaces:
                    client.offer({"type": "subscribe_rejected", "reason": "limit"})
                    continue
                async with session_factory()() as session:
                    if not await _public_interest_exists(session, space_id):
                        client.offer({"type": "subscribe_rejected", "reason": "not_found"})
                        continue
                client.spaces.add(space_id)
                client.offer({"type": "subscribed", "space_id": space_id})
            elif ftype == "unsubscribe" and isinstance(space_id, str):
                client.spaces.discard(space_id)
    except WebSocketDisconnect:
        pass
    finally:
        gateway.unregister(client)
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump
