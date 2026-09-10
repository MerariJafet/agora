"""Own a fresh PostgreSQL database, Redis/NATS containers and artifacts for one smoke.

Uses existing local PostgreSQL container only to create/drop its unique test database.
Never flushes shared Redis, uses live data, pulls images, or contacts a model provider.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from load_harness import REPO, free_port


def command(args, **kwargs):
    result = subprocess.run(args, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError("isolated setup command failed: " + Path(args[0]).name)
    return result


def main():
    run_id = "load_" + secrets.token_hex(8)
    database = "agora_test_" + run_id
    pg = "agora-dev-postgres-1"
    temporary = Path(tempfile.mkdtemp(prefix="agora-load-private-"))
    temporary.chmod(0o700)
    artifacts = temporary / "artifacts"
    artifacts.mkdir(mode=0o700)
    (artifacts / ".harness-owner").write_text(run_id)
    containers = []
    database_created = False
    output = Path(
        os.environ.get("HARNESS_OUTPUT", str(REPO / "audit" / "load-smoke" / f"{run_id}.json"))
    ).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    status = 1
    try:
        # Image inspection is read-only; missing images fail instead of pulling implicitly.
        for image in ["redis:7-alpine", "nats:2.10-alpine"]:
            command(["docker", "image", "inspect", image])
        command(["docker", "exec", pg, "createdb", "-U", "agora", "-O", "agora", database])
        database_created = True
        ports = []
        for role, image, internal in [
            ("redis", "redis:7-alpine", 6379),
            ("nats", "nats:2.10-alpine", 4222),
        ]:
            port = free_port()
            while port in ports or port in {6380, 4222}:
                port = free_port()
            ports.append(port)
            name = f"agora-{run_id}-{role}"
            command(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    name,
                    "--label",
                    f"agora.harness={run_id}",
                    "-p",
                    f"127.0.0.1:{port}:{internal}",
                    image,
                ]
            )
            containers.append(name)
        env = {k: v for k, v in os.environ.items() if not k.startswith("AGORA_")}
        env.update(
            {
                "AGORA_ENV": "test",
                "AGORA_RUN_ID": run_id,
                "AGORA_ENVIRONMENT_ID": run_id,
                "AGORA_PROVENANCE_CLASS": "test",
                "AGORA_TEST_WORLD_INSTANCE_ID": run_id,
                "AGORA_WORLD_INSTANCE_ID": "agora-local-real",
                "AGORA_DATABASE_URL": f"postgresql+asyncpg://agora:agora_dev_password@127.0.0.1:5434/{database}",
                "AGORA_REDIS_URL": f"redis://127.0.0.1:{ports[0]}/0",
                "AGORA_NATS_URL": f"nats://127.0.0.1:{ports[1]}",
                "AGORA_OUTBOX_ENABLED": "false",
                "AGORA_RESEARCH_SCHEDULER_ENABLED": "false",
                "AGORA_ARTIFACT_STORE_ROOT": str(artifacts),
                "HARNESS_OUTPUT": str(output),
                "AGORA_PUBLIC_OPEN_WORLD": "false",
                "AGORA_TOKOIN_LOCAL_CONTROL_PLANE_ENABLED": "false",
                "AGORA_INSTITUTIONAL_REGISTRY_CONTROL_PLANE_ENABLED": "false",
                "AGORA_INSTITUTIONAL_VALIDATOR_PILOT_ENABLED": "false",
            }
        )
        command(
            [sys.executable, "-m", "alembic", "-c", "apps/api/alembic.ini", "upgrade", "head"],
            cwd=REPO,
            env=env,
        )
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts/load_harness.py")], cwd=REPO, env=env
        )
        status = result.returncode
    finally:
        errors = []
        for name in reversed(containers):
            try:
                command(["docker", "rm", "-f", name])
            except RuntimeError:
                errors.append("owned_container_cleanup_failed")
        if database_created:
            try:
                command(["docker", "exec", pg, "dropdb", "-U", "agora", database])
            except RuntimeError:
                errors.append("owned_database_cleanup_failed")
        shutil.rmtree(temporary)
        print(
            json.dumps(
                {"isolation_cleanup_ok": not errors, "errors": errors, "result_path": str(output)}
            ),
            flush=True,
        )
        if errors:
            status = 1
    return status


if __name__ == "__main__":
    raise SystemExit(main())
