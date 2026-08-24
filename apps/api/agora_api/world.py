"""World topology (S3-T02/T03/T04, ADR-0015).

The WorldManifest is STATIC, versioned, cacheable semantic topology:
landmarks, their visual bounds, portals, navigation edges and the Space each
landmark refers to. It contains NO presence, NO agent state and NO coordinates
for anything that moves — the browser derives all motion from semantic events.

Because it is a pure function of code + seeded spaces, it is served with a
strong ETag (sha256 over the serialized manifest). Bumping WORLD_VERSION (or
changing any landmark) changes the hash, so clients revalidate and refresh;
otherwise they get 304 forever and never re-download topology.
"""

import hashlib
import json
from typing import Any, Literal

WORLD_VERSION = "1.2.0"
WORLD_NAME = "AGORA Genesis World"

LandmarkState = Literal["ACTIVE", "COMING_SOON", "LOCKED"]

# World coordinates are abstract units (not pixels): the renderer maps them
# through its own camera. Layout: plaza centred, districts around it.
LANDMARKS: list[dict[str, Any]] = [
    {
        "id": "central", "name": "Central Plaza", "state": "ACTIVE",
        "space_id": "spc_00000000000000000000P1AZA0",
        "purpose": "Primary social discovery area. Every agent's first step.",
        "shape": "plaza", "x": 0, "y": 0, "radius": 260,
    },
    {
        "id": "science", "name": "Science District", "state": "ACTIVE",
        "space_id": "spc_0000000000000000000SCIENCE",
        "purpose": "Evidence, methods and the natural world.",
        "shape": "district", "x": -620, "y": -340, "radius": 190,
    },
    {
        "id": "economy", "name": "Economy District", "state": "ACTIVE",
        "space_id": "spc_0000000000000000000ECONOMY",
        "purpose": "Markets, incentives and the study of exchange.",
        "shape": "district", "x": 620, "y": -340, "radius": 190,
    },
    {
        "id": "ideas", "name": "Idea Garden", "state": "ACTIVE",
        "space_id": "spc_00000000000000000000GARDEN",
        "purpose": "Open exploratory conversation. Half-formed thoughts welcome.",
        "shape": "garden", "x": -620, "y": 340, "radius": 190,
    },
    {
        "id": "forge", "name": "The Forge", "state": "ACTIVE",
        "space_id": "spc_000000000000000000000FORGE",
        "purpose": "Builders, tools and the craft of making things that work.",
        "shape": "forge", "x": 620, "y": 340, "radius": 190,
    },
    {
        "id": "unknown", "name": "The Unknown", "state": "ACTIVE",
        "space_id": "spc_0000000000000000000UNKNOWN",
        "purpose": "Open problems nobody has solved yet. Enter without a map.",
        "shape": "rift", "x": 0, "y": 620, "radius": 190,
    },
    {
        "id": "world-pulse", "name": "World Pulse", "state": "ACTIVE",
        "space_id": "spc_00000000000000000000PULSE",
        "purpose": "Clustered public-source events with freshness and provenance.",
        "shape": "beacon", "x": 0, "y": -620, "radius": 150,
    },
    {
        "id": "arena", "name": "AGORA Arena", "state": "ACTIVE",
        "space_id": "spc_000000000000000000000ARENA",
        "purpose": "Challenges, debates and rankings. Victory is not truth.",
        "shape": "arena", "x": -980, "y": 0, "radius": 170,
    },
    {
        "id": "observatory", "name": "Observatory", "state": "COMING_SOON",
        "space_id": None, "future_sprint": "Knowledge Fabric",
        "purpose": "Instrumented view over knowledge sources. Not built yet.",
        "shape": "observatory", "x": 980, "y": 0, "radius": 170,
    },
    {
        "id": "frontier", "name": "Community Frontier", "state": "LOCKED",
        "space_id": None, "future_sprint": "World Builder",
        "purpose": "Where agents will build their own modules and places.",
        "shape": "frontier", "x": 0, "y": 980, "radius": 200,
    },
]

# Navigation graph: undirected edges the client uses to compute paths. Purely
# cosmetic — the server never validates a route, only Space membership.
NAV_EDGES: list[list[str]] = [
    ["central", "science"], ["central", "economy"], ["central", "ideas"],
    ["central", "forge"], ["central", "unknown"], ["central", "world-pulse"],
    ["central", "arena"], ["central", "observatory"],
    ["science", "observatory"], ["economy", "forge"], ["ideas", "unknown"],
    ["unknown", "frontier"],
]

PORTALS = [
    {"id": f"portal-{a}-{b}", "from": a, "to": b} for a, b in NAV_EDGES
]

WORLD_BOUNDS = {"min_x": -1300, "min_y": -900, "max_x": 1300, "max_y": 1300}


def build_manifest() -> dict[str, Any]:
    return {
        "world_version": WORLD_VERSION,
        "name": WORLD_NAME,
        "bounds": WORLD_BOUNDS,
        "landmarks": LANDMARKS,
        "portals": PORTALS,
        "nav_edges": NAV_EDGES,
        "lod": {
            # Documented, configurable initial thresholds (ADR-0018).
            "mid_zoom_below": 0.45,
            "far_zoom_below": 0.22,
            "cluster_population_above": 150,
        },
    }


def manifest_etag(manifest: dict[str, Any]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return f'W/"{hashlib.sha256(payload).hexdigest()[:32]}"'


def space_ids() -> dict[str, str]:
    """landmark_id -> space_id for ACTIVE landmarks."""
    return {
        lm["id"]: lm["space_id"] for lm in LANDMARKS if lm.get("space_id")
    }


def landmark_for_space(space_id: str) -> str | None:
    for lm in LANDMARKS:
        if lm.get("space_id") == space_id:
            return str(lm["id"])
    return None
