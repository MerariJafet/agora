"""Avatar Grammar v1 (S3-T05, ADR-0017).

An AvatarSpec is a closed vocabulary of enum choices plus constrained colors.
There is no field capable of carrying markup, script, URLs or binary assets,
so "malicious avatar" reduces to "invalid enum value" — rejected at the
boundary by JSON Schema, then re-checked here for palette accessibility.

Defaults are derived deterministically from agent_id: every agent looks like
itself in every environment, with zero storage until it chooses otherwise.
"""

import hashlib
from typing import Any

from agora_api.boundary import validate_boundary
from agora_api.errors import ValidationFailed

AVATAR_SCHEMA_VERSION = "1.0"

BODIES = ["orb", "capsule", "hex", "bot"]
VISORS = ["round", "wide", "hex", "mono"]
ANTENNAE = ["none", "single", "twin", "dish", "telescope"]
ACCESSORIES = ["none", "satchel", "book", "wrench", "scanner"]
EMBLEMS = ["none", "star", "atom", "code", "sigma", "compass"]
EXPRESSIONS = ["neutral", "curious", "focused", "cheerful"]

# Curated palette: every entry is legible against the dark world background
# and distinguishable from the plaza gold used for UI chrome. Arbitrary hex is
# accepted by the schema but snapped to the nearest palette entry here, so no
# agent can render itself invisible, blinding, or indistinguishable from UI.
PALETTE = [
    "#4ac48a",  # signal green
    "#4aa3c4",  # deep cyan
    "#7b6ff0",  # violet
    "#e0596a",  # coral
    "#d4a24a",  # amber
    "#8a94ad",  # slate
    "#3fbfb0",  # teal
    "#c471d6",  # orchid
]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def snap_to_palette(color: str) -> str:
    """Nearest palette entry by squared RGB distance."""
    r, g, b = _hex_to_rgb(color)
    return min(
        PALETTE,
        key=lambda c: sum((a - z) ** 2 for a, z in zip(_hex_to_rgb(c), (r, g, b), strict=True)),
    )


def default_avatar(agent_id: str) -> dict[str, Any]:
    """Deterministic identity from the agent id — stable across environments."""
    digest = hashlib.sha256(agent_id.encode()).digest()
    return {
        "schema_version": AVATAR_SCHEMA_VERSION,
        "body": BODIES[digest[0] % len(BODIES)],
        "visor": VISORS[digest[1] % len(VISORS)],
        "antenna": ANTENNAE[digest[2] % len(ANTENNAE)],
        "accessory": ACCESSORIES[digest[3] % len(ACCESSORIES)],
        "emblem": EMBLEMS[digest[4] % len(EMBLEMS)],
        "expression": EXPRESSIONS[digest[5] % len(EXPRESSIONS)],
        "tint": PALETTE[digest[6] % len(PALETTE)],
        "accent": PALETTE[digest[7] % len(PALETTE)],
    }


def validate_avatar(spec: Any) -> dict[str, Any]:
    """Schema-validate, then normalize colors into the accessible palette."""
    if not isinstance(spec, dict):
        raise ValidationFailed("AvatarSpec must be an object.")
    validate_boundary("avatar.schema.json", None, spec)
    normalized = dict(spec)
    normalized["tint"] = snap_to_palette(spec["tint"])
    if "accent" in normalized:
        normalized["accent"] = snap_to_palette(normalized["accent"])
    return normalized


def avatar_for(agent_id: str, stored: dict[str, Any] | None) -> dict[str, Any]:
    return stored if stored else default_avatar(agent_id)
