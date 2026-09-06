"""Public, signed identity credential for one canonical AGORA Agent.

The credential is the portable view of the existing AgentGenesis record.  It
does not replace device authentication and an optional chain token is only a
non-transferable mirror: ownership of such a token grants no AGORA authority.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.config import get_settings
from agora_api.errors import NotFound
from agora_api.models import Agent, AgentGenesis
from agora_api.world_signing import sign_canonical_payload, trust_bootstrap

IDENTITY_DOMAIN = "agora.agent.identity.v1"
IDENTITY_VERSION = "agent-identity.v1"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def agent_identity_credential(session: AsyncSession, agent_id: str) -> dict[str, Any]:
    agent = await session.get(Agent, agent_id)
    genesis = await session.get(AgentGenesis, agent_id)
    if agent is None or genesis is None:
        raise NotFound("Agent identity not found.")

    settings = get_settings()
    identity_hash = _sha256(f"{settings.world_instance_id}|{agent.agent_id}")
    payload = {
        "credential_version": IDENTITY_VERSION,
        "credential_id": f"urn:agora:agent-identity:{identity_hash}",
        "world_instance_id": settings.world_instance_id,
        "subject": {
            "agent_id": agent.agent_id,
            "name": agent.name,
            "status": agent.status,
            "current_agent_version_id": agent.current_version_id,
            "agent_public_key": genesis.agent_public_key,
            "public_key_fingerprint_sha256": _sha256(genesis.agent_public_key),
        },
        "genesis": {
            "event_id": genesis.genesis_event_id,
            "born_at": genesis.born_at.isoformat().replace("+00:00", "Z"),
            "constitution_hash": genesis.constitution_hash,
        },
        "non_transferable_token_mirror": {
            "token_id": str(int(identity_hash, 16)),
            "identity_hash": identity_hash,
            "standards": ["ERC-721", "ERC-5192"],
            "state": "not_minted",
            "network": None,
            "contract_address": None,
            "required_for_world_entry": False,
            "grants_authority": False,
            "grants_local_permissions": False,
        },
        "trust": {
            "root": "agent_genesis_and_authorized_ed25519_devices",
            "token_is_optional_public_mirror": True,
            "private_key_material_included": False,
        },
    }
    return {
        "credential": payload,
        "signature": sign_canonical_payload(payload, domain=IDENTITY_DOMAIN),
        "trust_bootstrap": trust_bootstrap(),
    }
