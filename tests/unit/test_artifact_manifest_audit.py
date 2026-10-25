"""Offline audits must not mistake partial recovery or same-size corruption for PASS."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "artifact_audit", Path(__file__).resolve().parents[2] / "scripts/audit_artifact_store.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
audit = _module.audit


@pytest.mark.parametrize("damage", [None, "missing", "corrupt", "escape", "size_mismatch"])
def test_audit_requires_original_bytes_and_safe_paths(tmp_path, damage):
    content = b"original"
    digest = hashlib.sha256(content).hexdigest()
    key = f"sha256/{digest[:2]}/{digest}"
    row = {"content_hash": digest, "content_size": len(content), "storage_key": key}
    root = tmp_path / "store"
    blob = root / key
    blob.parent.mkdir(parents=True)
    if damage == "escape":
        outside = tmp_path / "private"
        outside.write_bytes(content)
        blob.symlink_to(outside)
    elif damage != "missing":
        blob.write_bytes(b"tampered" if damage == "corrupt" else content)
    if damage == "size_mismatch":
        row["content_size"] += 1
    result = audit([row, row], root)
    assert result["version_count"] == 2
    assert result["distinct_reference_count"] == 1
    assert result["complete"] is (damage is None)
    assert result["verified_count"] == int(damage is None)


def test_manifest_path_cannot_override_content_address(tmp_path):
    row = {"content_hash": "a" * 64, "content_size": 1, "storage_key": "../../secret"}
    result = audit([row], tmp_path)
    assert not result["complete"]
    assert result["results"][0]["status"] == "invalid_reference"
