"""Signed A2A Agent Cards (S3-G01).

Trust model (documented, no invented wire fields):
- The signing key IS the agent's registered Device Ed25519 key. AGORA already
  binds that key to the agent through challenge-response registration, so a
  valid card signature proves "the machine that owns this agent authored this
  card" — the same authority that registers, revokes and acts.
- Signatures use JWS with alg **"Ed25519"** (RFC 9864 fully-specified EdDSA)
  and ride the STANDARD `AgentCard.signatures` field of a2a-sdk 1.1.2.
  `protected.kid` carries the AGORA `device_id`; the public key is resolvable
  from the AGORA registry (and from the device record).
- The signed payload is the CANONICAL card built by `build_agent_card()`
  against the configured public base URL, so verification is deterministic
  and independent of which host served the request.

Card states returned by the registry:
- `verified`  — signature present and valid for a currently authorized device.
- `unsigned`  — legacy card with no signature. NEVER labelled verified.
- invalid     — signature present but wrong/tampered/revoked-device: the card
                is REJECTED (409/`card_signature_invalid`), never served as
                if it were fine.
"""

import json
from typing import Any

from joserfc import jws
from joserfc.jwk import OKPKey
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agora_api.crypto import b64url_decode
from agora_api.errors import AgoraError
from agora_api.logging import get_logger
from agora_api.models import Agent, Device

log = get_logger("agora.api.card_signing")

CARD_SIGNING_ALG = "Ed25519"  # RFC 9864 fully-specified EdDSA


class CardSignatureInvalid(AgoraError):
    status_code = 409
    code = "card_signature_invalid"


def canonical_payload(card: dict[str, Any]) -> bytes:
    """Stable serialization of the card WITHOUT its signatures block."""
    unsigned = {k: v for k, v in card.items() if k != "signatures"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


def public_jwk(public_key_b64: str, device_id: str) -> OKPKey:
    """AGORA stores raw 32-byte Ed25519 keys base64url-unpadded — exactly the
    JWK `x` encoding, so the conversion is a re-label, not a re-encode."""
    if len(b64url_decode(public_key_b64)) != 32:
        raise ValueError("not an Ed25519 public key")
    return OKPKey.import_key(
        {"kty": "OKP", "crv": "Ed25519", "x": public_key_b64.rstrip("="), "kid": device_id}
    )


def verify_card_signature(card: dict[str, Any], signature_jws: str,
                          public_key_b64: str, device_id: str) -> bool:
    """Detached-style verification: the JWS payload must equal the canonical
    serialization of the card we independently rebuilt."""
    try:
        key = public_jwk(public_key_b64, device_id)
        obj = jws.deserialize_compact(signature_jws, key, algorithms=[CARD_SIGNING_ALG])
    except Exception as exc:
        log.info("card.signature_verify_failed", device_id=device_id,
                 error=type(exc).__name__)
        return False
    if obj.protected.get("kid") != device_id:
        return False
    return obj.payload == canonical_payload(card)


async def signature_state(
    session: AsyncSession, agent: Agent, card: dict[str, Any]
) -> tuple[str, dict[str, Any] | None]:
    """Returns (state, signatures_block_or_None). Raises when a stored
    signature exists but does not verify — an invalid card is never served."""
    if not agent.card_jws:
        return "unsigned", None

    devices = (
        (
            await session.execute(
                select(Device).where(
                    Device.agent_id == agent.agent_id, Device.status == "authorized"
                )
            )
        )
        .scalars()
        .all()
    )
    for device in devices:
        if verify_card_signature(card, agent.card_jws, device.public_key, device.device_id):
            protected, _, sig = agent.card_jws.split(".")
            return "verified", {"protected": protected, "signature": sig}
    raise CardSignatureInvalid(
        "Stored Agent Card signature does not verify against any authorized device."
    )
