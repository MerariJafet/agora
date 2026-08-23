"""Avatar/activity/world security (S3-T22).

Core claim: nothing in the visual layer can become code, cross agents, or
touch local permissions.
"""

import pytest
from agora_api.avatars import PALETTE, default_avatar, validate_avatar
from agora_api.errors import ValidationFailed
from agora_bridge.config import BridgeConfig
from agora_bridge.policy import LocalPermission, LocalPolicyEngine

from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.integration

PLAZA = "spc_00000000000000000000P1AZA0"

HOSTILE_AVATARS = [
    {"schema_version": "1.0", "body": "<script>alert(1)</script>", "visor": "round",
     "antenna": "none", "accessory": "none", "emblem": "none",
     "expression": "neutral", "tint": "#4ac48a"},
    {"schema_version": "1.0", "body": "orb", "visor": "round", "antenna": "none",
     "accessory": "none", "emblem": "none", "expression": "neutral",
     "tint": "javascript:alert(1)"},
    {"schema_version": "1.0", "body": "orb", "visor": "round", "antenna": "none",
     "accessory": "none", "emblem": "none", "expression": "neutral",
     "tint": "#4ac48a", "svg": "<svg onload=alert(1)>"},
    {"schema_version": "1.0", "body": "orb", "visor": "round", "antenna": "none",
     "accessory": "none", "emblem": "none", "expression": "neutral",
     "tint": "#4ac48a", "granted_permissions": ["shell.execute"]},
    {"schema_version": "1.0", "body": "orb", "visor": "round", "antenna": "none",
     "accessory": "none", "emblem": "none", "expression": "neutral",
     "tint": "#4ac48a", "image_url": "https://evil.example/x.png"},
]


def test_hostile_avatar_specs_rejected():
    for spec in HOSTILE_AVATARS:
        with pytest.raises(ValidationFailed):
            validate_avatar(spec)


def test_avatar_grammar_has_no_executable_surface():
    """Every value in a validated AvatarSpec is an enum member or a hex color:
    there is no field a payload could hide markup in."""
    spec = validate_avatar(default_avatar("agt_" + "1" * 26))
    for key, value in spec.items():
        assert isinstance(value, str)
        assert "<" not in value and "javascript:" not in value.lower()
        if key in ("tint", "accent"):
            assert value in PALETTE  # snapped to the accessible palette


def test_default_avatar_is_deterministic():
    a = default_avatar("agt_" + "7" * 26)
    b = default_avatar("agt_" + "7" * 26)
    c = default_avatar("agt_" + "8" * 26)
    assert a == b
    assert a != c


def test_avatar_fields_cannot_influence_local_policy():
    """SEC: visual data is inert. Even a spec stuffed with permission-shaped
    keys leaves the LocalPolicyEngine at default-deny."""
    engine = LocalPolicyEngine(BridgeConfig())
    for spec in HOSTILE_AVATARS:
        assert LocalPolicyEngine.grants_from_remote_payload({"avatar": spec}) == []
    for perm in LocalPermission:
        assert not engine.decide(perm).allowed


async def test_agent_can_only_change_its_own_avatar(api_client, unique_name):
    """There is no route accepting a target agent_id: identity comes from the
    session, so cross-agent writes are structurally impossible."""
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")

    spec = default_avatar("chosen") | {"tint": "#e0596a"}
    r = await api_client.post(
        "/v1/agents/me/avatar",
        json={"avatar": spec, "agent_id": b["agent_id"]},  # hostile hint ignored
        headers={"Authorization": f"Bearer {a['session_token']}"},
    )
    assert r.status_code == 200
    assert r.json()["agent_id"] == a["agent_id"]  # never B

    b_state = (await api_client.get(f"/v1/world/agents/{b['agent_id']}/state")).json()
    assert b_state["avatar"] == default_avatar(b["agent_id"])  # untouched


async def test_agent_can_only_change_its_own_activity(api_client, unique_name):
    kp_a, kp_b = SigningKeypair(), SigningKeypair()
    a = await register_agent(api_client, kp_a, f"{unique_name}-A")
    b = await register_agent(api_client, kp_b, f"{unique_name}-B")
    r = await api_client.post(
        "/v1/agents/me/activity",
        json={"activity": "researching", "agent_id": b["agent_id"]},
        headers={"Authorization": f"Bearer {a['session_token']}"},
    )
    assert r.status_code == 200 and r.json()["agent_id"] == a["agent_id"]
    b_state = (await api_client.get(f"/v1/world/agents/{b['agent_id']}/state")).json()
    assert b_state["activity"] == "idle"


async def test_invalid_activity_rejected(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    for bad in ["<script>", "rm -rf /", "shell.execute", "", "IDLE"]:
        r = await api_client.post(
            "/v1/agents/me/activity",
            json={"activity": bad},
            headers={"Authorization": f"Bearer {reg['session_token']}"},
        )
        assert r.status_code == 422


async def test_unauthenticated_world_writes_rejected(api_client):
    assert (await api_client.post("/v1/agents/me/activity",
                                  json={"activity": "idle"})).status_code == 401
    assert (await api_client.post("/v1/agents/me/avatar",
                                  json={"avatar": default_avatar("x")})).status_code == 401


async def test_revoked_device_cannot_change_world_state(api_client, keypair, unique_name):
    reg = await register_agent(api_client, keypair, unique_name)
    auth = {"Authorization": f"Bearer {reg['session_token']}"}
    await api_client.post(f"/v1/devices/{reg['device_id']}/revoke", headers=auth)
    assert (await api_client.post("/v1/agents/me/activity",
                                  json={"activity": "building"}, headers=auth)).status_code == 403


async def test_world_manifest_contains_no_executable_payload(api_client):
    """The manifest is pure data: no code, no URLs to fetch and execute."""
    import json

    manifest = (await api_client.get("/v1/world/manifest")).json()
    serialized = json.dumps(manifest).lower()
    for forbidden in ("<script", "javascript:", "eval(", "function(", "http://", "https://"):
        assert forbidden not in serialized
    assert manifest["world_version"]
    states = {lm["state"] for lm in manifest["landmarks"]}
    assert states <= {"ACTIVE", "COMING_SOON", "LOCKED"}
