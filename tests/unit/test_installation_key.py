"""Device Installation Key lifecycle tests."""

import json
import stat
import sys

import pytest
from agora_bridge.installation import ensure_installation_key, installation_path

# Windows has no POSIX file modes; there the keyring/ACL path is the guard.
NO_POSIX_MODES = pytest.mark.skipif(sys.platform == "win32", reason="no POSIX file modes")


@NO_POSIX_MODES
def test_installation_key_is_local_persistent_and_hardware_free(tmp_path, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))

    first = ensure_installation_key()
    second = ensure_installation_key()
    path = installation_path()
    data = json.loads(path.read_text())

    assert first == second
    assert first.installation_key_id.startswith("dik_")
    assert data["hardware_identifiers_collected"] is False
    assert "hostname" not in str(data).lower()
    assert "machine" not in str(data).lower()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
