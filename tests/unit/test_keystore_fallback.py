"""Private-key storage review (S1.1-T08): the file fallback is explicit,
permission-restricted, and never silently selected in production-like
environments."""

import pytest
from agora_bridge import identity as identity_mod
from agora_bridge.identity import IdentityManager


@pytest.fixture
def file_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(identity_mod, "_keyring_available", lambda: False)
    monkeypatch.setenv("AGORA_BRIDGE_HOME", str(tmp_path))
    return tmp_path


def test_production_refuses_file_keystore_without_opt_in(file_backend, monkeypatch):
    monkeypatch.setenv("AGORA_BRIDGE_ENV", "production")
    monkeypatch.delenv("AGORA_BRIDGE_ALLOW_FILE_KEYSTORE", raising=False)
    manager = IdentityManager("ProdAgent")
    assert manager.storage_backend == "file"
    with pytest.raises(RuntimeError, match="Refusing the plaintext-file keystore"):
        manager.generate()
    assert not (file_backend / "keys").exists()


def test_production_file_keystore_with_explicit_opt_in(file_backend, monkeypatch, capsys):
    monkeypatch.setenv("AGORA_BRIDGE_ENV", "production")
    monkeypatch.setenv("AGORA_BRIDGE_ALLOW_FILE_KEYSTORE", "1")
    manager = IdentityManager("OptInAgent")
    public_key = manager.generate()
    assert len(public_key) == 43
    warning = capsys.readouterr().err
    assert "WARNING" in warning and "fallback" in warning.lower()
    key_file = file_backend / "keys" / "OptInAgent.ed25519"
    assert key_file.exists()
    assert (key_file.stat().st_mode & 0o777) == 0o600


def test_dev_fallback_warns_and_restricts_permissions(file_backend, monkeypatch, capsys):
    monkeypatch.delenv("AGORA_BRIDGE_ENV", raising=False)
    manager = IdentityManager("DevAgent")
    manager.generate()
    assert "WARNING" in capsys.readouterr().err
    key_file = file_backend / "keys" / "DevAgent.ed25519"
    assert (key_file.stat().st_mode & 0o777) == 0o600
    # signing works and never prints/logs key material
    signature = manager.sign(b"probe")
    assert len(signature) == 86
