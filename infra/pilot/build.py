# ruff: noqa: S603, S607
# Subprocess argv is constructed locally; no shell or remote input is evaluated.
"""Build from an allowlisted ephemeral context, including on legacy Docker builders."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def stage(destination, target="api"):
    web = target == "web"
    files = [] if web else [ROOT / "requirements.txt"]
    suffixes = (
        {".ts", ".tsx", ".js", ".mjs", ".json", ".css", ".svg", ".png", ".ico", ".woff2"}
        if web
        else {".py", ".json", ".toml", ".ini", ".mako"}
    )
    directories = (
        ["apps/web", "packages/sdk-typescript"]
        if web
        else ["apps/api", "bridge", "packages/protocol"]
    )
    for directory in directories:
        for source in (ROOT / directory).rglob("*"):
            if (
                source.is_file()
                and source.suffix in suffixes
                and not any(
                    part.startswith(".") or part in {"__pycache__", "node_modules"}
                    for part in source.relative_to(ROOT).parts
                )
            ):
                files.append(source)
    files.extend(
        ROOT / "infra/pilot" / name
        for name in (
            ["Dockerfile.web"]
            if web
            else [
                "Dockerfile",
                "readiness.py",
                "assert-production.py",
            ]
        )
    )
    for source in files:
        if source.is_symlink():
            raise ValueError("symlinks are not allowed in build context")
        target = destination / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    digest = hashlib.sha256()
    for source in sorted(files):
        digest.update(str(source.relative_to(ROOT)).encode() + b"\0")
        digest.update(source.read_bytes())
    return {
        "files": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "source_sha256": digest.hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["api", "bridge", "web"], required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="agora-pilot-build-") as directory:
        context = Path(directory)
        inventory = stage(context, args.target)
        print(json.dumps({"context_allowlisted": True, **inventory}), flush=True)
        subprocess.run(
            [
                "docker",
                "build",
                "--pull=false",
                "--build-arg",
                "AGORA_SOURCE_SHA256=" + inventory["source_sha256"],
                "--target",
                args.target,
                "-f",
                "infra/pilot/Dockerfile.web" if args.target == "web" else "infra/pilot/Dockerfile",
                "-t",
                args.tag,
                ".",
            ],
            cwd=context,
            check=True,
        )


if __name__ == "__main__":
    main()
