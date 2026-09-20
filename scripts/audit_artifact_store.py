#!/usr/bin/env python3
"""Read-only, offline verification of a DB artifact manifest against its blob store.

Exit 0: complete; 2: missing, corrupt or invalid references. Never modifies bytes,
metadata or the database. Run on a consistent DB/blob backup, or with uploads paused.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path


def audit(manifest: list[dict], root: Path) -> dict:
    root = root.resolve()
    results = []
    seen = set()
    for row in manifest:
        digest, size, key = (row.get(k) for k in (
            "content_hash", "content_size", "storage_key"
        ))
        if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or type(size) is not int or size < 0
                or key != f"sha256/{digest[:2]}/{digest}"):
            results.append({"status": "invalid_reference",
                            "artifact_version_id": row.get("artifact_version_id")})
            continue
        reference = (key, size)
        if reference in seen:
            continue
        seen.add(reference)
        path = root / key
        try:
            if not path.resolve().is_relative_to(root / "sha256"):
                status = "unsafe_path"
            elif not path.is_file():
                status = "missing"
            else:
                with path.open("rb") as stream:
                    actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
                    actual_size = stream.tell()
                status = "verified" if actual_hash == digest and actual_size == size else "corrupt"
        except OSError:
            status = "unreadable"
        results.append({"content_hash": digest, "content_size": size,
                        "storage_key": key, "status": status})
    return {"complete": all(r["status"] == "verified" for r in results),
            "version_count": len(manifest), "distinct_reference_count": len(seen),
            "verified_count": sum(r["status"] == "verified" for r in results),
            "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--store-root", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        if not isinstance(manifest, list) or not all(isinstance(r, dict) for r in manifest):
            raise ValueError("Manifest must be a list of artifact-version objects")
        result = audit(manifest, args.store_root)
    except (ValueError, OSError) as exc:
        print(json.dumps({"complete": False, "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
