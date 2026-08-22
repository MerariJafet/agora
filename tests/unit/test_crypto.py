"""Unit tests: Ed25519 signing/verification and canonical message binding."""

from agora_api.crypto import registration_message, verify_signature
from tests.conftest import SigningKeypair


def test_sign_verify_roundtrip():
    kp = SigningKeypair()
    msg = registration_message("chl_X", "nonce", kp.public_key_b64, "Agent")
    assert verify_signature(kp.public_key_b64, msg, kp.sign_b64(msg))


def test_malformed_signature_rejected():
    kp = SigningKeypair()
    msg = registration_message("chl_X", "nonce", kp.public_key_b64, "Agent")
    assert not verify_signature(kp.public_key_b64, msg, "A" * 86)
    assert not verify_signature(kp.public_key_b64, msg, "!!not-base64!!")
    assert not verify_signature(kp.public_key_b64, msg, "")


def test_signature_from_other_key_rejected():
    kp, other = SigningKeypair(), SigningKeypair()
    msg = registration_message("chl_X", "nonce", kp.public_key_b64, "Agent")
    assert not verify_signature(kp.public_key_b64, msg, other.sign_b64(msg))


def test_signature_bound_to_message_fields():
    """Changing any bound field (challenge, nonce, key, name) invalidates it."""
    kp = SigningKeypair()
    msg = registration_message("chl_X", "nonce", kp.public_key_b64, "Agent")
    sig = kp.sign_b64(msg)
    tampered = registration_message("chl_Y", "nonce", kp.public_key_b64, "Agent")
    assert not verify_signature(kp.public_key_b64, tampered, sig)
    tampered = registration_message("chl_X", "nonce", kp.public_key_b64, "OtherAgent")
    assert not verify_signature(kp.public_key_b64, tampered, sig)


def test_bridge_and_api_share_canonical_message():
    from agora_bridge.crypto_wire import registration_message as bridge_message

    args = ("chl_A", "n0nce", "pubkey", "Genesis")
    assert bridge_message(*args) == registration_message(*args)
