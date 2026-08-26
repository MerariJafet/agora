"""Versioned local runtime sync for owner-operated AGORA agents.

Only runtime-managed files are installed. Agent-owned state is intentionally
outside this manifest: identity keys, config.json, manifest.json, AGENT.md,
memory.md, .env and audit logs are never read as source material nor written.
"""
# ruff: noqa: S603,S607

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agora_bridge.local_runtime_driver import RUNTIME_MANAGED_MARKER, RUNTIME_VERSION

RUNTIME_WRAPPER = """#!/usr/bin/env python3
# AGORA_RUNTIME_MANAGED_V1
from agora_bridge.local_runtime_driver import main

if __name__ == "__main__":
    raise SystemExit(main())
"""

OWNED_FILENAMES = {
    ".env",
    ".soul",
    "AGENT.md",
    "audit.log",
    "config.json",
    "daemon.log",
    "manifest.json",
    "memory.md",
    "state.json",
}

MANAGED_FILENAMES = {
    "runtime_driver.py",
    ".agora-runtime-version.json",
}


class RuntimeSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeArtifact:
    relative_path: str
    content: bytes
    mode: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def _runtime_commit(repo_root: Path) -> str:
    try:
        import subprocess

        return subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "--short=12", "HEAD"],
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001 - sync still works outside a git checkout
        return "unknown"


def expected_artifacts(repo_root: Path) -> list[RuntimeArtifact]:
    wrapper = RuntimeArtifact("runtime_driver.py", RUNTIME_WRAPPER.encode(), 0o700)
    marker = {
        "schema_version": "1.0",
        "marker": RUNTIME_MANAGED_MARKER,
        "runtime_version": RUNTIME_VERSION,
        "runtime_commit": _runtime_commit(repo_root),
        "runtime_driver_sha256": wrapper.sha256,
    }
    return [
        wrapper,
        RuntimeArtifact(
            ".agora-runtime-version.json",
            (json.dumps(marker, indent=2, sort_keys=True) + "\n").encode(),
            0o600,
        ),
    ]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def _owned_state_hashes(agent_home: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in sorted(OWNED_FILENAMES):
        path = agent_home / name
        if path.is_file():
            hashes[name] = file_sha256(path)
    return hashes


def _read_existing_marker(agent_home: Path) -> dict | None:
    marker_path = agent_home / ".agora-runtime-version.json"
    if not marker_path.exists():
        return None
    try:
        data = json.loads(marker_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeSyncError(f"invalid runtime marker in {agent_home}: {exc}") from exc
    if data.get("marker") != RUNTIME_MANAGED_MARKER:
        raise RuntimeSyncError(f"unrecognized runtime marker in {agent_home}")
    return data


def _write_atomic(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def dry_run(agent_home: Path, repo_root: Path) -> dict:
    artifacts = expected_artifacts(repo_root)
    changes = []
    for artifact in artifacts:
        target = agent_home / artifact.relative_path
        current = file_sha256(target) if target.exists() else None
        changes.append(
            {
                "path": str(target),
                "exists": target.exists(),
                "current_sha256": current,
                "expected_sha256": artifact.sha256,
                "would_change": current != artifact.sha256,
            }
        )
    return {
        "agent_home": str(agent_home),
        "runtime_version": RUNTIME_VERSION,
        "runtime_commit": _runtime_commit(repo_root),
        "changes": changes,
        "agent_owned_files_present": sorted(_owned_state_hashes(agent_home)),
    }


def sync_agent_home(agent_home: Path, repo_root: Path) -> dict:
    if not agent_home.exists():
        agent_home.mkdir(parents=True, mode=0o700)
    before_owned = _owned_state_hashes(agent_home)
    backup_dir = agent_home / ".agora-runtime-backup"
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    for name in MANAGED_FILENAMES:
        current = agent_home / name
        if current.exists():
            shutil.copy2(current, backup_dir / name)
    for artifact in expected_artifacts(repo_root):
        _write_atomic(agent_home / artifact.relative_path, artifact.content, artifact.mode)
    after_owned = _owned_state_hashes(agent_home)
    if before_owned != after_owned:
        raise RuntimeSyncError("agent-owned state changed during runtime sync")
    marker = _read_existing_marker(agent_home)
    wrapper_hash = file_sha256(agent_home / "runtime_driver.py")
    if marker is None or marker.get("runtime_driver_sha256") != wrapper_hash:
        raise RuntimeSyncError("runtime checksum mismatch after sync")
    return {
        "agent_home": str(agent_home),
        "runtime_version": marker["runtime_version"],
        "runtime_commit": marker["runtime_commit"],
        "runtime_driver_sha256": wrapper_hash,
        "agent_owned_state_changed": False,
    }


def rollback_agent_home(agent_home: Path) -> dict:
    backup_dir = agent_home / ".agora-runtime-backup"
    if not backup_dir.exists():
        raise RuntimeSyncError("no runtime backup exists")
    before_owned = _owned_state_hashes(agent_home)
    restored: list[str] = []
    for name in MANAGED_FILENAMES:
        source = backup_dir / name
        target = agent_home / name
        if source.exists():
            shutil.copy2(source, target)
            restored.append(name)
        else:
            target.unlink(missing_ok=True)
            restored.append(f"{name}:removed")
    if before_owned != _owned_state_hashes(agent_home):
        raise RuntimeSyncError("agent-owned state changed during rollback")
    return {"agent_home": str(agent_home), "restored": restored}


def agent_runtime_status(agent_home: Path) -> dict:
    marker = _read_existing_marker(agent_home)
    wrapper_path = agent_home / "runtime_driver.py"
    return {
        "agent_home": str(agent_home),
        "marker": marker,
        "runtime_driver_sha256": file_sha256(wrapper_path) if wrapper_path.exists() else None,
        "owned_state_hashes": _owned_state_hashes(agent_home),
    }


def _agent_homes_from_args(paths: list[str], base: Path) -> list[Path]:
    if paths:
        return [Path(p).expanduser().resolve() for p in paths]
    return sorted(
        p for p in base.iterdir()
        if p.is_dir() and (p / "manifest.json").exists() and (p / "config.json").exists()
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync canonical AGORA runtime wrappers.")
    parser.add_argument("agent_homes", nargs="*")
    parser.add_argument("--repo-root", default="/home/merari-acero/agora")
    parser.add_argument("--base", default="/home/merari-acero/.agora-agents")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).expanduser().resolve()
    homes = _agent_homes_from_args(args.agent_homes, Path(args.base).expanduser().resolve())
    rows = []
    for home in homes:
        if args.rollback:
            rows.append(rollback_agent_home(home))
        elif args.dry_run:
            rows.append(dry_run(home, repo_root))
        else:
            rows.append(sync_agent_home(home, repo_root))
    print(json.dumps({"count": len(rows), "results": rows}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
