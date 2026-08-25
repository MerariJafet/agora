"""Bridge-side WorldManifest verification."""

from __future__ import annotations

from typing import Any

from agora_api.world_signing import CONSTITUTION_HASH, verify_manifest


def verify_world_manifest(manifest: dict[str, Any], trust_bootstrap: dict[str, Any]) -> bool:
    keys = {
        key["key_id"]: key["public_key"]
        for key in trust_bootstrap.get("active_keys", [])
        if key.get("status") == "active"
    }
    return verify_manifest(
        manifest,
        trusted_public_keys=keys,
        min_epoch=int(trust_bootstrap.get("minimum_epoch") or 1),
        expected_constitution_hash=str(
            trust_bootstrap.get("constitution_hash") or CONSTITUTION_HASH
        ),
    )
