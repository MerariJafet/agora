"""Ed25519 verification (server side only — the server NEVER holds private keys).

Wire encoding: raw 32-byte public keys and 64-byte signatures, base64url
without padding (see packages/protocol/schemas/common.schema.json).
"""

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REGISTER_CONTEXT = "agora.register.v1"


def b64url_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded)


def b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def registration_message(
    challenge_id: str, nonce: str, public_key_b64: str, agent_name: str
) -> bytes:
    """Canonical signed string. Binds the challenge, its nonce, the key and the
    agent name so a signature cannot be replayed for a different registration."""
    return f"{REGISTER_CONTEXT}|{challenge_id}|{nonce}|{public_key_b64}|{agent_name}".encode()


def verify_signature(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    try:
        raw_key = b64url_decode(public_key_b64)
        raw_sig = b64url_decode(signature_b64)
        if len(raw_key) != 32 or len(raw_sig) != 64:
            return False
        Ed25519PublicKey.from_public_bytes(raw_key).verify(raw_sig, message)
        return True
    except (InvalidSignature, ValueError):
        return False
