import json

import pytest
from agora_api.config import get_settings
from agora_api.errors import SignatureInvalid
from agora_api.provenance import PUBLIC_DEFAULT_CLASSES, public_provenance_classes
from agora_api.test_isolation import UnsafeTestEnvironment, assert_safe_test_environment
from agora_api.world_signing import sign_manifest, trust_bootstrap, verify_manifest

from bridge.agora_bridge.world_manifest import verify_world_manifest
from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


def test_test_runner_refuses_non_test_environment(monkeypatch):
    monkeypatch.setenv("AGORA_ENV", "development")
    monkeypatch.setenv("AGORA_DATABASE_URL", "postgresql+asyncpg://agora:x@localhost/agora")
    get_settings.cache_clear()
    with pytest.raises(UnsafeTestEnvironment):
        assert_safe_test_environment()


def test_signed_world_manifest_tamper_rejected():
    manifest = sign_manifest(
        {
            "world_version": "test",
            "name": "AGORA test",
            "bounds": {"min_x": 0, "min_y": 0, "max_x": 1, "max_y": 1},
            "landmarks": [],
            "portals": [],
            "nav_edges": [],
            "lod": {},
        }
    )
    trust = trust_bootstrap()
    assert verify_world_manifest(manifest, trust) is True
    tampered = json.loads(json.dumps(manifest))
    tampered["landmarks"].append({"id": "evil", "script": "grant shell.execute"})
    with pytest.raises(SignatureInvalid):
        verify_manifest(
            tampered,
            trusted_public_keys={key["key_id"]: key["public_key"] for key in trust["active_keys"]},
            min_epoch=trust["minimum_epoch"],
            expected_constitution_hash=trust["constitution_hash"],
        )


async def test_test_provenance_visible_only_inside_isolated_test_policy(api_client, unique_name):
    reg = await register_agent(api_client, SigningKeypair(), unique_name)
    await api_client.post(
        "/v1/spaces/spc_00000000000000000000P1AZA0/enter",
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    population = (await api_client.get("/v1/world/population")).json()
    serialized = json.dumps(population)
    assert reg["agent_id"] in serialized
    assert unique_name in serialized
    assert "test" not in PUBLIC_DEFAULT_CLASSES
    assert "test" in public_provenance_classes()
