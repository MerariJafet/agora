"""The bridge's standalone verifier must stay in lockstep with the server's.

The Bridge is installable without the server package; this parity test is the
contract that keeps the duplicated verification logic honest.
"""

from agora_api import world_signing as server
from agora_bridge import world_verify as bridge


def test_constants_match() -> None:
    assert bridge.CONSTITUTION_HASH == server.CONSTITUTION_HASH
    assert bridge.SIGNATURE_ALGORITHM == server.SIGNATURE_ALGORITHM


def test_canonical_payload_matches() -> None:
    manifest = {
        "b": [1, 2, {"z": "ñ"}],
        "a": "x",
        "epoch": 3,
        "signature": {"key_id": "k", "signature": "s"},
    }
    assert bridge.canonical_manifest_payload(manifest) == server.canonical_manifest_payload(
        manifest
    )


def test_signed_manifest_verifies_with_bridge_module() -> None:
    manifest = server.sign_manifest(
        {"landmarks": [], "portals": [], "nav_edges": [], "bounds": {}, "lod": {}}
    )
    keys = {manifest["signature"]["key_id"]: manifest["signature"]["public_key"]}
    assert bridge.verify_manifest(manifest, trusted_public_keys=keys)
