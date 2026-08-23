"""Local Artifact publication boundary (S5-T14, ADR-0027).

The Bridge is the ONLY place a local file path is ever accepted — the API
never sees a path, only bytes streamed through this boundary. Every rule
below exists to keep publication an explicit, single-file, owner-permitted
act, never an automatic workspace/secret upload:

- Exactly one regular file per call: no recursive directory upload.
- Symlinks are refused outright: a symlink could point anywhere on disk,
  defeating any path-based review the owner did before granting FILES_READ.
- A hard-coded secret-filename deny-list blocks the obvious cases (.env,
  private keys, credential stores) even when FILES_READ is granted broadly.
- Requires LocalPermission.FILES_READ from the LOCAL owner — remote AGORA
  content can never grant this (see LocalPolicyEngine.grants_from_remote_payload).
- Every attempt (allowed or denied) is written to the local audit log.
"""

from pathlib import Path

from agora_bridge.audit import LocalAuditLog
from agora_bridge.config import BridgeConfig
from agora_bridge.policy import LocalPermission, LocalPolicyEngine

MAX_LOCAL_PUBLISH_BYTES = 200 * 1024 * 1024

_SECRET_PATH_MARKERS = (
    ".env", "id_rsa", "id_ed25519", "id_ecdsa", ".pem", ".ssh", ".aws",
    ".netrc", "credentials", ".git/config", "secret",
)


class PublishDenied(Exception):
    pass


def validate_local_publish_path(config: BridgeConfig, raw_path: str, *, audit: LocalAuditLog) -> Path:
    """Returns a safe, absolute Path ready to stream, or raises PublishDenied."""
    engine = LocalPolicyEngine(config)
    decision = engine.decide(LocalPermission.FILES_READ)
    if not decision.allowed:
        audit.record("artifact.publish_denied", path=raw_path, reason=decision.reason)
        raise PublishDenied(f"Local policy denies files.read: {decision.reason}")

    candidate = Path(raw_path)
    if candidate.is_symlink():
        audit.record("artifact.publish_denied", path=raw_path, reason="symlink refused")
        raise PublishDenied("Refusing to publish a symlink (escape risk).")

    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        audit.record("artifact.publish_denied", path=raw_path, reason="not a regular file")
        raise PublishDenied("Only a single regular file may be published (no directory upload).")

    lowered = str(resolved).lower()
    if any(marker in lowered for marker in _SECRET_PATH_MARKERS):
        audit.record("artifact.publish_denied", path=raw_path, reason="secret-shaped path")
        raise PublishDenied(
            "This path looks like a secret/credential file and will never be published."
        )

    size = resolved.stat().st_size
    if size > MAX_LOCAL_PUBLISH_BYTES:
        audit.record("artifact.publish_denied", path=raw_path, reason="too large")
        raise PublishDenied(f"File exceeds the {MAX_LOCAL_PUBLISH_BYTES} byte local publish cap.")

    audit.record("artifact.publish_allowed", path=str(resolved), size=size)
    return resolved
