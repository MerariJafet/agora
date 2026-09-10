"""A2A registry + JSON-RPC relay endpoints (S2-T15/T16)."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.a2a_service import (
    build_agent_card,
    create_task,
    get_task_for,
    jsonrpc_error,
    task_wire,
    validate_jsonrpc,
)
from agora_api.authz import CurrentDevice
from agora_api.db import get_session
from agora_api.errors import NotFound, ValidationFailed
from agora_api.models import Agent
from agora_api.presence import list_present
from agora_api.ratelimit import enforce_rate_limit

router = APIRouter(prefix="/v1/a2a", tags=["a2a"])


def _base_url(request: Request) -> str:
    from agora_api.config import get_settings

    return get_settings().public_base_url.rstrip("/")


@router.get("/agents")
async def registry(
    request: Request, session: AsyncSession = Depends(get_session), space_id: str | None = None
) -> dict:
    """AGORA registry discovery: complements standard Agent Card discovery
    (a client that already knows an agent's card URL never needs this).
    Optional space_id filters to agents currently present in that Space.
    Future skill filtering slots in here without schema changes."""
    agents = (
        (await session.execute(select(Agent).order_by(Agent.agent_id))).scalars().all()
    )
    if space_id is not None:
        present = {a["agent_id"] for a in await list_present(space_id)}
        agents = [a for a in agents if a.agent_id in present]
    base = _base_url(request)
    return {
        "agents": [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "card_url": f"{base}/v1/a2a/agents/{a.agent_id}/card",
            }
            for a in agents
        ]
    }


@router.get("/agents/{agent_id}/card")
async def agent_card(
    agent_id: str, request: Request, session: AsyncSession = Depends(get_session)
) -> dict:
    from agora_api.card_signing import signature_state
    from agora_api.config import get_settings

    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise NotFound("Agent not found.")
    # Signature verification runs against the CANONICAL card (built from the
    # configured public base URL), so it never depends on the serving host.
    canonical = build_agent_card(agent, get_settings().public_base_url)
    state, signature_block = await signature_state(session, agent, canonical)

    card = canonical
    if signature_block is not None:
        card["signatures"] = [signature_block]
    # AGORA-specific metadata lives BESIDE the standard card, never inside it.
    return {
        "card": card,
        "agora": {
            "agent_id": agent.agent_id,
            "status": agent.status,
            # "verified" | "unsigned". An invalid signature raises 409 above:
            # a tampered card is never served as if it were fine.
            "card_signature": state,
        },
    }


@router.post("/agents/{agent_id}/jsonrpc")
async def jsonrpc(
    agent_id: str,
    request: Request,
    device: CurrentDevice,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """JSON-RPC 2.0 relay for the target agent. Sprint 02 methods:
    message/send, tasks/get. Initiator must be an authenticated, non-revoked
    AGORA device. Payload contents are never logged."""
    await enforce_rate_limit("a2a_rpc", device.device_id)
    target = await session.get(Agent, agent_id)
    if target is None:
        raise NotFound("Target agent not found.")

    body = await request.json()
    request_id, method, params = validate_jsonrpc(body)

    if method == "message/send":
        message = params.get("message")
        if not isinstance(message, dict):
            return jsonrpc_error(request_id, -32602, "params.message required")
        task = await create_task(
            session,
            initiator_agent_id=device.agent_id,
            target=target,
            message=message,
            trace_id=getattr(request.state, "trace_id", None),
        )
        return {"jsonrpc": "2.0", "id": request_id, "result": {"task": task_wire(task)}}

    if method == "tasks/get":
        task_id = params.get("id")
        if not isinstance(task_id, str):
            return jsonrpc_error(request_id, -32602, "params.id required")
        task = await get_task_for(session, task_id, device.agent_id)
        return {"jsonrpc": "2.0", "id": request_id, "result": {"task": task_wire(task)}}

    return jsonrpc_error(request_id, -32601, f"Method not supported in Sprint 02: {method}")


@router.post("/validate-card")
async def validate_card_endpoint(request: Request) -> dict:
    """Utility: strict validation of an Agent Card against the official
    a2a-sdk implementation (used by tests and future federation checks)."""
    from agora_api.a2a_service import validate_agent_card

    body = await request.json()
    if not isinstance(body, dict):
        raise ValidationFailed("Expected a JSON Agent Card object.")
    validate_agent_card(body)
    return {"valid": True}
