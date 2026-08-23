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

from agora_api.a2a_service import complete_task, pending_tasks_for, _relay_frame
from agora_api.authz import bearer_token, resolve_device_session
from agora_api.db import session_factory
from agora_api.errors import AgoraError
from agora_api.logging import get_logger
from agora_api.models import Agent
from agora_api.owners import SESSION_COOKIE, resolve_web_session
from agora_api.presence import refresh_presence
from agora_api.realtime import RtClient, gateway

router = APIRouter(tags=["realtime"])
log = get_logger("agora.api.realtime.ws")

SEND_INTERVAL = 0.05


async def _pump(ws: WebSocket, client: RtClient) -> None:
    """Drain the client's bounded queue to the socket."""
    while not client.closed:
        try:
            frame = await asyncio.wait_for(client.queue.get(), timeout=1.0)
        except TimeoutError:
            continue
        await ws.send_text(json.dumps(frame))
        if frame.get("type") == "revoked":
            client.closed = True
    with contextlib.suppress(Exception):
        await ws.close(code=4403)


@router.websocket("/v1/realtime/bridge")
async def bridge_ws(ws: WebSocket) -> None:
    token = None
    auth = ws.headers.get("authorization")
    try:
        token = bearer_token(auth)
        async with session_factory()() as session:
            device = await resolve_device_session(session, token)
            agent = await session.get(Agent, device.agent_id)
            pending = await pending_tasks_for(session, device.agent_id)
    except AgoraError:
        await ws.close(code=4401)
        return

    await ws.accept()
    client = RtClient(kind="bridge", agent_id=device.agent_id, device_id=device.device_id)
    gateway.register(client)
    client.offer({"type": "welcome", "agent_id": device.agent_id, "device_id": device.device_id})
    # Predictable offline handling: queued submitted tasks arrive on connect.
    for task in pending:
        client.offer({"type": "a2a_task", **_relay_frame(task)})
    log.info("realtime.bridge_connected", agent_id=device.agent_id)

    pump = asyncio.create_task(_pump(ws, client))
    try:
        while not client.closed:
            raw = await ws.receive_text()
            try:
                frame = json.loads(raw)
            except ValueError:
                continue
            ftype = frame.get("type")
            if ftype == "heartbeat":
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
            elif ftype == "a2a_result":
                task_id = frame.get("task_id")
                artifacts = frame.get("artifacts")
                if isinstance(task_id, str) and isinstance(artifacts, list):
                    try:
                        async with session_factory()() as session:
                            await complete_task(session, task_id, artifacts)
                    except AgoraError as exc:
                        client.offer({"type": "a2a_result_rejected",
                                      "task_id": task_id, "code": exc.code})
    except WebSocketDisconnect:
        pass
    finally:
        gateway.unregister(client)
        pump.cancel()
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
            if frame.get("type") == "subscribe" and isinstance(frame.get("space_id"), str):
                client.spaces = {frame["space_id"]}  # space-scoped interest only
                client.offer({"type": "subscribed", "space_id": frame["space_id"]})
    except WebSocketDisconnect:
        pass
    finally:
        gateway.unregister(client)
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump
