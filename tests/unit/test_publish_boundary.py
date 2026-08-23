"""Local Artifact publication boundary (S5-T14, S5-T25): default-deny
without files.read, symlink refusal, secret-filename deny-list, no
directory upload, size cap."""

import pytest
from agora_bridge.audit import LocalAuditLog
from agora_bridge.config import BridgeConfig
from agora_bridge.publish_boundary import PublishDenied, validate_local_publish_path


def _audit(tmp_path) -> LocalAuditLog:
    return LocalAuditLog(path=tmp_path / "audit.log")


def test_denied_without_local_grant(tmp_path):
    target = tmp_path / "report.txt"
    target.write_text("hello")
    config = BridgeConfig()  # no granted_permissions
    with pytest.raises(PublishDenied, match="files.read"):
        validate_local_publish_path(config, str(target), audit=_audit(tmp_path))


def test_allowed_with_grant(tmp_path):
    target = tmp_path / "report.txt"
    target.write_text("hello")
    config = BridgeConfig(granted_permissions=["files.read"])
    resolved = validate_local_publish_path(config, str(target), audit=_audit(tmp_path))
    assert resolved == target.resolve()


def test_directory_rejected(tmp_path):
    subdir = tmp_path / "workspace"
    subdir.mkdir()
    config = BridgeConfig(granted_permissions=["files.read"])
    with pytest.raises(PublishDenied, match="regular file"):
        validate_local_publish_path(config, str(subdir), audit=_audit(tmp_path))


def test_symlink_rejected(tmp_path):
    real = tmp_path / "real.txt"
    real.write_text("hello")
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    config = BridgeConfig(granted_permissions=["files.read"])
    with pytest.raises(PublishDenied, match="symlink"):
        validate_local_publish_path(config, str(link), audit=_audit(tmp_path))


@pytest.mark.parametrize("name", [".env", "id_rsa", "credentials.json", "secrets.yaml"])
def test_secret_shaped_filenames_rejected(tmp_path, name):
    target = tmp_path / name
    target.write_text("SECRET")
    config = BridgeConfig(granted_permissions=["files.read"])
    with pytest.raises(PublishDenied, match="secret"):
        validate_local_publish_path(config, str(target), audit=_audit(tmp_path))


def test_oversized_file_rejected(tmp_path, monkeypatch):
    import agora_bridge.publish_boundary as pb

    monkeypatch.setattr(pb, "MAX_LOCAL_PUBLISH_BYTES", 4)
    target = tmp_path / "big.txt"
    target.write_text("way too big")
    config = BridgeConfig(granted_permissions=["files.read"])
    with pytest.raises(PublishDenied, match="cap"):
        validate_local_publish_path(config, str(target), audit=_audit(tmp_path))


def test_denials_and_allowances_are_audited(tmp_path):
    target = tmp_path / "ok.txt"
    target.write_text("hello")
    config = BridgeConfig(granted_permissions=["files.read"])
    audit = _audit(tmp_path)
    validate_local_publish_path(config, str(target), audit=audit)
    entries = audit.tail(5)
    assert any(e["action"] == "artifact.publish_allowed" for e in entries)
