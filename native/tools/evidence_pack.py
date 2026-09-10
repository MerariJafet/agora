#!/usr/bin/env python3
"""Index immutable local experiment evidence without copying private node homes."""

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

PRIVATE = re.compile(
    rb"-----BEGIN (?:ENCRYPTED |RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{32}"
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def collect(root, output, source_commit, engine):
    root, output = root.resolve(), output.absolute()
    if output.exists():
        raise ValueError("Evidence index already exists; use a new output path")
    files, findings = [], []
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError("Symlinks forbidden in evidence tree")
        if not p.is_file() or p.absolute() == output:
            continue
        data = p.read_bytes()
        files.append(
            {
                "path": str(p.relative_to(root)),
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        if PRIVATE.search(data):
            findings.append({"path": str(p.relative_to(root)), "type": "PRIVATE_KEY_CONTAINER"})
    inventory = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    result = {
        "format": "AGORA_ALPHA_EVIDENCE_INDEX_V1",
        "mode": "TEST_NON_RECOGNIZABLE",
        "source_commit": source_commit,
        "engine_sha256": sha(engine),
        "OS": platform.platform(),
        "architecture": platform.machine(),
        "python": sys.version,
        "files": files,
        "inventory_sha256": hashlib.sha256(inventory).hexdigest(),
        "secret_pattern_findings": findings,
        "scan_scope": (
            "All files in evidence root; PEM-container pattern only. "
            "Complement secret-audit.json. Does not prove all secrets absent."
        ),
        "status": "FAIL" if findings else "INDEXED",
        "independent_attestation": False,
    }
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    return result


def verify(root, index):
    result = json.loads(index.read_text())
    failures = []
    for item in result["files"]:
        path = (root / item["path"]).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or not path.is_file()
            or sha(path) != item["sha256"]
        ):
            failures.append(item["path"])
    return failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        bad = verify(args.root, args.output)
        print(json.dumps({"status": "FAIL" if bad else "PASS", "mismatched_paths": bad}))
        raise SystemExit(bool(bad))
    if not args.source_commit or not args.engine:
        parser.error("source-commit and engine required for new pack")
    subprocess.run(
        [shutil.which("git") or "/usr/bin/git", "cat-file", "-e", args.source_commit + "^{commit}"],
        check=True,
    )
    report = collect(args.root, args.output, args.source_commit, args.engine)
    print(json.dumps({k: v for k, v in report.items() if k != "files"}))
    raise SystemExit(bool(report["secret_pattern_findings"]))
