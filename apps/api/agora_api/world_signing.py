"""Signed WorldManifest trust envelope (P1 stabilization).

ETag remains cache metadata only. Authenticity comes from an Ed25519 signature
over a deterministic canonical payload that excludes the signature envelope.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from agora_api.config import get_settings
from agora_api.errors import AuthRequired, SignatureInvalid
from agora_api.passports_service import CONSTITUTION_HASH

CONSTITUTION_VERSION = "2026-08-25.p1-stabilization"
SIGNATURE_ALGORITHM = "Ed25519"
WORLD_PROTOCOL_VERSION = "world-manifest.v1"
DEV_SENTINEL_SECRET = "agora-dev-world-signing-secret-change-me"  # noqa: S105
DEV_SENTINEL_KEY_ID = "agora-world-dev-2026-08"


def signing_assurance() -> dict[str, Any]:
    settings = get_settings()
    sentinel = settings.world_signing_secret == DEV_SENTINEL_SECRET
    local_dev = settings.env == "development" and not settings.public_open_world
    if settings.env == "test":
        source = "deterministic_test"
    elif sentinel and local_dev:
        source = "local_development_sentinel"
    else:
        source = "configured_secret"
    return {
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": settings.world_signing_key_id,
        "assurance": source,
        "rotation_status": "active",
        "sentinel": sentinel,
        "public_open_world": settings.public_open_world,
    }


def assert_world_signing_configuration_safe() -> None:
    settings = get_settings()
    sentinel_secret = settings.world_signing_secret == DEV_SENTINEL_SECRET
    sentinel_key = settings.world_signing_key_id == DEV_SENTINEL_KEY_ID
    if settings.env == "test":
        return
    if settings.env == "development" and not settings.public_open_world:
        if not settings.world_signing_secret:
            raise AuthRequired("Development world signing key is not configured.")
        return
    if not settings.world_signing_secret:
        raise AuthRequired("World signing key is not configured.")
    if sentinel_secret or sentinel_key:
        raise AuthRequired("Production/public WorldManifest signing key uses development sentinel.")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def canonical_manifest_payload(manifest: dict[str, Any]) -> bytes:
    unsigned = {k: v for k, v in manifest.items() if k != "signature"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def _private_key() -> Ed25519PrivateKey:
    settings = get_settings()
    assert_world_signing_configuration_safe()
    seed = hashlib.sha256(settings.world_signing_secret.encode()).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_key_b64() -> str:
    raw = _private_key().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return b64url(raw)


def add_manifest_security_fields(manifest: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    spaces_digest = hashlib.sha256(
        json.dumps(
            {
                "landmarks": manifest["landmarks"],
                "portals": manifest["portals"],
                "nav_edges": manifest["nav_edges"],
                "bounds": manifest["bounds"],
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    secured = dict(manifest)
    secured.update(
        {
            "world_id": "agora-genesis-world",
            "world_protocol_version": WORLD_PROTOCOL_VERSION,
            "constitution_version": CONSTITUTION_VERSION,
            "constitution_hash": CONSTITUTION_HASH,
            "epoch": settings.world_manifest_epoch,
            "issued_at": "2026-08-25T00:00:00Z",
            "freshness_policy": {
                "max_age_seconds": 60,
                "requires_revalidation": True,
                "etag_is_cache_only": True,
            },
            "affordances_digest": hashlib.sha256(
                json.dumps(secured.get("lod", {}), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "spaces_landmarks_digest": spaces_digest,
            "resource_policy_digest": hashlib.sha256(
                b"no server frame loop; no coordinate streaming; local policy remains authoritative"
            ).hexdigest(),
        }
    )
    return secured


def sign_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    secured = add_manifest_security_fields(manifest)
    key = _private_key()
    payload = canonical_manifest_payload(secured)
    signature = key.sign(payload)
    secured["signature"] = {
        "schema_version": "1.0",
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": get_settings().world_signing_key_id,
        "public_key": public_key_b64(),
        "signature": b64url(signature),
        "payload_hash": hashlib.sha256(payload).hexdigest(),
    }
    return secured


def sign_canonical_payload(payload: dict[str, Any], *, domain: str) -> dict[str, Any]:
    """Sign an arbitrary canonical world payload with explicit domain separation."""
    signed_payload = {"domain": domain, "payload": payload}
    raw = json.dumps(
        signed_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()
    signature = _private_key().sign(raw)
    return {
        "schema_version": "1.0",
        "domain": domain,
        "algorithm": SIGNATURE_ALGORITHM,
        "key_id": get_settings().world_signing_key_id,
        "public_key": public_key_b64(),
        "signature": b64url(signature),
        "payload_hash": hashlib.sha256(raw).hexdigest(),
    }


def verify_canonical_payload(
    payload: dict[str, Any],
    signature: dict[str, Any],
    *,
    domain: str,
    trusted_public_keys: dict[str, str],
) -> bool:
    if signature.get("domain") != domain:
        raise SignatureInvalid("Signed payload domain mismatch.")
    if signature.get("algorithm") != SIGNATURE_ALGORITHM:
        raise SignatureInvalid("Unsupported payload signature algorithm.")
    key_id = signature.get("key_id")
    public_key = trusted_public_keys.get(str(key_id))
    if not public_key:
        raise SignatureInvalid("Unknown payload signing key.")
    raw = json.dumps(
        {"domain": domain, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    if signature.get("payload_hash") != hashlib.sha256(raw).hexdigest():
        raise SignatureInvalid("Signed payload hash mismatch.")
    try:
        key = Ed25519PublicKey.from_public_bytes(b64url_decode(public_key))
        key.verify(b64url_decode(str(signature.get("signature"))), raw)
    except Exception as exc:  # noqa: BLE001
        raise SignatureInvalid("Signed payload verification failed.") from exc
    return True


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


def trust_bootstrap() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "world_id": "agora-genesis-world",
        "constitution_version": CONSTITUTION_VERSION,
        "constitution_hash": CONSTITUTION_HASH,
        "minimum_epoch": get_settings().world_manifest_epoch,
        "active_keys": [
            {
                "key_id": get_settings().world_signing_key_id,
                "algorithm": SIGNATURE_ALGORITHM,
                "public_key": public_key_b64(),
                "status": "active",
                "assurance": signing_assurance()["assurance"],
            }
        ],
        "signing_assurance": signing_assurance(),
        "rotation_policy": (
            "New keys are published with overlapping active status for one epoch; "
            "retired keys are rejected once minimum_epoch advances."
        ),
    }
