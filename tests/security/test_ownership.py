"""Ownership, dev auth, CSRF and secure claim tests (S2-T02/03/04/05, T21)."""

import secrets
from datetime import timedelta

import pytest
from agora_api.db import session_factory
from agora_api.events import now_utc
from agora_api.models import ClaimChallenge
from sqlalchemy import update

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration


async def _login(api_client, username: str) -> dict:
    r = await api_client.post("/v1/auth/dev/login", json={"username": username})
    assert r.status_code == 200, r.text
    assert "agora_session" in r.cookies
    # cookie must be HttpOnly
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    return r.json()


def _claim_signature(keypair: SigningKeypair, agent_id: str, code: str) -> str:
    return keypair.sign_b64(f"agora.claim.v1|{agent_id}|{code}".encode())


async def _claim_flow(api_client, keypair, unique_name, username: str) -> tuple[dict, dict, str]:
    """login → register agent → request claim → device consumes claim."""
    login = await _login(api_client, username)
    reg = await register_agent(api_client, keypair, unique_name)
    claim = await api_client.post(
        "/v1/owner/claims",
        json={"agent_id": reg["agent_id"]},
        headers={"X-CSRF-Token": login["csrf_token"]},
    )
    assert claim.status_code == 201, claim.text
    code = claim.json()["claim_code"]
    consume = await api_client.post(
        "/v1/registration/claim",
        json={
            "agent_id": reg["agent_id"],
            "code": code,
            "device_id": reg["device_id"],
            "signature": _claim_signature(keypair, reg["agent_id"], code),
        },
    )
    assert consume.status_code == 200, consume.text
    return login, reg, code


async def test_full_claim_flow_and_replay_rejected(api_client, keypair, unique_name):
    login, reg, code = await _claim_flow(
        api_client, keypair, unique_name, f"owner-{secrets.token_hex(4)}"
    )
    # replaying the exact same consumed code fails (single-use)
    replay = await api_client.post(
        "/v1/registration/claim",
        json={
            "agent_id": reg["agent_id"],
            "code": code,
            "device_id": reg["device_id"],
            "signature": _claim_signature(keypair, reg["agent_id"], code),
        },
    )
    assert replay.status_code in (401, 409)
    # my-agents shows the claimed agent
    mine = await api_client.get("/v1/owner/agents")
    assert reg["agent_id"] in [a["agent_id"] for a in mine.json()["agents"]]


async def test_agent_id_alone_cannot_claim(api_client, keypair, unique_name):
    """SEC-005: without a valid code + device signature, no ownership."""
    await _login(api_client, f"thief-{secrets.token_hex(4)}")
    reg = await register_agent(api_client, keypair, unique_name)
    bogus = await api_client.post(
        "/v1/registration/claim",
        json={
            "agent_id": reg["agent_id"],
            "code": "guessed-code",
            "device_id": reg["device_id"],
            "signature": _claim_signature(keypair, reg["agent_id"], "guessed-code"),
        },
    )
    assert bogus.status_code == 401


async def test_claim_requires_device_signature(api_client, keypair, unique_name):
    login = await _login(api_client, f"owner-{secrets.token_hex(4)}")
    reg = await register_agent(api_client, keypair, unique_name)
    claim = await api_client.post(
        "/v1/owner/claims",
        json={"agent_id": reg["agent_id"]},
        headers={"X-CSRF-Token": login["csrf_token"]},
    )
    code = claim.json()["claim_code"]
    attacker = SigningKeypair()  # does not hold the device key
    r = await api_client.post(
        "/v1/registration/claim",
        json={
            "agent_id": reg["agent_id"],
            "code": code,
            "device_id": reg["device_id"],
            "signature": attacker.sign_b64(f"agora.claim.v1|{reg['agent_id']}|{code}".encode()),
        },
    )
    assert r.status_code == 401


async def test_claim_expiry(api_client, keypair, unique_name):
    login = await _login(api_client, f"owner-{secrets.token_hex(4)}")
    reg = await register_agent(api_client, keypair, unique_name)
    claim = await api_client.post(
        "/v1/owner/claims",
        json={"agent_id": reg["agent_id"]},
        headers={"X-CSRF-Token": login["csrf_token"]},
    )
    code = claim.json()["claim_code"]
    async with session_factory()() as session:
        await session.execute(
            update(ClaimChallenge)
            .where(ClaimChallenge.agent_id == reg["agent_id"])
            .values(expires_at=now_utc() - timedelta(seconds=1))
        )
        await session.commit()
    r = await api_client.post(
        "/v1/registration/claim",
        json={
            "agent_id": reg["agent_id"],
            "code": code,
            "device_id": reg["device_id"],
            "signature": _claim_signature(keypair, reg["agent_id"], code),
        },
    )
    assert r.status_code == 401


async def test_cross_owner_claim_blocked(api_client, keypair, unique_name):
    """An owned agent cannot be re-claimed by anyone (ownership never moves
    implicitly)."""
    _, reg, _ = await _claim_flow(api_client, keypair, unique_name, f"o1-{secrets.token_hex(4)}")
    login2 = await _login(api_client, f"o2-{secrets.token_hex(4)}")
    second = await api_client.post(
        "/v1/owner/claims",
        json={"agent_id": reg["agent_id"]},
        headers={"X-CSRF-Token": login2["csrf_token"]},
    )
    assert second.status_code == 409


async def test_csrf_required_for_state_changes(api_client, keypair, unique_name):
    """SEC-012: cookie alone is not enough for mutations."""
    await _login(api_client, f"owner-{secrets.token_hex(4)}")
    reg = await register_agent(api_client, keypair, unique_name)
    no_csrf = await api_client.post("/v1/owner/claims", json={"agent_id": reg["agent_id"]})
    assert no_csrf.status_code == 403
    assert no_csrf.json()["error"]["code"] == "csrf_rejected"
    wrong = await api_client.post(
        "/v1/owner/claims",
        json={"agent_id": reg["agent_id"]},
        headers={"X-CSRF-Token": "f" * 64},
    )
    assert wrong.status_code == 403


async def test_owner_revoke_and_cross_owner_denied(api_client, unique_name):
    """SEC-004: Owner A cannot revoke Owner B's devices."""
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    login_a, reg_a, _ = await _claim_flow(
        api_client, kp_a, f"{unique_name}-A", f"oa-{secrets.token_hex(4)}"
    )
    login_b, reg_b, _ = await _claim_flow(
        api_client, kp_b, f"{unique_name}-B", f"ob-{secrets.token_hex(4)}"
    )
    # B (logged in last, holds the cookie) cannot revoke A's device
    cross = await api_client.post(
        f"/v1/owner/devices/{reg_a['device_id']}/revoke",
        headers={"X-CSRF-Token": login_b["csrf_token"]},
    )
    assert cross.status_code == 403
    assert cross.json()["error"]["code"] == "owner_authority_required"
    # B revokes its own device successfully
    own = await api_client.post(
        f"/v1/owner/devices/{reg_b['device_id']}/revoke",
        headers={"X-CSRF-Token": login_b["csrf_token"]},
    )
    assert own.status_code == 200
    assert own.json()["status"] == "revoked"


async def test_dev_login_fails_closed_in_production(api_client, monkeypatch):
    """SEC-011: with production settings, dev auth is unavailable."""
    from agora_api import owners
    from agora_api.config import Settings

    monkeypatch.setattr(owners, "get_settings", lambda: Settings(env="production"))
    r = await api_client.post("/v1/auth/dev/login", json={"username": "prod-attacker"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "auth_provider_unavailable"