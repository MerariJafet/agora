"""Canonical signed-message construction. Must match apps/api/agora_api/crypto.py
(single protocol constant, duplicated by design across trust boundaries — the
Bridge must not import server code)."""

REGISTER_CONTEXT = "agora.register.v1"


def registration_message(
    challenge_id: str, nonce: str, public_key_b64: str, agent_name: str
) -> bytes:
    return f"{REGISTER_CONTEXT}|{challenge_id}|{nonce}|{public_key_b64}|{agent_name}".encode()
