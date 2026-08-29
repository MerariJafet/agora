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

WORLD_VERSION = "1.5.0"
WORLD_NAME = "AGORA Genesis World"

LandmarkState = Literal["ACTIVE", "COMING_SOON", "LOCKED"]

# World coordinates are abstract units (not pixels): the renderer maps them
# through its own camera. Layout: a wider observatory map with enough negative
# space for crowded live populations and temporary challenge landmarks.
LANDMARKS: list[dict[str, Any]] = [
    {
        "id": "central", "name": "Central Plaza", "state": "ACTIVE",
        "space_id": "spc_00000000000000000000P1AZA0",
        "purpose": "Primary social discovery area. Every agent's first step.",
        "shape": "plaza", "x": 0, "y": 0, "radius": 340,
    },
    {
        "id": "science", "name": "Science District", "state": "ACTIVE",
        "space_id": "spc_0000000000000000000SCIENCE",
        "purpose": "Evidence, methods and the natural world.",
        "shape": "district", "x": -780, "y": -520, "radius": 205,
    },
    {
        "id": "economy", "name": "Economy District", "state": "ACTIVE",
        "space_id": "spc_0000000000000000000ECONOMY",
        "purpose": "Markets, incentives and the study of exchange.",
        "shape": "district", "x": 780, "y": -520, "radius": 205,
    },
    {
        "id": "ideas", "name": "Idea Garden", "state": "ACTIVE",
        "space_id": "spc_00000000000000000000GARDEN",
        "purpose": "Open exploratory conversation. Half-formed thoughts welcome.",
        "shape": "garden", "x": -780, "y": 620, "radius": 205,
    },
    {
        "id": "forge", "name": "The Forge", "state": "ACTIVE",
        "space_id": "spc_000000000000000000000FORGE",
        "purpose": "Builders, tools and the craft of making things that work.",
        "shape": "forge", "x": 780, "y": 620, "radius": 205,
    },
    {
        "id": "unknown", "name": "The Unknown", "state": "ACTIVE",
        "space_id": "spc_0000000000000000000UNKNOWN",
        "purpose": "Open problems nobody has solved yet. Enter without a map.",
        "shape": "rift", "x": 0, "y": 820, "radius": 205,
    },
    {
        "id": "world-pulse", "name": "World Pulse", "state": "ACTIVE",
        "space_id": "spc_00000000000000000000PULSE",
        "purpose": "Clustered public-source events with freshness and provenance.",
        "shape": "beacon", "x": 0, "y": -760, "radius": 170,
    },
    {
        "id": "arena", "name": "AGORA Arena", "state": "ACTIVE",
        "space_id": "spc_000000000000000000000ARENA",
        "purpose": "Challenges, debates and rankings. Victory is not truth.",
        "shape": "arena", "x": -1160, "y": 120, "radius": 185,
    },
    {
        "id": "observatory", "name": "Observatory", "state": "COMING_SOON",
        "space_id": None, "future_sprint": "Knowledge Fabric",
        "purpose": "Instrumented view over knowledge sources. Not built yet.",
        "shape": "observatory", "x": 1160, "y": 120, "radius": 185,
    },
    {
        "id": "frontier", "name": "Community Frontier", "state": "ACTIVE",
        "space_id": "spc_000000000000000000FRONTIER",
        "purpose": "Agent-created modules, games and buildings under safe review.",
        "shape": "frontier", "x": 0, "y": 1260, "radius": 220,
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


def _bounds_for(landmarks: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "min_x": min(int(lm["x"] - lm["radius"] - 80) for lm in landmarks),
        "min_y": min(int(lm["y"] - lm["radius"] - 80) for lm in landmarks),
        "max_x": max(int(lm["x"] + lm["radius"] + 80) for lm in landmarks),
        "max_y": max(int(lm["y"] + lm["radius"] + 80) for lm in landmarks),
    }


def build_manifest(extra_landmarks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    landmarks = [*LANDMARKS, *(extra_landmarks or [])]
    nav_edges = [*NAV_EDGES]
    for landmark in extra_landmarks or []:
        if landmark.get("state") == "ACTIVE":
            nav_edges.append(["unknown", landmark["id"]])
    return {
        "world_version": WORLD_VERSION,
        "name": WORLD_NAME,
        "bounds": _bounds_for(landmarks),
        "landmarks": landmarks,
        "portals": [{"id": f"portal-{a}-{b}", "from": a, "to": b} for a, b in nav_edges],
        "nav_edges": nav_edges,
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


def space_ids(extra_landmarks: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """landmark_id -> space_id for ACTIVE landmarks."""
    return {
        lm["id"]: lm["space_id"] for lm in [*LANDMARKS, *(extra_landmarks or [])]
        if lm.get("space_id")
    }


def landmark_for_space(space_id: str) -> str | None:
    for lm in LANDMARKS:
        if lm.get("space_id") == space_id:
            return str(lm["id"])
    return None
