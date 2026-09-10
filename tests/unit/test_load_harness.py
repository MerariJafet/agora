"""Benchmark must fail closed before opening live resources or counting errors."""

import importlib.util
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("load_harness", ROOT / "scripts/load_harness.py")
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)


def isolated_env(tmp_path):
    run = "load_0123456789abcdef"
    (tmp_path / ".harness-owner").write_text(run)
    return {
        "AGORA_RUN_ID": run,
        "AGORA_ENV": "test",
        "AGORA_PROVENANCE_CLASS": "test",
        "AGORA_ENVIRONMENT_ID": run,
        "AGORA_TEST_WORLD_INSTANCE_ID": run,
        "AGORA_OUTBOX_ENABLED": "false",
        "AGORA_RESEARCH_SCHEDULER_ENABLED": "false",
        "AGORA_DATABASE_URL": f"postgresql://127.0.0.1:5434/agora_test_{run}",
        "AGORA_REDIS_URL": "redis://127.0.0.1:19801/0",
        "AGORA_NATS_URL": "nats://127.0.0.1:19802",
        "AGORA_ARTIFACT_STORE_ROOT": str(tmp_path),
    }


def test_owned_isolation_is_accepted(tmp_path):
    harness.require_isolation(isolated_env(tmp_path))


@pytest.mark.parametrize(
    "key,value",
    [
        ("AGORA_DATABASE_URL", "postgresql://127.0.0.1:5434/agora"),
        ("AGORA_DATABASE_URL", "postgresql://remote.example/agora_test_load_0123456789abcdef"),
        ("AGORA_REDIS_URL", "redis://127.0.0.1:6380/15"),
        ("AGORA_NATS_URL", "nats://127.0.0.1:4222"),
        ("AGORA_PROVENANCE_CLASS", "real"),
        ("AGORA_ENV", "production"),
        ("AGORA_OUTBOX_ENABLED", "true"),
        ("AGORA_RESEARCH_SCHEDULER_ENABLED", "true"),
        ("AGORA_RUN_ID", "manual"),
        ("AGORA_ARTIFACT_STORE_ROOT", "/nonexistent"),
    ],
)
def test_live_or_unowned_configuration_rejected(tmp_path, key, value):
    env = isolated_env(tmp_path)
    env[key] = value
    with pytest.raises(ValueError):
        harness.require_isolation(env)


@pytest.mark.parametrize(
    "status,body",
    [
        (403, {"detail": "denied"}),
        (500, {}),
        (200, {"error": {"code": -1}}),
        (200, {"jsonrpc": "2.0"}),
    ],
)
def test_rejected_operations_cannot_be_success_latencies(status, body):
    with pytest.raises(ValueError):
        harness.checked(httpx.Response(status, json=body), rpc=True)


def test_valid_rpc_and_empty_percentiles():
    assert harness.checked(httpx.Response(200, json={"jsonrpc": "2.0", "result": {}}), rpc=True)
    assert harness.percentile([], 0.95) is None
    assert harness.percentile([1, 2, 3, 4, 5], 0.95) == 5
