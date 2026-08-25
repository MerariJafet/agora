"""Local Device Installation Key lifecycle.

The installation key identifies this local Bridge installation without
collecting hardware facts. It is generated locally, stored with file mode 0600,
and used only as an owner-side continuity hint; AGORA Cloud never receives a
private key, MAC address, disk serial, hostname or TPM fingerprint.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from ulid import ULID

from agora_bridge.config import bridge_home


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def installation_path() -> Path:
    return bridge_home() / "installation.json"


@dataclass(frozen=True)
class InstallationKey:
    installation_key_id: str
    public_key: str


def ensure_installation_key() -> InstallationKey:
    """Create or load the local installation key metadata.

    The private key is intentionally local-only. Sprint post-roadmap phase 1
    stores only public installation metadata in BridgeConfig and API lineage.
    """
    path = installation_path()
    if path.exists():
        data = json.loads(path.read_text())
        return InstallationKey(data["installation_key_id"], data["public_key"])

    private = Ed25519PrivateKey.generate()
    private_raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_raw = private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    data = {
        "installation_key_id": f"dik_{ULID()}",
        "public_key": _b64url(public_raw),
        "private_key": _b64url(private_raw),
        "hardware_identifiers_collected": False,
    }
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    path.chmod(0o600)
    return InstallationKey(data["installation_key_id"], data["public_key"])
