"""Signed Agent Card tests (S3-G01/T22)."""

import base64
import json

import pytest
from agora_api.a2a_service import build_agent_card
from agora_api.card_signing import CARD_SIGNING_ALG, canonical_payload
from agora_api.config import get_settings
from agora_api.db import session_factory
from agora_api.models import Agent
from joserfc import jws
from joserfc.jwk import OKPKey

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


def _signing_jwk(keypair: SigningKeypair, device_id: str) -> OKPKey:
    from cryptography.hazmat.primitives import serialization

    raw_priv = keypair._private.private_bytes(  # noqa: SLF001 - test helper
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    return OKPKey.import_key({
        "kty": "OKP", "crv": "Ed25519",
        "x": keypair.public_key_b64,
        "d": base64.urlsafe_b64encode(raw_priv).decode().rstrip("="),
        "kid": device_id,
    })


def _sign(card: dict, keypair: SigningKeypair, device_id: str) -> str:
    return jws.serialize_compact(
        {"alg": CARD_SIGNING_ALG, "kid": device_id},
        canonical_payload(card),
        _signing_jwk(keypair, device_id),
        algorithms=[CARD_SIGNING_ALG],
    )


async def _canonical_card(agent_id: str) -> dict:
    async with session_factory()() as session:
        agent = await session.get(Agent, agent_id)
        assert agent is not None
        return build_agent_card(agent, get_settings().public_base_url)


async def test_unsigned_card_is_never_verified(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    body = (await api_client.get(f"/v1/a2a/agents/{reg['agent_id']}/card")).json()
    assert body["agora"]["card_signature"] == "unsigned"
    assert "signatures" not in body["card"] or not body["card"].get("signatures")


async def test_signed_card_verifies(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    card = await _canonical_card(reg["agent_id"])
    signature = _sign(card, keypair, reg["device_id"])
    upload = await api_client.post(
        "/v1/agents/me/card-signature",
        json={"signature_jws": signature},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert upload.status_code == 200
    body = (await api_client.get(f"/v1/a2a/agents/{reg['agent_id']}/card")).json()
    assert body["agora"]["card_signature"] == "verified"
    assert body["card"]["signatures"]


async def test_signature_from_other_key_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    card = await _canonical_card(reg["agent_id"])
    attacker = SigningKeypair()
    bogus = _sign(card, attacker, reg["device_id"])
    r = await api_client.post(
        "/v1/agents/me/card-signature",
        json={"signature_jws": bogus},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 422


async def test_tampered_card_fails_verification(api_client, keypair, unique_name):
    """A signature valid for card A must not validate card B: if stored state
    no longer matches the canonical card, the registry refuses to serve it."""
    reg = await register_agent(api_client, keypair, unique_name)
    card = await _canonical_card(reg["agent_id"])
    signature = _sign(card, keypair, reg["device_id"])
    await api_client.post(
        "/v1/agents/me/card-signature",
        json={"signature_jws": signature},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    # Tamper with the agent so the canonical card no longer matches.
    async with session_factory()() as session:
        agent = await session.get(Agent, reg["agent_id"])
        agent.name = f"{unique_name}-TAMPERED"
        await session.commit()
    r = await api_client.get(f"/v1/a2a/agents/{reg['agent_id']}/card")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "card_signature_invalid"


async def test_tampered_signature_bytes_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    card = await _canonical_card(reg["agent_id"])
    signature = _sign(card, keypair, reg["device_id"])
    header, payload, sig = signature.split(".")
    flipped = sig[:-4] + ("AAAA" if not sig.endswith("AAAA") else "BBBB")
    r = await api_client.post(
        "/v1/agents/me/card-signature",
        json={"signature_jws": f"{header}.{payload}.{flipped}"},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 422


async def test_payload_swap_rejected(api_client, keypair, unique_name):
    """A correctly-signed JWS whose payload is NOT the canonical card is
    rejected — signing something else does not make a card valid."""
    reg = await register_agent(api_client, keypair, unique_name)
    forged = jws.serialize_compact(
        {"alg": CARD_SIGNING_ALG, "kid": reg["device_id"]},
        json.dumps({"name": "Totally Different"}).encode(),
        _signing_jwk(keypair, reg["device_id"]),
        algorithms=[CARD_SIGNING_ALG],
    )
    r = await api_client.post(
        "/v1/agents/me/card-signature",
        json={"signature_jws": forged},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert r.status_code == 422


async def test_revoked_device_signature_no_longer_verifies(api_client, keypair, unique_name):
    """Card trust follows device authority: revoking the signing device makes
    the card unverifiable rather than silently 'still fine'."""
    reg = await register_agent(api_client, keypair, unique_name)
    card = await _canonical_card(reg["agent_id"])
    signature = _sign(card, keypair, reg["device_id"])
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(
        "/v1/agents/me/card-signature", json={"signature_jws": signature}, headers=auth
    )
    assert (await api_client.get(f"/v1/a2a/agents/{reg['agent_id']}/card")).json()[
        "agora"]["card_signature"] == "verified"

    await api_client.post(f"/v1/devices/{reg['device_id']}/revoke", headers=auth)
    r = await api_client.get(f"/v1/a2a/agents/{reg['agent_id']}/card")
    assert r.status_code == 409
