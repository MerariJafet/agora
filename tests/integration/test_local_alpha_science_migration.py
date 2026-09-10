"""0038 roundtrip on a fresh wrapper-owned isolated database only."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from agora_api.db import session_factory
from sqlalchemy import text

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


async def test_empty_database_provider_migration_roundtrip():
    assert os.environ.get("AGORA_ENV") == "test"
    assert "agora_test_" in os.environ.get("AGORA_DATABASE_URL", "")
    destination = ROOT / "audit/local-alpha-v02/science" / os.environ["AGORA_RUN_ID"]
    destination.mkdir(parents=True, exist_ok=True)
    async with session_factory()() as session:
        count = await session.scalar(text("SELECT count(*) FROM institutional_validators"))
        assert count == 0, "Use a fresh isolated wrapper invocation for migration roundtrip"
    results = []
    for command, expected_size in (("downgrade", 16), ("upgrade", 32)):
        target = (
            "0037_a2a_delivery_contract" if command == "downgrade" else "0038_python_test_reviewer"
        )
        process = subprocess.run(
            [str(ROOT / ".venv/bin/alembic"), "-c", "apps/api/alembic.ini", command, target],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        entry = {
            "command": command,
            "target": target,
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        results.append(entry)
        destination.joinpath("migration-roundtrip.json").write_text(json.dumps(results, indent=2))
        assert process.returncode == 0, process.stderr
        async with session_factory()() as session:
            size = await session.scalar(
                text(
                    "SELECT character_maximum_length FROM information_schema.columns "
                    "WHERE table_name='institutional_validators' AND column_name='brain_provider'"
                )
            )
            definition = await session.scalar(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conname='ck_pilot_validator_brain_provider'"
                )
            )
            version = await session.scalar(text("SELECT version_num FROM alembic_version"))
        assert size == expected_size
        assert version == target
        assert "codex" in definition and "claude" in definition
        assert ("python-scripted-test" in definition) == (command == "upgrade")
        entry.update({"verified_size": size, "verified_check": definition, "version": version})
        destination.joinpath("migration-roundtrip.json").write_text(json.dumps(results, indent=2))
