import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "evidence_pack", Path(__file__).parents[1] / "tools/evidence_pack.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_index_verifies_then_detects_modified_artifact(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    artifact = root / "result.txt"
    artifact.write_text("PASS")
    engine = tmp_path / "engine"
    engine.write_bytes(b"TEST")
    index = tmp_path / "index.json"
    module.collect(root, index, "fixture", engine)
    assert module.verify(root, index) == []
    artifact.write_text("CHANGED")
    assert module.verify(root, index) == ["result.txt"]
    with pytest.raises(ValueError, match="exists"):
        module.collect(root, index, "fixture", engine)


def test_evidence_refuses_symlink(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    (root / "escape").symlink_to("/etc/hostname")
    with pytest.raises(ValueError, match="Symlinks"):
        module.collect(root, tmp_path / "index.json", "fixture", tmp_path / "engine")
