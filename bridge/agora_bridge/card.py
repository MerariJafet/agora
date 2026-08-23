"""Bridge-side Agent Card signing (S3-G01).

The Bridge fetches its own canonical card from AGORA, signs the canonical
serialization with the LOCAL device Ed25519 key (JWS, alg "Ed25519" per
RFC 9864) and publishes only the signature. The private key never leaves the
machine — signing happens here, exactly like registration and revocation.
"""

import json
from typing import Any

from joserfc import jws

from agora_bridge.identity import IdentityManager

CARD_SIGNING_ALG = "Ed25519"


def canonical_payload(card: dict[str, Any]) -> bytes:
    """Must match apps/api/agora_api/card_signing.canonical_payload — the
    constant is duplicated across the trust boundary by design (the Bridge
    never imports server code)."""
    unsigned = {k: v for k, v in card.items() if k != "signatures"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


def sign_card(card: dict[str, Any], identity: IdentityManager, device_id: str) -> str:
    """Compact JWS over the canonical card payload, signed locally."""
    return jws.serialize_compact(
        {"alg": CARD_SIGNING_ALG, "kid": device_id},
        canonical_payload(card),
        identity.jwk(device_id),
        algorithms=[CARD_SIGNING_ALG],
    )
