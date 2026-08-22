"""IdentityManager: Ed25519 device identity, generated and kept locally.

Storage order (S1-T06):
1. OS keyring (Secret Service / Keychain / Windows Credential Locker) via the
   `keyring` package, when a real backend is available.
2. Documented development fallback: file under AGORA_BRIDGE_HOME/keys with
   0600 permissions. The fallback is explicit — a warning is printed and the
   storage backend is recorded in config metadata. Never use the file
   fallback for production deployments.

The private key NEVER leaves this module except to sign() locally.
"""

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from agora_bridge.config import bridge_home

KEYRING_SERVICE = "agora-bridge"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _keyring_available() -> bool:
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        return not isinstance(keyring.get_keyring(), FailKeyring)
    except Exception:
        return False


def _file_key_path(agent_name: str) -> Path:
    return bridge_home() / "keys" / f"{agent_name}.ed25519"


class IdentityManager:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.storage_backend: str = "keyring" if _keyring_available() else "file"

    # -- storage -----------------------------------------------------------
    def _store(self, private_bytes: bytes) -> None:
        encoded = _b64url(private_bytes)
        if self.storage_backend == "keyring":
            import keyring

            keyring.set_password(KEYRING_SERVICE, self.agent_name, encoded)
            return
        print(
            "WARNING: no OS keyring backend available; storing device key in "
            f"{_file_key_path(self.agent_name)} (mode 0600). Development fallback only.",
            file=sys.stderr,
        )
        path = _file_key_path(self.agent_name)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.write_text(encoded + "\n")
        path.chmod(0o600)

    def _load(self) -> bytes | None:
        if self.storage_backend == "keyring":
            import keyring

            encoded = keyring.get_password(KEYRING_SERVICE, self.agent_name)
        else:
            path = _file_key_path(self.agent_name)
            encoded = path.read_text().strip() if path.exists() else None
        return _b64url_decode(encoded) if encoded else None

    # -- identity ----------------------------------------------------------
    def exists(self) -> bool:
        return self._load() is not None

    def generate(self) -> str:
        """Generate a new device identity. Returns the public key (b64url)."""
        if self.exists():
            raise RuntimeError(f"identity for '{self.agent_name}' already exists")
        private = Ed25519PrivateKey.generate()
        raw = private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
        self._store(raw)
        return self.public_key()

    def _private_key(self) -> Ed25519PrivateKey:
        raw = self._load()
        if raw is None:
            raise RuntimeError(f"no identity for '{self.agent_name}'. Run `agora init` first.")
        return Ed25519PrivateKey.from_private_bytes(raw)

    def public_key(self) -> str:
        raw = self._private_key().public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return _b64url(raw)

    def sign(self, message: bytes) -> str:
        """Sign locally; only the signature (never the key) crosses the wire."""
        return _b64url(self._private_key().sign(message))

    def delete(self) -> None:
        if self.storage_backend == "keyring":
            import keyring

            try:
                keyring.delete_password(KEYRING_SERVICE, self.agent_name)
            except Exception:
                pass
        else:
            _file_key_path(self.agent_name).unlink(missing_ok=True)
