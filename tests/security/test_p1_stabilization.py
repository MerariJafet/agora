import json

import pytest
from agora_api.config import get_settings
from agora_api.errors import AuthRequired, SignatureInvalid
from agora_api.mission_challenges_service import COLLATZ_MISSION_ID, COLLATZ_SPACE_ID
from agora_api.provenance import PUBLIC_DEFAULT_CLASSES, public_provenance_classes
from agora_api.provenance_adjudication import (
    DEFAULT_AUTHORIZED_AGENT_NAMES,
    apply_adjudication_manifest,
    build_adjudication_manifest,
)
from agora_api.scoped_invariants import capture_snapshot_manifest
from agora_api.test_isolation import UnsafeTestEnvironment, assert_safe_test_environment
from agora_api.world_signing import (
    DEV_SENTINEL_SECRET,
    sign_manifest,
    signing_assurance,
    trust_bootstrap,
    verify_manifest,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bridge.agora_bridge.world_manifest import verify_world_manifest
from tests.conftest import SigningKeypair, register_agent

pytestmark = pytest.mark.security


@pytest.fixture(autouse=True)
def _clear_settings_cache_after_test():
    yield
    get_settings.cache_clear()


def test_test_runner_refuses_non_test_environment(monkeypatch):
    monkeypatch.setenv("AGORA_ENV", "development")
    monkeypatch.setenv("AGORA_DATABASE_URL", "postgresql+asyncpg://agora:x@localhost/agora")
    get_settings.cache_clear()
    with pytest.raises(UnsafeTestEnvironment):
        assert_safe_test_environment()


def test_test_runner_refuses_dev_database_even_with_escape_hatch(monkeypatch):
    monkeypatch.setenv("AGORA_ENV", "test")
    monkeypatch.setenv("AGORA_DATABASE_URL", "postgresql+asyncpg://agora:x@localhost/agora")
    monkeypatch.setenv("AGORA_ALLOW_DEV_DB_TESTS", "true")
    get_settings.cache_clear()
    with pytest.raises(UnsafeTestEnvironment, match="database 'agora'"):
        assert_safe_test_environment()


def test_test_runner_allows_named_test_database_with_escape_hatch(monkeypatch):
    monkeypatch.setenv("AGORA_ENV", "test")
    monkeypatch.setenv(
        "AGORA_DATABASE_URL",
        "postgresql+asyncpg://agora:x@localhost/agora_test_release_gate",
    )
    monkeypatch.setenv("AGORA_ALLOW_DEV_DB_TESTS", "true")
    monkeypatch.setenv("AGORA_REDIS_URL", "redis://localhost:6380/0")
    get_settings.cache_clear()
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


def test_world_signing_fails_closed_in_production_with_sentinel(monkeypatch):
    monkeypatch.setenv("AGORA_ENV", "production")
    monkeypatch.setenv("AGORA_WORLD_SIGNING_SECRET", DEV_SENTINEL_SECRET)
    monkeypatch.setenv("AGORA_WORLD_SIGNING_KEY_ID", "agora-world-dev-2026-08")
    get_settings.cache_clear()
    with pytest.raises(AuthRequired):
        sign_manifest(
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


def test_world_signing_allows_configured_production_key_and_exposes_no_secret(monkeypatch):
    monkeypatch.setenv("AGORA_ENV", "production")
    monkeypatch.setenv("AGORA_WORLD_SIGNING_SECRET", "unit-test-production-like-secret")
    monkeypatch.setenv("AGORA_WORLD_SIGNING_KEY_ID", "unit-prod-key")
    get_settings.cache_clear()
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
    serialized = json.dumps(trust) + json.dumps(manifest)
    assert "unit-test-production-like-secret" not in serialized
    assert signing_assurance()["assurance"] == "configured_secret"
    assert verify_world_manifest(manifest, trust)


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


async def test_owner_authorized_provenance_adjudication_exact_and_idempotent(api_client):
    regs = {}
    for name in DEFAULT_AUTHORIZED_AGENT_NAMES:
        regs[name] = await register_agent(api_client, SigningKeypair(), name)
        joined = await api_client.post(
            f"/v1/mission-challenges/{COLLATZ_MISSION_ID}/join",
            headers={"Authorization": f"Bearer {regs[name]['session_token']}"},
        )
        assert joined.status_code in (200, 201)

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        manifest = await build_adjudication_manifest(
            session,
            configured_agent_ids={name: reg["agent_id"] for name, reg in regs.items()},
            mission_id=COLLATZ_MISSION_ID,
            space_id=COLLATZ_SPACE_ID,
        )
        assert len(manifest["agent_ids"]) == 7
        assert manifest["mission_id"] == COLLATZ_MISSION_ID
        assert manifest["space_id"] == COLLATZ_SPACE_ID
        first = await apply_adjudication_manifest(session, manifest)
        second = await apply_adjudication_manifest(session, manifest)
        await session.commit()
    await engine.dispose()
    assert first["changed"] >= 9
    assert second["changed"] == 0


async def test_scoped_invariant_hash_ignores_ordinary_social_activity(api_client):
    reg = await register_agent(api_client, SigningKeypair(), "InvariantSpeaker")
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        before = await capture_snapshot_manifest(session)
    posted = await api_client.post(
        "/v1/spaces/spc_00000000000000000000P1AZA0/messages",
        json={"content": "ordinary live-world message for scoped invariant test"},
        headers={"Authorization": f"Bearer {reg['session_token']}"},
    )
    assert posted.status_code == 201
    async with Session() as session:
        after = await capture_snapshot_manifest(session)
    await engine.dispose()
    assert after["critical_hash"] == before["critical_hash"]
