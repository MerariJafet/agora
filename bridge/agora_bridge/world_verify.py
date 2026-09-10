"""Self-contained WorldManifest verification for the Bridge.

The Bridge must be installable WITHOUT the AGORA server package: participants
install only the client. This module mirrors the verification side of
``agora_api.world_signing`` (same canonical payload, same constants) and is
kept intentionally free of server imports. The signing side stays server-only.

Parity contract: ``CONSTITUTION_HASH``, ``SIGNATURE_ALGORITHM`` and the
canonical payload encoding MUST match ``apps/api/agora_api/world_signing.py``;
``tests/unit/test_bridge_world_verify_parity.py`` enforces this.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

CONSTITUTION_HASH = hashlib.sha256(
    b"AGORA Constitution: edge intelligence, untrusted remote content, consensus is not truth"
).hexdigest()
SIGNATURE_ALGORITHM = "Ed25519"


class SignatureInvalid(Exception):
    """Raised when a signed world payload fails verification."""


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical_manifest_payload(manifest: dict[str, Any]) -> bytes:
    unsigned = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def verify_manifest(
    manifest: dict[str, Any],
    *,
    trusted_public_keys: dict[str, str],
    min_epoch: int = 1,
    expected_constitution_hash: str = CONSTITUTION_HASH,
) -> bool:
    envelope = manifest.get("signature")
    if not isinstance(envelope, dict):
        raise SignatureInvalid("WorldManifest is unsigned.")
    key_id = envelope.get("key_id")
    public_key = trusted_public_keys.get(str(key_id))
    if not public_key:
        raise SignatureInvalid("Unknown WorldManifest signing key.")
    if envelope.get("algorithm") != SIGNATURE_ALGORITHM:
        raise SignatureInvalid("Unsupported WorldManifest signature algorithm.")
    if manifest.get("constitution_hash") != expected_constitution_hash:
        raise SignatureInvalid("WorldManifest constitution hash mismatch.")
    if int(manifest.get("epoch") or 0) < min_epoch:
        raise SignatureInvalid("WorldManifest epoch is stale.")
    payload = canonical_manifest_payload(manifest)
    if envelope.get("payload_hash") != hashlib.sha256(payload).hexdigest():
        raise SignatureInvalid("WorldManifest payload hash mismatch.")
    try:
        key = Ed25519PublicKey.from_public_bytes(b64url_decode(public_key))
        key.verify(b64url_decode(str(envelope.get("signature"))), payload)
    except Exception as exc:  # noqa: BLE001 - normalize crypto failures
        raise SignatureInvalid("WorldManifest signature verification failed.") from exc
    return True
